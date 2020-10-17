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
import requests
import seaborn as sns
from matplotlib.dates import DateFormatter
from matplotlib.ticker import AutoLocator, MaxNLocator

from .tplink import TpLinkClient
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


def create_plot(*, title: str, x_attr: str, y_attr: str, stats: list) -> io.BytesIO:
    sns.set()

    if len(stats) <= 2:
        marker = 'o'
    else:
        marker = None

    x = tuple(getattr(item, x_attr) for item in stats)
    y = tuple(round(getattr(item, y_attr), 1) for item in stats)

    fig, ax = plt.subplots(figsize=(12, 8,))
    ax.plot(x, y, marker=marker)

    if isinstance(x[0], (datetime.date, datetime.datetime,)):
        diff = abs(x[0] - x[-1])
        postfix = f'({x[0].strftime("%H:%M:%S %d.%m.%y")} - {x[1].strftime("%H:%M:%S %d.%m.%y")})'

        if diff < datetime.timedelta(seconds=20):
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

        with open(image_name, 'rb') as image:
            return io.BytesIO(image.read())


def check_user_connection_to_router() -> bool:
    tplink_client = TpLinkClient(
        username=config.ROUTER_USERNAME,
        password=config.ROUTER_PASSWORD,
        url=config.ROUTER_URL,
    )

    try:
        connected_devices = tplink_client.get_connected_devices()
    except Exception as e:
        logging.exception(e)
        return False

    user_connection_to_router = any(
        device.get('MACAddress') in config.ROUTER_USER_MAC_ADDRESSES
        for device in connected_devices
    )

    return user_connection_to_router


def camera_is_available(src: int) -> bool:
    cap = cv2.VideoCapture(src)
    is_available = cap.isOpened()
    cap.release()

    return is_available


def get_weather() -> dict:
    return requests.get(config.OPENWEATHERMAP_URL).json()


def synchronized(func: typing.Callable) -> typing.Callable:
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
