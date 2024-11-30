import datetime
import functools
import io
import logging
import math
import os
import typing
from collections import deque
from contextlib import contextmanager

import cv2
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import pytz
import requests
from matplotlib.dates import DateFormatter
from matplotlib.ticker import AutoLocator, MaxNLocator
from requests import RequestException

from libs.casual_utils.time import get_current_time

from ... import config
from ...config import PY_TZ


def timer(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrap_func(*args, **kwargs) -> typing.Any:
        started_at = datetime.datetime.now()
        result = func(*args, **kwargs)
        finished_at = datetime.datetime.now()
        logging.debug(
            'Function %s.%s executed in %s.',
            func.__module__,
            func.__qualname__,
            finished_at - started_at,
        )
        return result

    return wrap_func


@contextmanager
def inline_timer(name: str) -> typing.Generator:
    started_at = datetime.datetime.now()
    yield
    finished_at = datetime.datetime.now()

    logging.info(
        '%s executed in %s.',
        name,
        finished_at - started_at,
    )


def get_cpu_temp() -> float:
    """Get the core temperature.
    Run a shell script to get the core temp and parse the output.
    Raises:
        RuntimeError: if response cannot be parsed.
    Returns:
        float: The core temperature in degrees Celsius.
    """

    with open('/sys/class/thermal/thermal_zone0/temp') as file:
        temp_str = file.read()

    try:
        return int(temp_str) / 1_000
    except (
        IndexError,
        ValueError,
    ) as e:
        raise RuntimeError('Could not parse temperature output.') from e


def init_settings_for_plt() -> None:
    import mplcyberpunk  # NOQA

    mpl.use('Agg')
    plt.ioff()
    pd.plotting.register_matplotlib_converters()
    plt.rcParams.update({'font.family': 'Roboto'})

    plt.style.use('cyberpunk')


@timer
def create_plot(
    *,
    title: str,
    x_attr: str,
    y_attr: str,
    stats: typing.Sequence,
    additional_plots: typing.Sequence[dict] | None = None,
    legend: typing.Sequence[str] | None = None,
) -> io.BytesIO:
    if len(stats) <= 2:
        marker = 'o'
    else:
        marker = None

    x = tuple(getattr(item, x_attr) for item in stats)
    y = tuple(round(getattr(item, y_attr), 1) for item in stats)
    x_is_date = isinstance(
        x[0],

            datetime.date| datetime.datetime,
    )

    fig, ax = plt.subplots(
        figsize=(
            12,
            8,
        ),
    )
    ax.plot(mdates.date2num(x) if x_is_date else x, y, marker=marker)

    if additional_plots is not None:
        for additional_plot in additional_plots:
            x_ = tuple(getattr(item, additional_plot['x_attr']) for item in additional_plot['stats'])
            y_ = tuple(round(getattr(item, additional_plot['y_attr']), 1) for item in additional_plot['stats'])

            ax.plot(x_, y_, marker=marker)

    if legend is not None:
        ax.legend(legend)

    if x_is_date:
        if len(x) > 1:
            diff = abs(x[0] - x[-1])
            postfix = f'({x[0].strftime("%H:%M:%S %d.%m.%y")} - {x[-1].strftime("%H:%M:%S %d.%m.%y")})'
        else:
            diff = datetime.timedelta(seconds=1)
            postfix = ''

        if diff < datetime.timedelta(seconds=10):
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M:%S', tz=config.PY_TZ))
            ax.xaxis.set_major_locator(mdates.SecondLocator(interval=1))
            plt.xlabel(f'Time {postfix}')
        elif diff < datetime.timedelta(minutes=20):
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M', tz=config.PY_TZ))
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
            plt.xlabel(f'Time {postfix}')
        elif diff <= datetime.timedelta(hours=24):
            ax.xaxis.set_major_formatter(DateFormatter('%H', tz=config.PY_TZ))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
            plt.xlabel(f'Hours {postfix}')
        elif diff < datetime.timedelta(days=30):
            ax.xaxis.set_major_formatter(DateFormatter('%d', tz=config.PY_TZ))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            plt.xlabel(f'Days {postfix}')
        elif diff < datetime.timedelta(days=30 * 15):
            ax.xaxis.set_major_formatter(DateFormatter('%m', tz=config.PY_TZ))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            plt.xlabel(f'Months {postfix}')
        else:
            ax.xaxis.set_major_formatter(DateFormatter('%y', tz=config.PY_TZ))
            ax.xaxis.set_major_locator(mdates.YearLocator())
            plt.xlabel(f'Years {postfix}')
    else:
        ax.xaxis.set_major_locator(AutoLocator())

    if all((isinstance(i, int) or (isinstance(i, float) and i.is_integer())) for i in y):
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    ax.set_title(title)

    buffer = io.BytesIO()
    fig.savefig(buffer, format='png')
    buffer.seek(0)

    fig.clear()
    plt.close(fig)

    return buffer


def camera_is_available(src: int) -> bool:
    cap = cv2.VideoCapture(src)
    is_available = cap.isOpened()
    cap.release()

    return is_available


def get_weather() -> dict:
    return requests.get(config.OPENWEATHERMAP_URL, timeout=10).json()


def get_sunrise_time() -> datetime.datetime:
    try:
        weather_info = get_weather()
    except RequestException:
        logging.exception('Cannot get weather info')
        return PY_TZ.localize(datetime.datetime.combine(datetime.datetime.today(), datetime.time(6, 00)))

    sunrise_dt = datetime.datetime.fromtimestamp(weather_info['sys']['sunrise'])
    sunrise_dt -= datetime.timedelta(seconds=weather_info['timezone'])
    return pytz.UTC.localize(sunrise_dt)


def is_sleep_hours(timestamp: datetime.datetime | None = None) -> bool:
    if timestamp is None:
        timestamp = datetime.datetime.now()

    timestamp_time = timestamp.time()

    if config.SLEEPING_TIME[0] > config.SLEEPING_TIME[1]:
        return timestamp_time >= config.SLEEPING_TIME[0] or timestamp_time <= config.SLEEPING_TIME[1]

    return config.SLEEPING_TIME[0] <= timestamp_time <= config.SLEEPING_TIME[1]


def convert_params_to_date_range(
    delta_value: int = 24, delta_type: str = 'hours',
) -> tuple[datetime.datetime, datetime.datetime]:
    now = get_current_time()
    return now - datetime.timedelta(**{delta_type: delta_value}), now


# TODO: Use it
def max_timer(max_timedelta: datetime.timedelta, log: typing.Callable = logging.warning) -> typing.Callable:
    def _decorator(func: typing.Callable) -> typing.Callable:
        @functools.wraps(func)
        def _wrapper(*args, **kwargs) -> typing.Any:
            start = datetime.datetime.now()
            result = _wrapper(*args, **kwargs)
            delta = datetime.datetime.now() - start

            if delta > max_timedelta:
                log(
                    f'Slow execution in {func.__module__}ю{func.__name__}',
                    extra={
                        'delta': delta,
                        'args': args,
                        'kwargs': kwargs,
                        'result': result,
                    },
                )

            return result

        return _wrapper

    return _decorator


def get_ram_usage() -> float:
    total, used, free = map(int, os.popen('free -t -m').readlines()[1].split()[1:4])
    return 1 - free / total


def get_free_disk_space() -> int:
    return int(os.popen("df / --output=avail -B M |tail -n 1 |tr -d M |awk '{print $1}'").readlines()[0])


@contextmanager
def mock_var(module: object, attribute: str, new: typing.Any) -> typing.Generator:
    prev_value = getattr(module, attribute)
    setattr(module, attribute, new)
    yield
    setattr(module, attribute, prev_value)


def with_throttling(period: datetime.timedelta, *, count: int = 1) -> typing.Callable:
    def _decorator(func: typing.Callable) -> typing.Callable:
        times_of_run: deque = deque()

        @functools.wraps(func)
        def _wrapper(*args, **kwargs) -> None:
            now = datetime.datetime.now()

            while len(times_of_run) >= count:
                if now - times_of_run[0] > period:
                    times_of_run.popleft()
                else:
                    return

            times_of_run.append(now)

            func(*args, **kwargs)

        return _wrapper

    return _decorator


def get_effective_temperature(*, humidity: float, temperature: float) -> float:
    """
    See https://planetcalc.ru/2089/
    """

    e = humidity / 100 * 6.105 * math.e ** ((17.27 * temperature) / (237.7 + temperature))
    return temperature + 0.348 * e - 4.25
