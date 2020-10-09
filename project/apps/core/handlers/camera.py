import datetime
import typing

import schedule
from imutils.video import VideoStream

from ..base import BaseCommandHandler, Command
from ...common.constants import OFF, ON
from ...common.storage import file_storage
from ...common.utils import camera_is_available
from ...core import events
from ...core.constants import CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA, VIDEO_SECURITY
from ...guard.video_guard import VideoGuard
from ...messengers.constants import BotCommands
from .... import config


__all__ = (
    'Camera',
)


class Camera(BaseCommandHandler):
    initial_state = {
        VIDEO_SECURITY: None,
        USE_CAMERA: False,
        SECURITY_IS_ENABLED: False,
        CURRENT_FPS: None,
    }
    _video_stream: typing.Optional[VideoStream] = None
    _camera_is_available: bool = True

    def init_schedule(self, scheduler: schedule.Scheduler) -> None:
        scheduler.every(10).seconds.do(self._save_photo)
        scheduler.every(1).minutes.do(self._check_video_stream)

    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.CAMERA:
            if command.first_arg == ON:
                self._camera_is_available = True
                self._enable_camera()
            elif command.first_arg == OFF:
                self._disable_camera()
            elif command.first_arg == 'photo':
                self._take_picture()
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

    def update(self) -> None:
        video_guard: typing.Optional[VideoGuard] = self.state[VIDEO_SECURITY]
        use_camera: bool = self.state[USE_CAMERA]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]

        if video_guard and (video_guard.is_stopped or not use_camera or not security_is_enabled):
            self._disable_security()
            video_guard = None

        if not video_guard and use_camera and security_is_enabled and self._camera_is_available:
            self._enable_security()
            video_guard = self.state[VIDEO_SECURITY]

        self.state[CURRENT_FPS] = (
            video_guard.motion_detector.fps_tracker.fps()
            if video_guard else None
        )

    def clear(self) -> None:
        self._disable_camera()

    def _enable_camera(self) -> None:
        if not camera_is_available(config.VIDEO_SRC):
            self._camera_is_available = True
            self.messenger.send_message('Camera is not available')
            return

        self.state[USE_CAMERA] = True

        if not self._video_stream:
            self._video_stream = VideoStream(src=config.VIDEO_SRC, resolution=config.IMAGE_RESOLUTION)
            self._video_stream.start()

        self.messenger.send_message('The camera is on')

    def _disable_camera(self) -> None:
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        self.state[USE_CAMERA] = False

        if security_is_enabled:
            self._disable_security()

        if self._video_stream:
            self._video_stream.stop()
            self._video_stream.stream.stream.release()

        self.messenger.send_message('The camera is off')

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
                thread_pool=self.thread_pool,
                motion_detected_callback=events.motion_detected,
            )
            self.state[VIDEO_SECURITY] = video_guard
            video_guard.start()

        self.messenger.send_message('Video security is enabled')

    def _disable_security(self) -> None:
        video_guard: VideoGuard = self.state[VIDEO_SECURITY]

        if video_guard:
            video_guard.stop()
            self.state[VIDEO_SECURITY] = None
            self.messenger.send_message('Video security is stopped')
        elif self.state[USE_CAMERA]:
            self.messenger.send_message('Video security is already disabled')

    def _take_picture(self) -> None:
        if not self._can_use_camera():
            return

        now = datetime.datetime.now()
        frame = self._video_stream.read()

        if frame is not None:
            self.messenger.send_frame(frame, caption=f'Captured at {now.strftime("%d.%m.%Y, %H:%M:%S")}')
            self.thread_pool.run(file_storage.upload_frame, kwargs={
                'file_name': f'saved_photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                'frame': self._video_stream.read(),
            })

    def _can_use_camera(self) -> bool:
        use_camera: bool = self.state[USE_CAMERA]

        if use_camera:
            return True

        self.messenger.send_message('Camera is not enabled')
        return False

    def _save_photo(self) -> None:
        if not self.state[USE_CAMERA]:
            return

        now = datetime.datetime.now()

        self.thread_pool.run(file_storage.upload_frame, kwargs={
            'file_name': f'photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
            'frame': self._video_stream.read(),
        })

    def _check_video_stream(self):
        if not self._video_stream or not self._camera_is_available:
            return

        frame = self._video_stream.read()

        if frame is None:
            self._camera_is_available = False
            self.messenger.send_message('Camera is not available')
            self._run_command(BotCommands.CAMERA, OFF)
