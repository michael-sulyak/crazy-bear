import datetime
import unittest

from .. import utils


class UtilsTestCase(unittest.TestCase):
    def test_is_sleep_hours(self):
        timestamp_tpl = dict(year=2020, month=1, day=1)

        with utils.mock_var(utils.config, 'SLEEP_HOURS', (0, 6,)):
            self.assertTrue(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=1)))
            self.assertTrue(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=5)))
            self.assertFalse(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=7)))
            self.assertFalse(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=23)))

        with utils.mock_var(utils.config, 'SLEEP_HOURS', (20, 3,)):
            self.assertTrue(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=21)))
            self.assertTrue(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=23)))
            self.assertTrue(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=2)))
            self.assertFalse(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=4)))
            self.assertFalse(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=17)))
            self.assertFalse(utils.is_sleep_hours(datetime.datetime(**timestamp_tpl, hour=19)))
