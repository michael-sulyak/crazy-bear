import base64
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import requests


@dataclass(frozen=True)
class Product:
    id: int | None
    name: str | None
    en_name: str | None


@dataclass(frozen=True)
class DeviceStatus:
    offline: bool | None
    altering: bool | None


@dataclass(frozen=True)
class DeviceSetting:
    report_interval_seconds: int | None
    collect_interval_seconds: int | None


@dataclass(frozen=True)
class Measurement:
    battery_percent: float | None
    humidity_percent: float | None
    pressure_kpa: float | None
    temperature_celsius: float | None
    tvoc: float | None
    co2: float | None
    pm25: float | None
    pm10: float | None
    measured_at: datetime | None


@dataclass(frozen=True)
class Device:
    name: str
    mac: str
    version: str | None
    created_at: datetime | None
    group_id: int | None
    group_name: str | None
    product: Product | None
    status: DeviceStatus | None
    setting: DeviceSetting | None
    latest_measurement: Measurement | None


@dataclass(frozen=True)
class DeviceList:
    total: int
    devices: list[Device]


@dataclass
class AccessToken:
    access_token: str
    token_type: str
    expires_at: float

    def is_expired(self, safety_margin_seconds: int = 60) -> bool:
        """
        Returns True when token is expired or close to expiration.

        The safety margin avoids starting an API request with a token that
        may expire during the request.
        """
        return time.time() >= self.expires_at - safety_margin_seconds


class CleargrassApiError(Exception):
    pass


class CleargrassAuthError(CleargrassApiError):
    pass


