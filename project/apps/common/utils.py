import datetime
import functools
import io
import logging
import os
import threading
import typing
from contextlib import contextmanager

import cv2
import matplotlib
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests
import seaborn as sns
import sentry_sdk
from matplotlib.dates import DateFormatter
from matplotlib.ticker import AutoLocator, MaxNLocator

from ... import config


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
    except (IndexError, ValueError,) as e:
        raise RuntimeError('Could not parse temperature output.') from e


def init_settings_for_plt() -> None:
    matplotlib.use('Agg')
    plt.ioff()
    sns.set()
    pd.plotting.register_matplotlib_converters()


@timer
def create_plot(*,
                title: str,
                x_attr: str,
                y_attr: str,
                stats: typing.Sequence,
                additional_plots: typing.Optional[typing.Sequence[dict]] = None,
                legend: typing.Optional[typing.Sequence[str]] = None) -> io.BytesIO:
    if len(stats) <= 2:
        marker = 'o'
    else:
        marker = None

    x = tuple(getattr(item, x_attr) for item in stats)
    y = tuple(round(getattr(item, y_attr), 1) for item in stats)
    x_is_date = isinstance(x[0], (datetime.date, datetime.datetime,))

    fig, ax = plt.subplots(figsize=(12, 8,))
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


def is_sleep_hours(timestamp: typing.Optional[datetime.datetime] = None) -> bool:
    assert 0 <= config.SLEEP_HOURS[0] <= 24
    assert 0 <= config.SLEEP_HOURS[1] <= 24
    assert config.SLEEP_HOURS[0] != config.SLEEP_HOURS[1]

    if timestamp is None:
        timestamp = datetime.datetime.now()

    if config.SLEEP_HOURS[0] > config.SLEEP_HOURS[1]:
        return timestamp.hour >= config.SLEEP_HOURS[0] or timestamp.hour <= config.SLEEP_HOURS[1]
    else:
        return config.SLEEP_HOURS[0] <= timestamp.hour <= config.SLEEP_HOURS[1]


def convert_params_to_date_range(delta_value: int = 24,
                                 delta_type: str = 'hours') -> typing.Tuple[datetime.datetime, datetime.datetime]:
    now = current_time()
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


def get_my_ip() -> str:
    response = requests.get('https://api.ipify.org')
    response.raise_for_status()
    return response.content.decode('utf8')


@contextmanager
def log_performance(operation_type: str, name: str):
    with sentry_sdk.start_transaction(op=operation_type, name=name):
        yield


def log_func_performance(operation_type: str) -> typing.Callable:
    def decorate(func: typing.Callable) -> typing.Callable:
        func_name = f'{func.__module__}.{func.__qualname__}'

        @functools.wraps(func)
        def wrap_func(*args, **kwargs) -> typing.Any:
            with log_performance(operation_type, func_name):
                return func(*args, **kwargs)

        return wrap_func

    return decorate


def current_time() -> datetime.datetime:
    return datetime.datetime.now().astimezone()


def add_timestamp_in_frame(frame: np.array) -> None:
    cv2.putText(
        img=frame,
        text=datetime.datetime.now().strftime('%d.%m.%Y, %H:%M:%S'),
        org=(10, frame.shape[0] - 10,),
        fontFace=cv2.FONT_HERSHEY_SIMPLEX,
        fontScale=0.5,
        color=(0, 0, 255,),
        thickness=1,
    )


def get_ram_usage() -> float:
    total, used, free = map(int, os.popen('free -t -m').readlines()[1].split()[1:4])
    return 1 - free / total
