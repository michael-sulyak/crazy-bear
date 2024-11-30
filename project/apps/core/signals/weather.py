import datetime

from libs.casual_utils.time import get_current_time

from ...common import utils
from ...signals.models import Signal
from .. import constants
from .base import BaseSignalHandler, IntervalNotificationCheckMixin
from .utils import get_default_signal_compress_datetime_range


class WeatherHandler(IntervalNotificationCheckMixin, BaseSignalHandler):
    task_interval = datetime.timedelta(minutes=10)  # Note: See recommendation from https://openweathermap.org/faq

    def process(self) -> None:
        weather = utils.get_weather()
        now = get_current_time()

        Signal.bulk_add(
            (
                Signal(type=constants.WEATHER_TEMPERATURE, value=weather['main']['temp'], received_at=now),
                Signal(type=constants.WEATHER_HUMIDITY, value=weather['main']['humidity'], received_at=now),
            ),
        )

    def compress(self) -> None:
        signal_types = (
            constants.WEATHER_TEMPERATURE,
            constants.WEATHER_HUMIDITY,
        )
        Signal.clear(signal_types)

        datetime_range = get_default_signal_compress_datetime_range()

        for signal_type in signal_types:
            Signal.compress_by_time(
                signal_type,
                datetime_range=datetime_range,
            )

            Signal.compress(
                signal_type,
                datetime_range=datetime_range,
                approximation_time=datetime.timedelta(hours=1),
            )
