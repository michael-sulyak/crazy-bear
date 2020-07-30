from unittest.mock import Mock

import cv2

from ..motion_detector import MotionDetector
from .... import config


def test_motion_detector():
    video_stream = Mock()

    motion_detector = MotionDetector(
        video_stream=video_stream,
        max_fps=999999999999999,
        imshow=False,
    )

    detector_iter = motion_detector.run()

    video_stream.read.return_value = cv2.imread(str(config.APPS_DIR / 'guard/tests/resources/frame_1.png'))
    next(detector_iter)
    assert video_stream.read.call_count == 1
    assert motion_detector.is_occupied is False

    video_stream.read.return_value = cv2.imread(str(config.APPS_DIR / 'guard/tests/resources/frame_2.png'))
    next(detector_iter)
    assert video_stream.read.call_count == 2
    assert motion_detector.is_occupied is True
