import hashlib
import random
import time
import typing
import uuid

import requests

from project import config


__all__ = (
    'MiWiFi',
    'mi_wifi',
)

PUBLIC_KEY = 'a2ffa5c9be07488bbb04a3a47d3c5f6a'


def sha1(x: str) -> str:
    return hashlib.sha1(x.encode()).hexdigest()


def get_mac_address() -> str:
    as_hex = f'{uuid.getnode():012x}'
    return ':'.join(as_hex[i: i + 2] for i in range(0, 12, 2))


def generate_nonce(miwifi_type: int = 0) -> str:
    return f'{miwifi_type}_{get_mac_address()}_{int(time.time())}_{int(random.random() * 1000)}'


def generate_password_hash(nonce: str, password: str) -> str:
    return sha1(nonce + sha1(password + PUBLIC_KEY))


class MiWiFi:
    url: str
    password: str
    token: typing.Optional[str] = None
    miwifi_type: int

    def __init__(self, *, url: str, password: str, miwifi_type: int = 0) -> None:
        if url.endswith('/'):
            url = url[:-1]

        self.url = url
        self.password = password
        self.miwifi_type = miwifi_type

    def __enter__(self) -> 'MiWiFi':
        self.login()
        return self

    def __exit__(self, *args) -> None:
        self.logout()

    def login(self) -> None:
        nonce = generate_nonce(self.miwifi_type)

        response = requests.post(
            f'{self.url}/cgi-bin/luci/api/xqsystem/login',
            data={
                'username': 'admin',
                'logtype': '2',
                'password': generate_password_hash(nonce, self.password),
                'nonce': nonce,
            },
            timeout=5,
        )

        response.raise_for_status()
        json_response = response.json()
        self.token = json_response['token']

    def logout(self) -> None:
        response = requests.get(f'{self.url}/cgi-bin/luci/;stok={self.token}/web/logout')
        response.raise_for_status()
        self.token = None

    def status(self):
        return self.get_data('misystem/status')

    def device_list(self):
        return self.get_data('misystem/devicelist')

    def bandwidth_test(self):
        return self.get_data('misystem/bandwidth_test')

    def pppoe_status(self):
        return self.get_data('xqnetwork/pppoe_status')

    def wifi_detail_all(self):
        return self.get_data('xqnetwork/wifi_detail_all')

    def country_code(self):
        return self.get_data('xqsystem/country_code')

    def wan_info(self):
        return self.get_data('xqsystem/wan_info')

    def check_wan_type(self):
        return self.get_data('xqsystem/check_wan_type')

    def get_data(self, endpoint: str,*, _update_token: bool = True) -> dict:
        assert self.token is not None

        response = requests.get(
            f'{self.url}/cgi-bin/luci/;stok={self.token}/api/{endpoint}',
            timeout=5,
        )
        response.raise_for_status()
        data = response.json()

        if 'code' in data and data['code'] == 401:
            if _update_token:
                # Try to update token.
                mi_wifi.login()
                return self.get_data(endpoint, _update_token=False)

            raise Exception('Invalid request')

        return data


if config.ROUTER_TYPE == 'mi':
    mi_wifi = MiWiFi(password=config.ROUTER_PASSWORD, url=config.ROUTER_URL)
    mi_wifi.login()  # To reduce count of requests
else:
    mi_wifi = None
