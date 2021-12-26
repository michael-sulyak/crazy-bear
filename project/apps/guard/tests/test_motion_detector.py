import cv2

from ..motion_detector import MotionDetector
from .... import config


def test_motion_detector():
    motion_detector = MotionDetector(
        max_fps=999999999999999,
        show_frames=False,
    )

    frame = cv2.imread(str(config.APPS_DIR / 'guard/tests/resources/frame_1.png'))
    motion_detector.process_new_frame(frame, fps=1)
    assert motion_detector.is_occupied is False

    frame = cv2.imread(str(config.APPS_DIR / 'guard/tests/resources/frame_2.png'))
    motion_detector.process_new_frame(frame, fps=1)
    assert motion_detector.is_occupied is True
