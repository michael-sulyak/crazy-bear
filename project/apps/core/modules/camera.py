import datetime
import logging
import typing
from functools import partial

import numpy as np
from imutils.video import VideoStream

from ..base import BaseModule, Command
from ..constants import BotCommands, MotionTypeSources
from ... import task_queue
from ...common.camera import VideoCamera
from ...common.constants import OFF, ON
from ...common.storage import file_storage
from ...common.utils import add_timestamp_in_frame, camera_is_available, synchronized_method, with_throttling
from ...core import events
from ...core.constants import (
    CAMERA_IS_AVAILABLE, CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA, VIDEO_RECORDING_IS_ENABLED, VIDEO_SECURITY,
)
from ...guard.video_guard import VideoGuard
from ...task_queue import IntervalTask
from .... import config


__all__ = (
    'Camera',
)


class Camera(BaseModule):
    initial_state = {
        VIDEO_SECURITY: None,
        USE_CAMERA: False,
        CAMERA_IS_AVAILABLE: True,
        CURRENT_FPS: None,
        VIDEO_RECORDING_IS_ENABLED: False,
    }
    _video_stream: typing.Optional[VideoStream] = None
    _video_camera: typing.Optional[VideoCamera] = None
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
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CAMERA:
            if command.first_arg == ON:
                self._enable_camera()
            elif command.first_arg == OFF:
                self._disable_camera()
            elif command.first_arg == 'photo':
                self._take_photo()
            elif command.first_arg == 'record':
                if command.second_arg == ON:
                    self._start_video_recording()
                elif command.second_arg == OFF:
                    self._stop_video_recording()
                else:
                    return False
            else:
                return False

            return True

        if command.name == BotCommands.SECURITY:
            if command.first_arg == ON:
                self._enable_security()
            elif command.first_arg == OFF:
                self._disable_security()
            else:
                return False

            return True

        return False

    @synchronized_method
    def check(self) -> None:
        video_guard: typing.Optional[VideoGuard] = self.state[VIDEO_SECURITY]
        use_camera: bool = self.state[USE_CAMERA]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]

        if video_guard and (not self._video_camera.is_run or not use_camera or not security_is_enabled):
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

        if self.state[VIDEO_SECURITY]:
            self._disable_security()

        if self.state[VIDEO_RECORDING_IS_ENABLED]:
            self._stop_video_recording()

        if self.state[USE_CAMERA]:
            self._disable_camera()

    @synchronized_method
    def _enable_camera(self) -> None:
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

        self.messenger.send_message('The camera is on')

        if self.state[VIDEO_SECURITY]:
            self._enable_security()

    @synchronized_method
    def _disable_camera(self) -> None:
        self.state[USE_CAMERA] = False

        if self.state[SECURITY_IS_ENABLED]:
            self._disable_security()

        if self._video_stream:
            self._video_camera.stop()
            self._video_camera = None
            self._video_stream.stop()
            self._video_stream.stream.stream.release()
            self._video_stream = None

        self.messenger.send_message('The camera is off')

    @synchronized_method
    def _enable_security(self) -> None:
        if not self.state[USE_CAMERA]:
            return

        video_guard: VideoGuard = self.state[VIDEO_SECURITY]

        if video_guard:
            self.messenger.send_message('Video security is already enabled')
            return

        if self._video_stream:
            video_guard = VideoGuard(
                messenger=self.messenger,
                task_queue=self.task_queue,
                motion_detected_callback=events.motion_detected.send,
            )
            self.state[VIDEO_SECURITY] = video_guard
            video_guard.start()

        self.messenger.send_message('Video security is enabled')

    @synchronized_method
    def _disable_security(self) -> None:
        video_guard: VideoGuard = self.state[VIDEO_SECURITY]

        if video_guard:
            video_guard.stop()
            self.state[VIDEO_SECURITY] = None
            self.messenger.send_message('Video security is stopped')
        elif self.state[USE_CAMERA]:
            self.messenger.send_message('Video security is already disabled')

    @synchronized_method
    def _take_photo(self) -> None:
        if not self._can_use_camera():
            return

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

    @synchronized_method
    def _start_video_recording(self) -> None:
        if not self._can_use_camera():
            return

        self.state[VIDEO_RECORDING_IS_ENABLED] = True
        self.messenger.send_message('Start recording...')

    @synchronized_method
    def _stop_video_recording(self) -> None:
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
        video_guard: VideoGuard = self.state[VIDEO_SECURITY]

        if video_guard:
            try:
                video_guard.process_frame.send((frame, fps,))
            except Exception as e:
                logging.exception(e)
                self.messenger.send_message('Can\'t process the frame')
                self._disable_camera()

        if self.state[VIDEO_RECORDING_IS_ENABLED]:
            new_frame = np.copy(frame)
            add_timestamp_in_frame(new_frame)
            self._video_frames.append(new_frame)

    @synchronized_method
    @with_throttling(datetime.timedelta(seconds=5), count=1)
    @with_throttling(datetime.timedelta(minutes=1), count=10)
    def _process_motion_detection(self, *, source: str) -> None:
        if source == MotionTypeSources.SENSORS and self.state[USE_CAMERA]:
            self.task_queue.put(
                self._take_photo,
                priority=task_queue.TaskPriorities.HIGH,
            )
