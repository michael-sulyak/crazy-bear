import unittest
from datetime import timedelta

from libs.camera.fps import FPSTracker


class TestFPSTracker(unittest.TestCase):
    def test_creating(self):
        FPSTracker()

    def test_start(self):
        fps_manager = FPSTracker()
        fps_manager.start()
        fps_manager.stop()

        self.assertEqual(fps_manager.fps(), 0)

    def test_fps(self):
        fps_manager = FPSTracker()
        fps_manager.start()
        fps_manager.update()
        fps_manager.update()
        fps_manager.update()
        fps_manager.stop()

        fps_manager._finished_at = fps_manager._started_at + timedelta(seconds=1)  # noqa: SLF001

        self.assertEqual(fps_manager.fps(), 3)

    def test_duplicate(self):
        fps_manager = FPSTracker()
        fps_manager.start()
        fps_manager.update()
        fps_manager._started_at = fps_manager._started_at - fps_manager._timedelta_for_duplicate  # noqa: SLF001
        fps_manager.update()
        fps_manager.update()

        self.assertEqual(2, fps_manager._new_num_frames)  # noqa: SLF001

    def test_reset(self):
        fps_manager = FPSTracker()
        fps_manager.start()
        fps_manager.update()
        fps_manager._started_at = fps_manager._started_at - fps_manager._timedelta_for_duplicate  # noqa: SLF001
        fps_manager.update()
        fps_manager.update()
        fps_manager._started_at = fps_manager._started_at - fps_manager._timedelta_for_reset  # noqa: SLF001
        fps_manager.update()

        self.assertEqual(3, fps_manager._num_frames)  # noqa: SLF001
