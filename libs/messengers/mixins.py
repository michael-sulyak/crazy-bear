import abc
import io
import os
import tempfile
import typing

import cv2
import numpy as np


class BaseCVMixin(abc.ABC):
    @abc.abstractmethod
    def send_frame(self, frame: np.ndarray, caption: str | None = None) -> None:
        pass

    @abc.abstractmethod
    def send_frames_as_video(
        self, frames: list[np.ndarray], *, fps: int, caption: str | None = None,
    ) -> None:
        pass


class CVMixin(BaseCVMixin):
    @abc.abstractmethod
    def send_image(self, image: typing.Any, *, caption: str | None = None) -> None:
        pass

    @abc.abstractmethod
    def send_video(self, video: typing.BinaryIO, *, caption: str | None = None) -> None:
        pass

    def send_frame(self, frame: np.ndarray, caption: str | None = None) -> None:
        is_success, buffer = cv2.imencode('.jpg', frame)

        if not is_success:
            raise RuntimeError('Cannot encode camera frame as JPEG')

        with io.BytesIO(buffer.tobytes()) as image:
            self.send_image(image, caption=caption)

    def send_frames_as_video(
        self, frames: list[np.ndarray], *, fps: int, caption: str | None = None,
    ) -> None:
        if not frames:
            return

        if fps <= 0:
            raise ValueError('Video FPS must be positive')

        height, width = frames[0].shape[:2]
        size = (
            width,
            height,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            filename = os.path.join(temp_dir, 'video.mp4')

            video_writer = cv2.VideoWriter(
                filename=filename,
                fourcc=cv2.VideoWriter_fourcc(*'mp4v'),
                fps=fps,
                frameSize=size,
            )

            try:
                if not video_writer.isOpened():
                    raise RuntimeError('Cannot open MP4 video encoder')

                for frame in frames:
                    video_writer.write(frame)
            finally:
                video_writer.release()

            with open(filename, 'rb') as file:
                self.send_video(file, caption=caption)
