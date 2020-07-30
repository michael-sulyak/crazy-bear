import datetime
import threading
import typing

import cv2
import numpy as np
from imutils.video import VideoStream

from .motion_detector import MotionDetector
from ..common.storage import file_storage
from ..common.threads import ThreadPool
from ..messengers.base import BaseMessenger
from ... import config


class VideoGuard:
    video_stream: VideoStream
    motion_detector: MotionDetector
    messenger: BaseMessenger
    thread_pool: ThreadPool
    is_stopped: bool = True
    _main_thread: typing.Optional[threading.Thread] = None

    def __init__(self, messenger: BaseMessenger, video_stream: VideoStream, thread_pool: ThreadPool) -> None:
        self.video_stream = video_stream
        self.motion_detector = MotionDetector(self.video_stream, max_fps=config.FPS, imshow=config.IMSHOW)
        self.messenger = messenger
        self.thread_pool = thread_pool

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
                self._send_image_to_storage(frame=detector.marked_frame)
                self._send_video_to_storage(frames=frames)
                self._send_video_to_messenger(
                    frames=frames,
                    caption=f'Motion detected at {now.strftime("%Y-%m-%d, %H:%M:%S")}',
                )

            if detector.is_occupied and now - last_sent_photo > datetime.timedelta(seconds=5):
                self._send_image_to_storage(frame=detector.marked_frame)
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
                self._send_video_to_storage(frames)
                frames = []

            key = cv2.waitKey(1) & 0xFF

            if key == ord('q'):
                self.is_stopped = True

            if self.is_stopped:
                break

        self.motion_detector.realese()

    def _send_image_to_messenger(self, frame: np.array, caption: str) -> None:
        self.thread_pool.run(
            self.messenger.send_frame,
            args=(frame,),
            kwargs={'caption': caption},
        )

    def _send_image_to_storage(self, frame: np.array) -> None:
        now = datetime.datetime.now()

        self.thread_pool.run(file_storage.upload_frame, kwargs={
            'file_name': f'marked_images/{now.strftime("%Y-%m-%d %H:%M:%S.png")}',
            'frame': frame,
        })

    def _send_video_to_storage(self, frames: np.array) -> None:
        now = datetime.datetime.now()

        self.thread_pool.run(file_storage.upload_frames_as_video, kwargs={
            'file_name': f'videos/{now.strftime("%Y-%m-%d %H:%M:%S.avi")}',
            'frames': frames,
            'fps': config.FPS,
        })

    def _send_video_to_messenger(self, frames: np.array, caption: str) -> None:
        self.thread_pool.run(
            self.messenger.send_frames_as_video,
            args=(frames,),
            kwargs={
                'fps': config.FPS,
                'caption': caption,
            },
        )
