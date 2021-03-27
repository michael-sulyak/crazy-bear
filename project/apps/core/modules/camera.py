import datetime
import typing

import schedule
from imutils.video import VideoStream

from ..base import BaseModule, Command
from ...common.constants import OFF, ON
from ...common.storage import file_storage
from ... import task_queue
from ...common.utils import camera_is_available, synchronized
from ...core import events
from ...core.constants import CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA, VIDEO_SECURITY
from ...guard.video_guard import VideoGuard
from ...messengers.constants import BotCommands
from .... import config


__all__ = (
    'Camera',
)


class Camera(BaseModule):
    initial_state = {
        VIDEO_SECURITY: None,
        USE_CAMERA: False,
        SECURITY_IS_ENABLED: False,
        CURRENT_FPS: None,
    }
    _video_stream: typing.Optional[VideoStream] = None
    _camera_is_available: bool = True

    def init_schedule(self, scheduler: schedule.Scheduler) -> tuple:
        return (
            scheduler.every(10).seconds.do(
                self.unique_task_queue.push,
                self._save_photo,
                priority=task_queue.TaskPriorities.MEDIUM,
            ),
            scheduler.every(30).seconds.do(
                self.unique_task_queue.push,
                self._check_video_stream,
                priority=task_queue.TaskPriorities.LOW,
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CAMERA:
            if command.first_arg == ON:
                self._camera_is_available = True
                self._enable_camera()
            elif command.first_arg == OFF:
                self._disable_camera()
            elif command.first_arg == 'photo':
                self._take_photo()
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

    @synchronized
    def tick(self) -> None:
        video_guard: typing.Optional[VideoGuard] = self.state[VIDEO_SECURITY]
        use_camera: bool = self.state[USE_CAMERA]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]

        if video_guard and (video_guard.is_stopped or not use_camera or not security_is_enabled):
            self._disable_security()
            video_guard = None

        if not video_guard and use_camera and security_is_enabled and self._camera_is_available:
            self._enable_security()
            video_guard = self.state[VIDEO_SECURITY]

        if video_guard:
            self.state[CURRENT_FPS] = video_guard.motion_detector.fps_tracker.fps()
        else:
            self.state[CURRENT_FPS] = None

    @synchronized
    def disable(self) -> None:
        super().disable()
        self._disable_camera()

    @synchronized
    def _enable_camera(self) -> None:
        if not camera_is_available(config.VIDEO_SRC):
            self._camera_is_available = False
            self.messenger.send_message('Camera is not available')
            return

        self.state[USE_CAMERA] = True

        if not self._video_stream:
            self._video_stream = VideoStream(src=config.VIDEO_SRC, resolution=config.IMAGE_RESOLUTION)
            self._video_stream.start()

        self.messenger.send_message('The camera is on')

    @synchronized
    def _disable_camera(self) -> None:
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        self.state[USE_CAMERA] = False

        if security_is_enabled:
            self._disable_security()

        if self._video_stream:
            self._video_stream.stop()
            self._video_stream.stream.stream.release()

        self.messenger.send_message('The camera is off')

    @synchronized
    def _enable_security(self) -> None:
        if not self.state[USE_CAMERA]:
            return

        video_guard: VideoGuard = self.state[VIDEO_SECURITY]

        if video_guard:
            self.messenger.send_message('Video security is already enabled')
            return

        if not self._video_stream:
            self._enable_camera()

        if self._video_stream:
            video_guard = VideoGuard(
                messenger=self.messenger,
                video_stream=self._video_stream,
                task_queue=self.task_queue,
                motion_detected_callback=events.motion_detected,
            )
            self.state[VIDEO_SECURITY] = video_guard
            video_guard.start()

        self.messenger.send_message('Video security is enabled')

    @synchronized
    def _disable_security(self) -> None:
        video_guard: VideoGuard = self.state[VIDEO_SECURITY]

        if video_guard:
            video_guard.stop()
            self.state[VIDEO_SECURITY] = None
            self.messenger.send_message('Video security is stopped')
        elif self.state[USE_CAMERA]:
            self.messenger.send_message('Video security is already disabled')

    @synchronized
    def _take_photo(self) -> None:
        if not self._can_use_camera():
            return

        now = datetime.datetime.now()
        frame = self._video_stream.read()

        if frame is not None:
            self.messenger.send_frame(frame, caption=f'Captured at {now.strftime("%d.%m.%Y, %H:%M:%S")}')
            self.task_queue.put(
                file_storage.upload_frame,
                kwargs={
                    'file_name': f'saved_photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                    'frame': frame,
                },
                priority=task_queue.TaskPriorities.MEDIUM,
                retry_policy=task_queue.retry_policy_for_connection_error,
            )

    def _can_use_camera(self) -> bool:
        use_camera: bool = self.state[USE_CAMERA]

        if use_camera:
            return True

        self.messenger.send_message('Camera is not enabled')
        return False

    @synchronized
    def _save_photo(self) -> None:
        if not self.state[USE_CAMERA] or not self._video_stream:
            return

        now = datetime.datetime.now()

        file_storage.upload_frame(
            file_name=f'photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
            frame=self._video_stream.read(),
        )

    @synchronized
    def _check_video_stream(self) -> None:
        if not self._video_stream:
            return

        frame = self._video_stream.read()

        if frame is None:
            self._camera_is_available = False
            self.messenger.send_message('Camera is not available')
            self._run_command(BotCommands.CAMERA, OFF)
