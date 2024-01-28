import datetime

import cv2
import numpy as np


def add_timestamp_in_frame(frame: np.ndarray) -> None:
    cv2.putText(
        img=frame,
        text=datetime.datetime.now().strftime('%d.%m.%Y, %H:%M:%S'),
        org=(10, frame.shape[0] - 10,),
        fontFace=cv2.FONT_HERSHEY_SIMPLEX,
        fontScale=0.5,
        color=(0, 0, 255,),
        thickness=1,
    )
