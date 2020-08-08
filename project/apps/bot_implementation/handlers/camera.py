import datetime
import typing

from imutils.video import VideoStream

from project import config
from .. import constants
from ...common.constants import OFF, ON
from ...common.storage import file_storage
from ...common.threads import ThreadPool
from ...guard.constants import CURRENT_FPS, SECURITY_IS_ENABLED, USE_CAMERA, VIDEO_GUARD, VIDEO_STREAM
from ...guard.video_guard import VideoGuard
from ...messengers.base import BaseBotCommandHandler, Command

__all__ = (
    'Camera',
)

from ...messengers.constants import THREAD_POOL


class Camera(BaseBotCommandHandler):
    support_commands = {
        constants.BotCommands.CAMERA,
        constants.BotCommands.SECURITY,
    }
    _last_save_photo_at: typing.Optional[datetime.datetime] = None

    def init_state(self) -> None:
        self.state.create_many(**{
            VIDEO_GUARD: None,
            VIDEO_STREAM: None,
            USE_CAMERA: False,
            SECURITY_IS_ENABLED: False,
            CURRENT_FPS: None,
        })

    def process_command(self, command: Command) -> None:
        if command.name == constants.BotCommands.CAMERA:
            if command.first_arg == ON:
                self._enable_camera()
            elif command.first_arg == OFF:
                self._disable_camera()
            elif command.first_arg == 'photo':
                self._take_picture()
        elif command.name == constants.BotCommands.SECURITY:
            if command.first_arg == ON:
                self._enable_security()
            elif command.first_arg == OFF:
                self._disable_security()

    def update(self) -> None:
        video_guard: typing.Optional[VideoGuard] = self.state[VIDEO_GUARD]
        use_camera: bool = self.state[USE_CAMERA]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        video_stream: VideoStream = self.state[VIDEO_STREAM]
        thread_pool: ThreadPool = self.state[THREAD_POOL]
        now = datetime.datetime.now()

        if video_guard and (video_guard.is_stopped or not use_camera or not security_is_enabled):
            self._disable_security()
            video_guard = None

        if not video_guard and use_camera and security_is_enabled:
            self._enable_security()
            video_guard = self.state[VIDEO_GUARD]

        self.state[CURRENT_FPS] = (
            video_guard.motion_detector.fps_tracker.fps()
            if video_guard else None
        )

        if use_camera and (not self._last_save_photo_at or now - self._last_save_photo_at > datetime.timedelta(seconds=10)):
            self._last_save_photo_at = now

            thread_pool.run(file_storage.upload_frame, kwargs={
                'file_name': f'photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                'frame': video_stream.read(),
            })

    def clear(self) -> None:
        self._disable_camera()

    def _enable_camera(self) -> None:
        video_stream: VideoStream = self.state[VIDEO_STREAM]
        self.state[USE_CAMERA] = True

        if not video_stream:
            video_stream = VideoStream(src=config.VIDEO_SRC, resolution=config.IMAGE_RESOLUTION)
            self.state[VIDEO_STREAM] = video_stream
            video_stream.start()

        self.messenger.send_message('The camera is on')

    def _disable_camera(self) -> None:
        video_stream: VideoStream = self.state[VIDEO_STREAM]
        security_is_enabled: bool = self.state[SECURITY_IS_ENABLED]
        self.state[USE_CAMERA] = False

        if security_is_enabled:
            self._disable_security()

        if video_stream:
            video_stream.stop()
            video_stream.stream.stream.release()
            self.state.clear(VIDEO_STREAM)

        self.messenger.send_message('The camera is off')

    def _enable_security(self) -> None:
        video_stream: VideoStream = self.state[VIDEO_STREAM]
        video_guard: VideoGuard = self.state[VIDEO_GUARD]
        thread_pool: ThreadPool = self.state[THREAD_POOL]
        self.state[SECURITY_IS_ENABLED] = True

        if not self._can_use_camera():
            return

        if video_guard:
            self.messenger.send_message('VideoGuard is already enabled')
            return

        if not video_stream:
            self._enable_camera()
            video_stream = self.state[VIDEO_STREAM]

        if video_stream:
            video_guard = VideoGuard(
                messenger=self.messenger,
                video_stream=video_stream,
                thread_pool=thread_pool,
            )
            self.state[VIDEO_GUARD] = video_guard
            video_guard.start()

        self.messenger.send_message('Video security is enabled')

    def _disable_security(self) -> None:
        video_guard: VideoGuard = self.state[VIDEO_GUARD]
        self.state[SECURITY_IS_ENABLED] = False

        if video_guard:
            video_guard.stop()
            self.state.clear(VIDEO_GUARD)
            self.messenger.send_message('Video security is stopped')
        else:
            self.messenger.send_message('Video security is already disabled')

    def _take_picture(self) -> None:
        video_stream: VideoStream = self.state[VIDEO_STREAM]
        thread_pool: ThreadPool = self.state[THREAD_POOL]

        if not self._can_use_camera():
            return

        now = datetime.datetime.now()
        frame = video_stream.read()

        if frame is not None:
            self.messenger.send_frame(frame, caption=f'Captured at {now.strftime("%d.%m.%Y, %H:%M:%S")}')
            thread_pool.run(file_storage.upload_frame, kwargs={
                'file_name': f'saved_photos/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                'frame': video_stream.read(),
            })

    def _can_use_camera(self) -> bool:
        use_camera: bool = self.state[USE_CAMERA]

        if use_camera:
            return True
        else:
            self.messenger.send_message('Camera is not enabled')
            return False
