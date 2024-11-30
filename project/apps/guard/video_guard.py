import datetime
import typing

import numpy as np

from libs import task_queue as tq
from libs.image_processing.motion_detector import MotionDetector
from libs.messengers.base import BaseMessenger

from ... import config
from ..common.storage import file_storage


class VideoGuard:
    motion_detector: MotionDetector
    messenger: BaseMessenger
    task_queue: tq.BaseTaskQueue
    motion_detected_callback: typing.Callable | None = None
    process_frame: typing.Generator | None = None

    def __init__(
        self,
        *,
        messenger: BaseMessenger,
        task_queue: tq.BaseTaskQueue,
        motion_detected_callback: typing.Callable | None = None,
    ) -> None:
        self.motion_detector = MotionDetector(show_frames=config.IMSHOW, max_fps=config.FPS)
        self.messenger = messenger
        self.task_queue = task_queue
        self.motion_detected_callback = motion_detected_callback

    def start(self) -> None:
        self.process_frame = self.process_frames()
        next(self.process_frame)

    def stop(self) -> None:
        assert self.process_frame is not None

        self.process_frame.close()
        self.motion_detector.realese()

    def process_frames(self) -> typing.Generator[None, tuple, None]:
        last_is_occupied = False
        frames: list[np.ndarray] = []
        send_video = False
        min_frames_for_send_video = None
        last_sent_photo = None

        while True:
            try:
                frame, fps = yield
            except GeneratorExit:
                break

            self.motion_detector.process_new_frame(frame, fps=fps)

            if self.motion_detector.marked_frame is None:
                if frames:
                    frames = []

                continue

            now = datetime.datetime.now()

            if self.motion_detector.is_occupied:
                if not last_is_occupied:
                    last_is_occupied = True
                    last_sent_photo = now
                    frames = frames[-config.FPS * 20 :]
                    self._send_image_to_messenger(
                        frame=self.motion_detector.marked_frame,
                        caption=f'Motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                    )
                    self._save_image(frame=self.motion_detector.marked_frame)
                    self._save_video(frames=frames)
                    self._send_video_to_messenger(
                        frames=frames,
                        caption=f'Motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                    )

                    if self.motion_detected_callback:
                        self.motion_detected_callback()

                assert last_sent_photo is not None

                if now - last_sent_photo > datetime.timedelta(seconds=5):
                    self._save_image(frame=self.motion_detector.marked_frame)
                    self._send_image_to_messenger(
                        frame=self.motion_detector.marked_frame,
                        caption=f'Long motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                    )
                    last_sent_photo = now

            if not self.motion_detector.is_occupied and last_is_occupied:
                last_is_occupied = False
                send_video = True
                min_frames_for_send_video = len(frames) + config.FPS * 5

            frames.append(self.motion_detector.marked_frame)

            if len(frames) > config.FPS * 60 * 10:
                if self.motion_detector.is_occupied:
                    send_video = True
                    min_frames_for_send_video = 0
                else:
                    frames = frames[-self.motion_detector.is_occupied * 60 * 5 :]

            if send_video:
                assert min_frames_for_send_video is not None

                if len(frames) >= min_frames_for_send_video:
                    send_video = False
                    min_frames_for_send_video = None
                    self._save_video(frames)
                    frames = []

    def _send_image_to_messenger(self, frame: np.ndarray, caption: str) -> None:
        self.task_queue.put(
            self.messenger.send_frame,
            args=(frame,),
            kwargs={'caption': caption},
            priority=tq.TaskPriorities.HIGH,
        )

    def _send_video_to_messenger(self, frames: list[np.ndarray], caption: str) -> None:
        self.task_queue.put(
            self.messenger.send_frames_as_video,
            args=(frames,),
            kwargs={
                'fps': config.FPS,
                'caption': caption,
            },
            priority=tq.TaskPriorities.HIGH,
        )

    def _save_image(self, frame: np.ndarray) -> None:
        now = datetime.datetime.now()

        self.task_queue.put(
            file_storage.upload_frame,
            kwargs={
                'file_name': f'marked_images/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                'frame': frame,
            },
            priority=tq.TaskPriorities.MEDIUM,
        )

    def _save_video(self, frames: list[np.ndarray]) -> None:
        now = datetime.datetime.now()

        self.task_queue.put(
            file_storage.upload_frames_as_video,
            kwargs={
                'file_name': f'videos/{now.strftime("%Y-%m-%d %H:%M:%S.avi")}',
                'frames': frames,
                'fps': config.FPS,
            },
            priority=tq.TaskPriorities.MEDIUM,
        )
