import threading
import typing

from imutils.video import VideoStream

from .fps import FPSTracker


class VideoCamera:
    _is_run: threading.Event
    _worker: typing.Optional[threading.Thread] = None
    _video_stream: VideoStream
    _callback: typing.Callable
    _fps_tracker = FPSTracker

    def __init__(self, *,
                 video_stream: VideoStream,
                 callback: typing.Callable,
                 max_fps: int) -> None:
        self._fps_tracker = FPSTracker()
        self._video_stream = video_stream
        self._callback = callback
        self._is_run = threading.Event()
        self._max_fps = max_fps

    @property
    def fps(self) -> float:
        return self._fps_tracker.fps()

    @property
    def is_run(self) -> bool:
        return self._is_run.is_set()

    def start(self) -> None:
        self.stop()
        self._is_run.set()

        self._worker = threading.Thread(target=self._process_stream)
        self._worker.start()

    def stop(self) -> None:
        if not self._is_run.is_set():
            return

        self._is_run.clear()

        if self._worker is not None:
            self._worker.join()

    def _process_stream(self) -> typing.NoReturn:
        self._fps_tracker.start()

        while self._is_run.is_set():
            frame = self._video_stream.read()

            if frame is None:
                self._is_run.clear()
                break

            self._callback(frame=frame, fps=self._fps_tracker.fps())

            self._fps_tracker.update(fps=self._max_fps)
