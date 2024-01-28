import datetime
import typing

import cv2
import imutils
import imutils.video
import numpy as np


class MotionDetector:
    target_frame: typing.Optional[np.ndarray] = None
    marked_frame: typing.Optional[np.ndarray] = None
    is_occupied: bool = False
    _max_fps: int
    _min_area: int = 500
    _movement_ttl = datetime.timedelta(seconds=20)
    _last_changed_at: typing.Optional[datetime.datetime] = None
    _need_to_show_frames: bool

    def __init__(self, *, show_frames: bool, max_fps: int) -> None:
        self._need_to_show_frames = show_frames
        self._max_fps = max_fps

    def process_new_frame(self, frame: np.ndarray, *, fps: float) -> None:
        now = datetime.datetime.now()

        # Convert frame to grayscale, and blur it
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21,), 0)
        self.is_occupied = False

        # If the target frame is None, initialize it
        if self.target_frame is None or (now - self._last_changed_at) > self._movement_ttl:
            self.target_frame = gray
            self._last_changed_at = now
            return

        # Compute the absolute difference between the current frame and first frame
        frame_delta = cv2.absdiff(self.target_frame, gray)
        thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]

        # Dilate the thresholded image to fill in holes, then find contours
        # on thresholded image
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours = cv2.findContours(
            image=thresh,
            mode=cv2.RETR_EXTERNAL,
            method=cv2.CHAIN_APPROX_SIMPLE,
        )
        contours = imutils.grab_contours(contours)

        # Loop over the contours
        for contour in contours:
            # If the contour is too small, ignore it
            if cv2.contourArea(contour) < self._min_area:
                continue

            # Compute the bounding box for the contour, draw it on the frame,
            # and update the text
            x, y, w, h = cv2.boundingRect(contour)
            cv2.rectangle(frame, (x, y,), (x + w, y + h,), (0, 0, 255,), 1)
            self.is_occupied = True

        self._draw_result(
            frame=frame,
            thresh=thresh,
            frame_delta=frame_delta,
            fps=fps,
        )

        if self._need_to_show_frames:
            cv2.waitKey(1)

    def realese(self) -> None:
        if self._need_to_show_frames:
            cv2.destroyAllWindows()

    def _draw_result(
        self,
        *,
        frame: np.ndarray,
        thresh: np.ndarray,
        frame_delta: np.ndarray,
        fps: float,
    ) -> None:
        self.marked_frame = np.copy(frame)

        cv2.putText(
            img=self.marked_frame,
            text=f'Status: {"Occupied" if self.is_occupied else "Unoccupied"}',
            org=(10, 20,),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.5,
            color=(0, 0, 255,) if self.is_occupied else (0, 255, 0,),
            thickness=1,
        )
        current_fps = round(fps, 2)
        cv2.putText(
            img=self.marked_frame,
            text=f'FPS: {current_fps}',
            org=(10, 50,),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.5,
            color=(0, 0, 255,) if self._max_fps - current_fps > 0.1 else (0, 255, 0,),
            thickness=1,
        )
        cv2.putText(
            img=self.marked_frame,
            text=datetime.datetime.now().strftime('%d.%m.%Y, %H:%M:%S'),
            org=(10, frame.shape[0] - 10,),
            fontFace=cv2.FONT_HERSHEY_SIMPLEX,
            fontScale=0.5,
            color=(0, 0, 255,),
            thickness=1,
        )

        if self._need_to_show_frames:
            cv2.imshow('Security Feed', self.marked_frame)
            cv2.imshow('Thresh', thresh)
            cv2.imshow('Frame Delta', frame_delta)