class CleargrassClient:
    """
    Doc: https://developer.qingping.co/cloud-to-cloud/open-apis
    """

    def __init__(
            self,
            app_key: str,
            app_secret: str,
            api_base_url: str = 'https://apis.cleargrass.com',
            oauth_base_url: str = 'https://oauth.cleargrass.com',
            timeout_seconds: float = 10.0,
            token_refresh_margin_seconds: int = 60,
            proxies: dict | None = None,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.api_base_url = api_base_url.rstrip('/')
        self.oauth_base_url = oauth_base_url.rstrip('/')
        self.timeout_seconds = timeout_seconds
        self.token_refresh_margin_seconds = token_refresh_margin_seconds
        self.proxies = proxies

        self.session = requests.Session()
        self.access_token: AccessToken | None = None

    def get_devices(
            self,
            group_id: int | None = None,
            offset: int | None = None,
            limit: int | None = None,
    ) -> DeviceList:
        params: dict[str, Any] = {
            'timestamp': self._timestamp_ms(),
        }

        if group_id is not None:
            params['group_id'] = group_id

        if offset is not None:
            params['offset'] = offset

        if limit is not None:
            if limit > 50:
                raise ValueError('limit must not be bigger than 50')

            params['limit'] = limit

        payload = self._api_request(
            method='GET',
            path='/v1/apis/devices',
            params=params,
        )

        return self._parse_device_list(payload)

    def get_latest_measurement(self, mac: str) -> Measurement | None:
        devices = self.get_devices(limit=50)

        for device in devices.devices:
            if device.mac.upper() == mac.upper():
                return device.latest_measurement

        return None

    def get_latest_measurements(self) -> dict[str, Measurement]:
        devices = self.get_devices(limit=50)

        result: dict[str, Measurement] = {}

        for device in devices.devices:
            if device.latest_measurement is not None:
                result[device.mac] = device.latest_measurement

        return result
    def update_device_settings(
            self,
            macs: list[str],
            report_interval_seconds: int,
            collect_interval_seconds: int,
    ) -> None:
        if not macs:
            raise ValueError('macs must not be empty')

        if report_interval_seconds < 60:
            raise ValueError('report_interval_seconds must be at least 60')

        if collect_interval_seconds <= 0:
            raise ValueError('collect_interval_seconds must be greater than 0')

        if report_interval_seconds % collect_interval_seconds != 0:
            raise ValueError(
                'report_interval_seconds must be an integer multiple of '
                'collect_interval_seconds',
            )

        payload: dict[str, Any] = {
            'mac': macs,
            'report_interval': report_interval_seconds,
            'collect_interval': collect_interval_seconds,
            'timestamp': self._timestamp_ms(),
        }

        self._api_request(
            method='PUT',
            path='/v1/apis/devices/settings',
            json_body=payload,
        )
    def _api_request(
            self,
            method: str,
            path: str,
            params: dict[str, Any] | None = None,
            json_body: dict[str, Any] | None = None,
            retry_on_unauthorized: bool = True,
    ) -> dict[str, Any]:
        token = self._get_valid_access_token()

        url = f'{self.api_base_url}{path}'

        headers = {
            'Authorization': f'Bearer {token.access_token}',
            'Accept': 'application/json',
        }

        if json_body is not None:
            headers['Content-Type'] = 'application/json'

        response = self.session.request(
            method=method,
            url=url,
            params=params,
            json=json_body,
            headers=headers,
            timeout=self.timeout_seconds,
            proxies=self.proxies,
        )

        if response.status_code == 401 and retry_on_unauthorized:
            self.access_token = None

            return self._api_request(
                method=method,
                path=path,
                params=params,
                json_body=json_body,
                retry_on_unauthorized=False,
            )

        return self._parse_response(response)

    def _get_valid_access_token(self) -> AccessToken:
        if self.access_token is None:
            self.access_token = self._request_access_token()
            return self.access_token

        if self.access_token.is_expired(self.token_refresh_margin_seconds):
            self.access_token = self._request_access_token()
            return self.access_token

        return self.access_token

    def _request_access_token(self) -> AccessToken:
        url = f'{self.oauth_base_url}/oauth2/token'

        credentials = f'{self.app_key}:{self.app_secret}'.encode()
        encoded_credentials = base64.b64encode(credentials).decode('ascii')

        headers = {
            'Authorization': f'Basic {encoded_credentials}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
        }

        data = {
            'grant_type': 'client_credentials',
            'scope': 'device_full_access',
        }

        response = self.session.post(
            url=url,
            headers=headers,
            data=data,
            timeout=self.timeout_seconds,
            proxies=self.proxies,
        )

        try:
            payload = self._parse_response(response)
        except CleargrassApiError as exc:
            raise CleargrassAuthError('Failed to obtain Cleargrass access token') from exc

        access_token = payload.get('access_token')
        token_type = payload.get('token_type') or 'Bearer'
        expires_in = payload.get('expires_in')

        if not isinstance(access_token, str) or not access_token:
            raise CleargrassAuthError('OAuth response does not contain access_token')

        try:
            expires_in_seconds = int(expires_in)
        except TypeError as exc:
            raise CleargrassAuthError('OAuth response does not contain valid expires_in') from exc
        except ValueError as exc:
            raise CleargrassAuthError('OAuth response does not contain valid expires_in') from exc

        return AccessToken(
            access_token=access_token,
            token_type=str(token_type),
            expires_at=time.time() + expires_in_seconds,
        )

    @staticmethod
    def _parse_response(response: requests.Response) -> dict[str, Any]:
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise CleargrassApiError(
                f'Cleargrass request failed: {response.status_code} {response.text}',
            ) from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise CleargrassApiError(
                f'Cleargrass returned invalid JSON: {response.text}',
            ) from exc

        if not isinstance(data, dict):
            raise CleargrassApiError('Cleargrass returned non-object JSON response')

        return data

    @staticmethod
    def _timestamp_ms() -> int:
        return int(time.time() * 1000)

    @classmethod
    def _parse_device_list(cls, payload: dict[str, Any]) -> DeviceList:
        raw_devices = payload.get('devices', [])

        devices = [
            cls._parse_device(raw_device)
            for raw_device in raw_devices
            if isinstance(raw_device, dict)
        ]

        return DeviceList(
            total=int(payload.get('total', len(devices))),
            devices=devices,
        )

    @classmethod
    def _parse_device(cls, raw: dict[str, Any]) -> Device:
        info = raw.get('info') or {}
        data = raw.get('data')

        if not isinstance(info, dict):
            info = {}

        return Device(
            name=str(info.get('name') or ''),
            mac=str(info.get('mac') or ''),
            version=cls._optional_str(info.get('version')),
            created_at=cls._parse_unix_seconds(info.get('created_at')),
            group_id=cls._optional_int(info.get('group_id')),
            group_name=cls._optional_str(info.get('group_name')),
            product=cls._parse_product(info.get('product')),
            status=cls._parse_status(info.get('status')),
            setting=cls._parse_setting(info.get('setting')),
            latest_measurement=cls._parse_measurement(data),
        )

    @classmethod
    def _parse_product(cls, raw: Any) -> Product | None:
        if not isinstance(raw, dict):
            return None

        return Product(
            id=cls._optional_int(raw.get('id')),
            name=cls._optional_str(raw.get('name')),
            en_name=cls._optional_str(raw.get('en_name')),
        )

    @classmethod
    def _parse_status(cls, raw: Any) -> DeviceStatus | None:
        if not isinstance(raw, dict):
            return None

        return DeviceStatus(
            offline=cls._optional_bool(raw.get('offline')),
            altering=cls._optional_bool(raw.get('altering')),
        )

    @classmethod
    def _parse_setting(cls, raw: Any) -> DeviceSetting | None:
        if not isinstance(raw, dict):
            return None

        return DeviceSetting(
            report_interval_seconds=cls._optional_int(raw.get('report_interval')),
            collect_interval_seconds=cls._optional_int(raw.get('collect_interval')),
        )

    @classmethod
    def _parse_measurement(cls, raw: Any) -> Measurement | None:
        if not isinstance(raw, dict):
            return None

        return Measurement(
            battery_percent=cls._extract_value(raw, 'battery'),
            humidity_percent=cls._extract_value(raw, 'humidity'),
            pressure_kpa=cls._extract_value(raw, 'pressure'),
            temperature_celsius=cls._extract_value(raw, 'temperature'),
            tvoc=cls._extract_value(raw, 'tvoc'),
            co2=cls._extract_value(raw, 'co2'),
            pm25=cls._extract_value(raw, 'pm25'),
            pm10=cls._extract_value(raw, 'pm10'),
            measured_at=cls._parse_timestamp_field(raw.get('timestamp')),
        )

    @classmethod
    def _extract_value(cls, raw: dict[str, Any], key: str) -> float | None:
        field = raw.get(key)

        if not isinstance(field, dict):
            return None

        return cls._optional_float(field.get('value'))

    @classmethod
    def _parse_timestamp_field(cls, raw: Any) -> datetime | None:
        if not isinstance(raw, dict):
            return None

        return cls._parse_unix_seconds(raw.get('value'))

    @staticmethod
    def _parse_unix_seconds(value: Any) -> datetime | None:
        if value is None:
            return None

        try:
            timestamp = float(value)
        except TypeError:
            return None
        except ValueError:
            return None

        return datetime.fromtimestamp(timestamp, tz=UTC)

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None

        return str(value)

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value is None:
            return None

        try:
            return int(value)
        except TypeError:
            return None
        except ValueError:
            return None

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except TypeError:
            return None
        except ValueError:
            return None

    @staticmethod
    def _optional_bool(value: Any) -> bool | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        if isinstance(value, int):
            return bool(value)

        if isinstance(value, str):
            lowered = value.strip().lower()

            if lowered in {'true', '1', 'yes'}:
                return True

            if lowered in {'false', '0', 'no'}:
                return False

        return None
