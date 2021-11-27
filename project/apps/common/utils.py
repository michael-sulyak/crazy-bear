import datetime
import functools
import io
import logging
import os
import tempfile
import threading
import typing

import cv2
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd
import requests
import seaborn as sns
from matplotlib.dates import DateFormatter
from matplotlib.ticker import AutoLocator, MaxNLocator

from ... import config


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
        return int(temp_str) / 1000
    except (IndexError, ValueError,) as e:
        raise RuntimeError('Could not parse temperature output.') from e


def init_settings_for_plt():
    plt.ioff()
    sns.set()
    pd.plotting.register_matplotlib_converters()


def create_plot(*,
                title: str,
                x_attr: str,
                y_attr: str,
                stats: list,
                additional_plots: typing.Optional[typing.Sequence[dict]] = None,
                legend: typing.Optional[typing.Sequence[str]] = None) -> io.BytesIO:
    # init_settings_for_plt() is called before

    if len(stats) <= 2:
        marker = 'o'
    else:
        marker = None

    x = tuple(getattr(item, x_attr) for item in stats)
    y = tuple(round(getattr(item, y_attr), 1) for item in stats)

    fig, ax = plt.subplots(figsize=(12, 8,))
    ax.plot(x, y, marker=marker)

    if additional_plots is not None:
        for additional_plot in additional_plots:
            x_ = tuple(getattr(item, additional_plot['x_attr']) for item in additional_plot['stats'])
            y_ = tuple(round(getattr(item, additional_plot['y_attr']), 1) for item in additional_plot['stats'])

            ax.plot(x_, y_, marker=marker)

    if legend is not None:
        ax.legend(legend)

    if isinstance(x[0], (datetime.date, datetime.datetime,)):
        if len(x) > 1:
            diff = abs(x[0] - x[-1])
            postfix = f'({x[0].strftime("%H:%M:%S %d.%m.%y")} - {x[-1].strftime("%H:%M:%S %d.%m.%y")})'
        else:
            diff = datetime.timedelta(seconds=1)
            postfix = ''

        if diff < datetime.timedelta(seconds=10):
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M:%S'))
            ax.xaxis.set_major_locator(mdates.SecondLocator(interval=1))
            plt.xlabel(f'Time {postfix}')
        elif diff < datetime.timedelta(minutes=20):
            ax.xaxis.set_major_formatter(DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.MinuteLocator(interval=1))
            plt.xlabel(f'Time {postfix}')
        elif diff <= datetime.timedelta(hours=24):
            ax.xaxis.set_major_formatter(DateFormatter('%H'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
            plt.xlabel(f'Hours {postfix}')
        elif diff < datetime.timedelta(days=30):
            ax.xaxis.set_major_formatter(DateFormatter('%d'))
            ax.xaxis.set_major_locator(mdates.DayLocator(interval=1))
            plt.xlabel(f'Days {postfix}')
        elif diff < datetime.timedelta(days=30 * 15):
            ax.xaxis.set_major_formatter(DateFormatter('%m'))
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            plt.xlabel(f'Months {postfix}')
        else:
            ax.xaxis.set_major_formatter(DateFormatter('%y'))
            ax.xaxis.set_major_locator(mdates.YearLocator())
            plt.xlabel(f'Years {postfix}')
    else:
        ax.xaxis.set_major_locator(AutoLocator())

    if all(isinstance(i, int) or isinstance(i, float) and i.is_integer() for i in y):
        ax.yaxis.set_major_locator(MaxNLocator(integer=True))

    ax.set_title(title)

    with tempfile.TemporaryDirectory() as temp_dir_name:
        image_name = os.path.join(temp_dir_name, f'{title}.png')
        fig.savefig(image_name)
        fig.clear()
        plt.close(fig)

        with open(image_name, 'rb') as image:
            return io.BytesIO(image.read())


def camera_is_available(src: int) -> bool:
    cap = cv2.VideoCapture(src)
    is_available = cap.isOpened()
    cap.release()

    return is_available


def get_weather() -> dict:
    return requests.get(config.OPENWEATHERMAP_URL, timeout=10).json()


def synchronized_method(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def _wrapper(self, *args, **kwargs):
        try:
            lock = self._lock
        except AttributeError as e:
            raise Exception(f'"{func.__name__}" does not contain "_lock"') from e

        with lock:
            return func(self, *args, **kwargs)

    return _wrapper


def single_synchronized(func: typing.Callable) -> typing.Callable:
    lock = threading.RLock()

    @functools.wraps(func)
    def _wrapper(*args, **kwargs):
        with lock:
            return func(*args, **kwargs)

    return _wrapper


def is_sleep_hours(timestamp: datetime.datetime) -> bool:
    assert 0 <= config.SLEEP_HOURS[0] <= 24
    assert 0 <= config.SLEEP_HOURS[1] <= 24
    assert config.SLEEP_HOURS[0] != config.SLEEP_HOURS[1]

    if config.SLEEP_HOURS[0] > config.SLEEP_HOURS[1]:
        return timestamp.hour >= config.SLEEP_HOURS[0] or timestamp.hour <= config.SLEEP_HOURS[1]
    else:
        return config.SLEEP_HOURS[0] <= timestamp.hour <= config.SLEEP_HOURS[1]


def convert_params_to_date_range(delta_value: int = 24,
                                 delta_type: str = 'hours') -> typing.Tuple[datetime.datetime, datetime.datetime]:
    now = datetime.datetime.now()
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


def timer(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrap_func(*args, **kwargs) -> typing.Any:
        started_at = datetime.datetime.now()
        result = func(*args, **kwargs)
        finished_at = datetime.datetime.now()
        logging.info(
            'Function %s.%s executed in %s.',
            func.__module__,
            func.__qualname__,
            finished_at - started_at,
        )
        return result

    return wrap_func
