import base64
import re
import typing

import requests


class TpLinkClient:
    username: typing.Optional[str]
    password: str
    url: str

    def __init__(self, username: typing.Optional[str], password: str, url: str) -> None:
        self.url = url
        self.password = password
        self.username = username

    def get_connected_devices(self) -> typing.List[typing.Dict[str, typing.Any]]:
        raw_data = self._get_raw_connected_devices()
        raw_blocks = re.split(r'^\[.*\]0$', raw_data, flags=re.MULTILINE)

        devices = []

        for raw_block in raw_blocks:
            if not raw_block:
                continue

            lines = raw_block.splitlines()
            data = {}

            for line in lines:
                if not line:
                    continue

                key, value = line.split('=', 1)
                data[key] = value

            devices.append(data)

        return devices

    def _get_raw_connected_devices(self) -> str:
        connection_string = (
            self.password
            if self.username is None else
            f'{self.username}:{self.password}'
        )
        b64_encoded_password = base64.b64encode(connection_string.encode('ascii')).decode('ascii')
        cookie = f'Authorization=Basic {b64_encoded_password}'
        payload = '[LAN_HOST_ENTRY#0,0,0,0,0,0#0,0,0,0,0,0]0,0\r\n'

        response = requests.post(
            f'{self.url}/cgi?5',
            data=payload,
            headers={
                'Referer': self.url,
                'Cookie': cookie,
                'Content-Type': 'text/plain',
            },
            timeout=10,
        )

        response.raise_for_status()

        return response.text
