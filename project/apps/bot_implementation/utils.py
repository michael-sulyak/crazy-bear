import requests

from project import config


def get_weather() -> dict:
    return requests.get(config.OPENWEATHERMAP_URL).json()
