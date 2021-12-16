import unittest
import datetime
from unittest import mock

from ..utils import is_sleep_hours


class UtilsTestCase(unittest.TestCase):
    def test_is_sleep_hours(self):
        timestamp_tpl = dict(year=2020, month=1, day=1)

        with mock.patch('project.config.SLEEP_HOURS', [0, 6]):
            self.assertTrue(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=1)))
            self.assertTrue(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=5)))
            self.assertFalse(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=7)))
            self.assertFalse(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=23)))

        with mock.patch('project.config.SLEEP_HOURS', [20, 3]):
            self.assertTrue(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=21)))
            self.assertTrue(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=23)))
            self.assertTrue(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=2)))
            self.assertFalse(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=4)))
            self.assertFalse(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=17)))
            self.assertFalse(is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=19)))
