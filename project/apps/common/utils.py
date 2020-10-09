import logging
import os
import tempfile

import cv2
import matplotlib.pyplot as plt
import requests
import seaborn as sns
from matplotlib.ticker import AutoLocator, IndexFormatter

from .tplink import TpLinkClient
from ..messengers.base import BaseMessenger
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


def send_plot(messenger: BaseMessenger, title: str, attr: str, stats: list) -> None:
    sns.set()

    if len(stats) <= 2:
        marker = 'o'
    else:
        marker = None

    x = [i for i in range(len(stats))]
    x_labels = [item.time for item in stats]
    y = [round(getattr(item, attr), 1) for item in stats]

    fig, ax = plt.subplots()
    ax.xaxis.set_major_locator(AutoLocator())
    ax.yaxis.set_major_locator(AutoLocator())
    ax.xaxis.set_major_formatter(IndexFormatter(x_labels))
    ax.plot(x, y, marker=marker)
    ax.set_title(title)

    with tempfile.TemporaryDirectory() as temp_dir_name:
        image_name = os.path.join(temp_dir_name, 'plot.png')
        fig.savefig(image_name)

        with open(image_name, 'rb') as image:
            messenger.send_image(image)


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

    connected_mac_addresses = set(
        device.get('MACAddress')
        for device in connected_devices
    )

    return bool(connected_mac_addresses & config.ROUTER_USER_MAC_ADDRESSES)


def camera_is_available(src: int) -> bool:
    cap = cv2.VideoCapture(src)
    is_available = cap.isOpened()
    cap.release()

    return is_available


def get_weather() -> dict:
    return requests.get(config.OPENWEATHERMAP_URL).json()