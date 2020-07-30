from unittest.mock import Mock

import cv2

from ..video_guard import VideoGuard
from .... import config


def test_video_guard():
    messenger = Mock()
    video_stream = Mock()
    video_stream.read.return_value = cv2.imread(str(config.APPS_DIR / 'guard/tests/resources/frame_1.png'))
    thread_pool = Mock()

    video_guard = VideoGuard(
        messenger=messenger,
        video_stream=video_stream,
        thread_pool=thread_pool,
    )

    video_guard.is_stopped = True
    video_guard.run()
