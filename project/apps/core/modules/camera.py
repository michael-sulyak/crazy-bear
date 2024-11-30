import datetime
import logging
import typing
from functools import partial

import numpy as np
from imutils.video import VideoStream

from libs import task_queue
from libs.camera.base import VideoCamera
from libs.casual_utils.parallel_computing import synchronized_method
from libs.image_processing.utils import add_timestamp_in_frame
from libs.task_queue import IntervalTask

from .... import config
from ...common import interface
from ...common.constants import OFF, ON
from ...common.exceptions import Shutdown
from ...common.storage import file_storage
from ...common.utils import (
    camera_is_available,
    with_throttling,
)
from ...core import events
from ...core.constants import (
    CAMERA_IS_AVAILABLE,
    CURRENT_FPS,
    SECURITY_IS_ENABLED,
    USE_CAMERA,
    VIDEO_RECORDING_IS_ENABLED,
    VIDEO_SECURITY_IS_ENABLED,
)
from ...guard.video_guard import VideoGuard
from ..base import BaseModule
from ..constants import BotCommands, MotionTypeSources


__all__ = ('Camera',)


@interface.module(
    title='Camera',
    description=('The module provides integration with a camera.'),
)
class Camera(BaseModule):
    initial_state: typing.ClassVar = {
        VIDEO_SECURITY_IS_ENABLED: None,
        USE_CAMERA: False,
        CAMERA_IS_AVAILABLE: True,
        CURRENT_FPS: None,
        VIDEO_RECORDING_IS_ENABLED: False,
    }
    _video_stream: VideoStream | None = None
    _video_camera: VideoCamera | None = None
    _camera_is_available: bool = True
    _video_frames: list

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._update_camera_status()
        self._video_frames = []

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._save_photo,
                priority=task_queue.TaskPriorities.MEDIUM,
                interval=datetime.timedelta(seconds=10),
                run_immediately=False,
            ),
            IntervalTask(
                target=self._check_video_stream,
                priority=task_queue.TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=1),
            ),
            IntervalTask(
                target=self._update_camera_status,
                priority=task_queue.TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=10),
            ),
            IntervalTask(
                target=self.check,
                priority=task_queue.TaskPriorities.MEDIUM,
                interval=datetime.timedelta(seconds=10),
            ),
        )

    def subscribe_to_events(self) -> tuple:
        return (
            *super().subscribe_to_events(),
            events.frame_from_video_camera.connect(self._process_frame),
            events.motion_detected.connect(self._process_motion_detection),
            events.security_is_enabled.connect(self._enable_security),
            events.security_is_disabled.connect(self._disable_security),
        )

    @synchronized_method
    def check(self) -> None:
        video_guard: VideoGuard | None = self.state[VIDEO_SECURITY_IS_ENABLED]
        use_camera: bool = self.state[USE_CAMERA]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]

        if video_guard:
            assert self._video_camera is not None

            if self._video_camera.is_run or not use_camera or not security_is_enabled:
                self._disable_security()
                video_guard = None

        if not video_guard and use_camera and security_is_enabled and self.state[CAMERA_IS_AVAILABLE]:
            self._enable_security()

        if self._video_camera:
            self.state[CURRENT_FPS] = self._video_camera.fps
        else:
            self.state[CURRENT_FPS] = None

    @synchronized_method
    def disable(self) -> None:
        super().disable()

        if self.state[VIDEO_SECURITY_IS_ENABLED]:
            self._disable_security()

        if self.state[VIDEO_RECORDING_IS_ENABLED]:
            self._stop_video_recording()

        if self.state[USE_CAMERA]:
            self._disable_camera()

    @interface.command(BotCommands.CAMERA, ON)
    @synchronized_method
    def _enable_camera(self) -> None:
        if self.state[USE_CAMERA]:
            self.messenger.send_message('Camera is already on')
            return

        self._update_camera_status()

        if not self.state[CAMERA_IS_AVAILABLE]:
            self.messenger.send_message('Camera is not available')
            return

        self.state[USE_CAMERA] = True

        if self._video_camera is None:
            self._video_stream = VideoStream(src=config.VIDEO_SRC, resolution=config.IMAGE_RESOLUTION)
            self._video_stream.start()
            self._video_camera = VideoCamera(
                video_stream=self._video_stream,
                callback=partial(events.frame_from_video_camera.send, source=MotionTypeSources.VIDEO),
                max_fps=config.FPS,
            )
            self._video_camera.start()

        self.messenger.send_message('Camera is on')

        if self.state[VIDEO_SECURITY_IS_ENABLED]:
            self._enable_security()

    @interface.command(BotCommands.CAMERA, OFF)
    @synchronized_method
    def _disable_camera(self) -> None:
        if not self.state[USE_CAMERA]:
            self.messenger.send_message('Camera is already off')
            return

        self.state[USE_CAMERA] = False

        if self.state[SECURITY_IS_ENABLED]:
            self._disable_security()

        if self._video_stream is not None:
            assert self._video_camera is not None

            self._video_camera.stop()
            self._video_camera = None
            self._video_stream.stop()
            self._video_stream.stream.stream.release()
            self._video_stream = None

        self.messenger.send_message('Camera is off')

    @synchronized_method
    def _enable_security(self) -> None:
        if not self.state[USE_CAMERA]:
            return

        video_guard: VideoGuard = self.state[VIDEO_SECURITY_IS_ENABLED]

        if video_guard:
            self.messenger.send_message('Video security is already enabled')
            return

        if self._video_stream:
            video_guard = VideoGuard(
                messenger=self.messenger,
                task_queue=self.task_queue,
                motion_detected_callback=events.motion_detected.send,
            )
            self.state[VIDEO_SECURITY_IS_ENABLED] = video_guard
            video_guard.start()

        self.messenger.send_message('Video security is enabled')

    @synchronized_method
    def _disable_security(self) -> None:
        video_guard: VideoGuard = self.state[VIDEO_SECURITY_IS_ENABLED]

        if video_guard:
            video_guard.stop()
            self.state[VIDEO_SECURITY_IS_ENABLED] = None
            self.messenger.send_message('Video security is stopped')
        elif self.state[USE_CAMERA]:
            self.messenger.send_message('Video security is already disabled')

    @interface.command(BotCommands.CAMERA, 'photo')
    @synchronized_method
    def _take_photo(self) -> None:
        if not self._can_use_camera():
            return

        assert self._video_stream is not None

        frame = self._video_stream.read()

        if frame is None:
            return

        now = datetime.datetime.now()

        self.messenger.send_frame(
            frame,
            caption=f'Captured at {now.strftime("%d.%m.%Y, %H:%M:%S")}',
        )
        self.task_queue.put(
            file_storage.upload_frame,
            kwargs={
                'file_name': f'saved_photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                'frame': frame,
            },
            priority=task_queue.TaskPriorities.MEDIUM,
        )

    @interface.command(BotCommands.CAMERA, 'record', ON)
    @synchronized_method
    def _start_video_recording(self) -> None:
        if self.state[VIDEO_RECORDING_IS_ENABLED]:
            self.messenger.send_message('It is already started')
            return

        if not self._can_use_camera():
            return

        self.state[VIDEO_RECORDING_IS_ENABLED] = True
        self.messenger.send_message('Start recording...')

    @interface.command(BotCommands.CAMERA, 'record', OFF)
    @synchronized_method
    def _stop_video_recording(self) -> None:
        if not self.state[VIDEO_RECORDING_IS_ENABLED]:
            self.messenger.send_message('You need to start recording')
            return

        if not self._can_use_camera():
            return

        self.state[VIDEO_RECORDING_IS_ENABLED] = False
        video_frames = self._video_frames
        self._video_frames = []

        self.messenger.send_message('Sending the video...')
        self.task_queue.put(
            lambda: self.messenger.send_frames_as_video(
                frames=video_frames,
                fps=config.FPS,
                caption='Recorded video',
            ),
            priority=task_queue.TaskPriorities.MEDIUM,
        )

    def _can_use_camera(self) -> bool:
        use_camera: bool = self.state[USE_CAMERA]

        if use_camera:
            return True

        self.messenger.send_message('Camera is not enabled')
        return False

    @synchronized_method
    def _save_photo(self) -> None:
        if not self.state[USE_CAMERA] or not self._video_stream:
            return

        now = datetime.datetime.now()

        file_storage.upload_frame(
            file_name=f'photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
            frame=self._video_stream.read(),
        )

    @synchronized_method
    def _check_video_stream(self) -> None:
        if not self._video_stream:
            return

        frame = self._video_stream.read()

        if frame is None:
            self.state[CAMERA_IS_AVAILABLE] = False
            self.messenger.send_message('Camera is not available')
            self._run_command(BotCommands.CAMERA, OFF)

    @synchronized_method
    def _update_camera_status(self) -> None:
        if self._video_stream:
            return

        self.state[CAMERA_IS_AVAILABLE] = camera_is_available(config.VIDEO_SRC)

    @synchronized_method
    def _process_frame(self, frame, fps: float) -> None:
        video_guard: VideoGuard = self.state[VIDEO_SECURITY_IS_ENABLED]

        if video_guard:
            assert video_guard.process_frame is not None

            try:
                video_guard.process_frame.send(
                    (
                        frame,
                        fps,
                    )
                )
            except Shutdown:
                raise
            except Exception as e:
                logging.exception(e)
                self.messenger.send_message("Can't process the frame")
                self._disable_camera()

        if self.state[VIDEO_RECORDING_IS_ENABLED]:
            new_frame = np.copy(frame)
            add_timestamp_in_frame(new_frame)
            self._video_frames.append(new_frame)

    @synchronized_method
    @with_throttling(datetime.timedelta(seconds=5), count=1)
    def _process_motion_detection(self, *, source: str) -> None:
        if source == MotionTypeSources.SENSORS and self.state[USE_CAMERA]:
            self.task_queue.put(
                self._take_photo,
                priority=task_queue.TaskPriorities.HIGH,
            )
