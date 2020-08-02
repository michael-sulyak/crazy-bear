import unittest
from datetime import timedelta
from time import sleep
from unittest.mock import Mock

from ..threads import ThreadPool


class TestThreadPool(unittest.TestCase):
    def test_creating(self):
        ThreadPool(timedelta_for_part_sync=timedelta(seconds=1))

    def test_run(self):
        mock = Mock()

        thread_manager = ThreadPool(timedelta_for_part_sync=timedelta(seconds=1))
        thread_manager.run(mock.method)
        thread_manager.sync()

        mock.method.assert_called_once()

    def test_run_with_args_and_kwargs(self):
        mock = Mock()

        thread_manager = ThreadPool(timedelta_for_part_sync=timedelta(seconds=1))
        thread_manager.run(mock.method, args=(1, 2, 3,), kwargs={'bar': 'values'})
        thread_manager.sync()

        mock.method.assert_called_once_with(1, 2, 3, bar='values')

    def test_part_sync(self):
        mock = Mock()

        thread_manager = ThreadPool(timedelta_for_part_sync=timedelta(milliseconds=1))
        thread_manager.run(mock.method)
        self.assertGreater(len(thread_manager._threads), 0)
        sleep(0.01)
        thread_manager.part_sync()
        self.assertEqual(len(thread_manager._threads), 0)

        mock.method.assert_called_once_with()
