import datetime
import threading
import typing

import cv2
import numpy as np
from imutils.video import VideoStream

from .motion_detector import MotionDetector
from ..common.storage import file_storage
from ..common.threads import TaskQueue
from ..messengers.base import BaseMessenger
from ... import config


class VideoGuard:
    video_stream: VideoStream
    motion_detector: MotionDetector
    messenger: BaseMessenger
    task_queue: TaskQueue
    is_stopped: bool = True
    motion_detected_callback: typing.Optional[typing.Callable] = None
    _main_thread: typing.Optional[threading.Thread] = None

    def __init__(self, *,
                 messenger: BaseMessenger,
                 video_stream: VideoStream,
                 task_queue: TaskQueue,
                 motion_detected_callback: typing.Optional[typing.Callable] = None) -> None:
        self.video_stream = video_stream
        self.motion_detector = MotionDetector(video_stream=self.video_stream, max_fps=config.FPS, imshow=config.IMSHOW)
        self.messenger = messenger
        self.task_queue = task_queue
        self.motion_detected_callback = motion_detected_callback

    def start(self) -> None:
        self.stop()
        self.is_stopped = False

        self._main_thread = threading.Thread(target=self.run)
        self._main_thread.start()

    def stop(self) -> None:
        self.is_stopped = True

        if self._main_thread is not None:
            self._main_thread.join()

    def run(self) -> None:
        last_is_occupied = False
        frames = []
        send_video = False
        min_frames_for_send_video = None
        last_sent_photo = None

        for detector in self.motion_detector.run():
            if detector.marked_frame is None:
                if frames:
                    frames = []

                continue

            now = datetime.datetime.now()

            if detector.is_occupied and not last_is_occupied:
                last_is_occupied = True
                last_sent_photo = now
                frames = frames[-config.FPS * 20:]
                self._send_image_to_messenger(
                    frame=detector.marked_frame,
                    caption=f'Motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                )
                self._save_image(frame=detector.marked_frame)
                self._save_video(frames=frames)
                self._send_video_to_messenger(
                    frames=frames,
                    caption=f'Motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                )

                if self.motion_detected_callback:
                    self.motion_detected_callback()

            if detector.is_occupied and now - last_sent_photo > datetime.timedelta(seconds=5):
                self._save_image(frame=detector.marked_frame)
                self._send_image_to_messenger(
                    frame=detector.marked_frame,
                    caption=f'Long motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                )
                last_sent_photo = now

            if not detector.is_occupied and last_is_occupied:
                last_is_occupied = False
                send_video = True
                min_frames_for_send_video = len(frames) + config.FPS * 5

            frames.append(detector.marked_frame)

            if send_video and len(frames) >= min_frames_for_send_video:
                send_video = False
                min_frames_for_send_video = None
                self._save_video(frames)
                frames = []

            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                self.is_stopped = True

            if self.is_stopped:
                break

        self.motion_detector.realese()

    def _send_image_to_messenger(self, frame: np.array, caption: str) -> None:
        self.task_queue.push(
            self.messenger.send_frame,
            args=(frame,),
            kwargs={'caption': caption},
            is_high=True,
        )

    def _send_video_to_messenger(self, frames: typing.List[np.array], caption: str) -> None:
        self.task_queue.push(
            self.messenger.send_frames_as_video,
            args=(frames,),
            kwargs={
                'fps': config.FPS,
                'caption': caption,
            },
            is_high=True,
        )

    def _save_image(self, frame: np.array) -> None:
        now = datetime.datetime.now()

        self.task_queue.push(
            file_storage.upload_frame,
            kwargs={
                'file_name': f'marked_images/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
                'frame': frame,
            },
        )

    def _save_video(self, frames: np.array) -> None:
        now = datetime.datetime.now()

        self.task_queue.push(
            file_storage.upload_frames_as_video,
            kwargs={
                'file_name': f'videos/{now.strftime("%Y-%m-%d %H:%M:%S.avi")}',
                'frames': frames,
                'fps': config.FPS,
            },
        )
