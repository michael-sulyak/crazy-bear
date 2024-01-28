import abc
import cv2
import io
import numpy as np
import os
import tempfile
import typing

import telegram


class BaseCVMixin(abc.ABC):
    @abc.abstractmethod
    def send_frame(self, frame: np.ndarray, caption: typing.Optional[str] = None) -> None:
        pass

    @abc.abstractmethod
    def send_frames_as_video(self,
                             frames: typing.List[np.ndarray], *,
                             fps: int,
                             caption: typing.Optional[str] = None) -> None:
        pass


class CVMixin(BaseCVMixin):
    _bot: telegram.Bot
    chat_id: int

    def send_frame(self, frame: np.ndarray, caption: typing.Optional[str] = None) -> None:
        is_success, buffer = cv2.imencode('.jpg', frame)
        io_buf = io.BytesIO(buffer)
        self._bot.send_photo(
            self.chat_id,
            photo=io_buf,
            caption=caption,
        )

    def send_frames_as_video(self,
                             frames: typing.List[np.ndarray], *,
                             fps: int,
                             caption: typing.Optional[str] = None) -> None:
        if not frames:
            return

        height, width, layers = frames[0].shape
        size = (width, height,)

        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, 'video.avi')

            video_writer = cv2.VideoWriter(
                filename=filename,
                fourcc=cv2.VideoWriter_fourcc(*'DIVX'),
                fps=fps,
                frameSize=size,
            )

            for frame in frames:
                video_writer.write(frame)

            video_writer.release()

            with open(filename, 'rb') as file:
                self._bot.send_video(
                    self.chat_id,
                    video=file,
                    caption=caption,
                )
