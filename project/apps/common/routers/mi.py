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

    def login(self) -> None:
        nonce = self._generate_nonce()

        response = requests.post(
            f'{self.url}/cgi-bin/luci/api/xqsystem/login',
            data={
                'username': 'admin',
                'logtype': '2',
                'password': self._generate_password_hash(nonce),
                'nonce': nonce,
            },
            timeout=30,
        )

        response.raise_for_status()
        json_response = response.json()
        self.token = json_response['token']

    def logout(self) -> None:
        response = requests.get(f'{self.url}/cgi-bin/luci/;stok={self.token}/web/logout')
        response.raise_for_status()
        self.token = None

    def status(self) -> dict:
        return self._get_data('misystem/status')

    def device_list(self) -> dict:
        return self._get_data('misystem/devicelist')

    def bandwidth_test(self) -> dict:
        return self._get_data('misystem/bandwidth_test')

    def pppoe_status(self) -> dict:
        return self._get_data('xqnetwork/pppoe_status')

    def wifi_detail_all(self):
        return self._get_data('xqnetwork/wifi_detail_all')

    def country_code(self) -> dict:
        return self._get_data('xqsystem/country_code')

    def wan_info(self) -> dict:
        return self._get_data('xqsystem/wan_info')

    def check_wan_type(self) -> dict:
        return self._get_data('xqsystem/check_wan_type')

    def _get_data(self, endpoint: str, *, _update_token: bool = True) -> dict:
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
                return self._get_data(endpoint, _update_token=False)

            raise Exception('Invalid request')

        return data

    def _generate_nonce(self) -> str:
        return f'{self.miwifi_type}_{self._get_mac_address()}_{int(time.time())}_{int(random.random() * 1000)}'

    def _generate_password_hash(self, nonce: str) -> str:
        public_key = 'a2ffa5c9be07488bbb04a3a47d3c5f6a'
        return self._get_sha1(nonce + self._get_sha1(self.password + public_key))

    @staticmethod
    def _get_sha1(x: str) -> str:
        return hashlib.sha1(x.encode()).hexdigest()

    @staticmethod
    def _get_mac_address() -> str:
        as_hex = f'{uuid.getnode():012x}'
        return ':'.join(as_hex[i: i + 2] for i in range(0, 12, 2))


if config.ROUTER_TYPE == 'mi':
    mi_wifi = MiWiFi(password=config.ROUTER_PASSWORD, url=config.ROUTER_URL)
    mi_wifi.login()  # To reduce count of requests
else:
    mi_wifi = None
