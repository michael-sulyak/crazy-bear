from unittest.mock import Mock

import cv2

from .... import config
from ..video_guard import VideoGuard


def test_video_guard():
    messenger = Mock()
    task_queue = Mock()

    video_guard = VideoGuard(
        messenger=messenger,
        task_queue=task_queue,
    )
    video_guard.start()
    video_guard.process_frame.send(
        (
            cv2.imread(str(config.APPS_DIR / 'guard/tests/resources/frame_1.png')),
            1,
        ),
    )
