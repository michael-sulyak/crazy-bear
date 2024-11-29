import abc
import dataclasses
import itertools
import json
import logging
import re
import threading
import typing
from collections import defaultdict
import datetime

from paho.mqtt.client import Client, MQTTMessage, MQTTMessageInfo, MQTTv5
from paho.mqtt.enums import CallbackAPIVersion

from . import exceptions
from .constants import COORDINATOR_FRIENDLY_NAME, ZigBeePowerSources
from ..casual_utils.parallel_computing import synchronized_method
from ..smart_devices.base import BaseSmartDevice
from ..smart_devices.constants import SmartDeviceType


@dataclasses.dataclass
class ZigBeeDevice:
    friendly_name: str
    ieee_address: str
    power_source: str | None = None
    is_supported: bool | None = None
    is_disabled: bool | None = None
    is_available: bool | None = None
    type: str | None = None

    def to_str(self) -> str:
        return (
            f'Friendly name: `{self.friendly_name}`\n'
            f'IEEE address: `{self.ieee_address}`\n'
            f'Power source: `{self.power_source}`\n'
            f'Is supported: `{self.is_supported}`\n'
            f'Is disabled: `{self.is_disabled}`\n'
            f'Is available: `{self.is_available}`\n'
            f'Type: `{self.type}`'
        )

    @property
    def is_coordinator(self) -> bool:
        return self.friendly_name == COORDINATOR_FRIENDLY_NAME

    @property
    def is_active(self) -> bool:
        return self.power_source == ZigBeePowerSources.MAINS

    @property
    def is_passive(self) -> bool:
        return self.power_source == ZigBeePowerSources.BATTERY


class ZigBee:
    base_topic: str = 'zigbee2mqtt'
    _mq_host: str
    _mq_port: int
    _mq: Client | None = None
    _temporary_subscribers_map: dict[str, list[typing.Callable]]
    _permanent_subscribers_map: dict[str, list[typing.Callable]]
    _permanent_subscriber_key_regexps_map: dict[re.Pattern, str]
    _devices_map: dict[str, ZigBeeDevice]
    _availability_map: dict[str, bool]
    _lock: threading.RLock
    _is_opened: bool = False

    def __init__(self, *, mq_host: str, mq_port: int) -> None:
        self._lock = threading.RLock()

        self._temporary_subscribers_map = defaultdict(list)
        self._permanent_subscribers_map = defaultdict(list)
        self._availability_map = {}
        self._permanent_subscriber_key_regexps_map = {}
        self._devices_map = {}

        self._permanent_subscribers_map[f'{self.base_topic}/bridge/devices'].append(self._set_devices)

        self._subscribe_on_availability()

        self._mq_host = mq_host
        self._mq_port = mq_port

    @property
    @synchronized_method
    def mq(self) -> Client:
        if self._mq is None:
            self.open()

        assert self._mq is not None

        return self._mq

    @property
    @synchronized_method
    def devices(self) -> tuple[ZigBeeDevice, ...]:
        return tuple(self._devices_map.values())

    def set(self, friendly_name: str, payload: dict) -> None:
        self._publish_msg(f'{self.base_topic}/{friendly_name}/set', payload)

    def get_state(
        self,
        friendly_name: str,
        *,
        timeout: datetime.timedelta = datetime.timedelta(seconds=10),
    ) -> typing.Any:
        return self._request_data(
            topic_for_sending=f'{self.base_topic}/{friendly_name}/get',
            topic_for_receiving=f'{self.base_topic}/{friendly_name}',
            payload={'state': ''},
            timeout=timeout,
        )

    def is_health(self) -> bool:
        name = 'health_check'

        response = self._request_data(
            topic_for_sending=f'{self.base_topic}/bridge/request/{name}',
            topic_for_receiving=f'{self.base_topic}/bridge/response/{name}',
        )

        assert response is not None

        return response['status'] == 'ok' and response['data']['healthy']

    # def rename_device(self, friendly_name_or_ieee_address: str, new_friendly_name: str) -> bool:
    #     name = 'device/rename'
    #
    #     response = self._request_data(
    #         topic_for_sending=f'{self._base_topic}/bridge/request/{name}',
    #         topic_for_receiving=f'{self._base_topic}/bridge/response/{name}',
    #         payload={'from': friendly_name_or_ieee_address, 'to': new_friendly_name},
    #     )
    #
    #     assert response is not None
    #
    #     return response['status'] == 'ok'

    @synchronized_method
    def subscribe_on_topic(self, topic: str, func: typing.Callable) -> None:
        if '+' in topic:
            self._permanent_subscriber_key_regexps_map[re.compile(topic.replace('+', '.*'))] = topic

        self._permanent_subscribers_map[topic].append(func)

        if self._is_opened:
            self.mq.subscribe(topic)

        logging.info(f'ZigBee: "{func}" subscribes on "{topic}".')

    @synchronized_method
    def open(self) -> None:
        if self._mq is not None:
            raise exceptions.ZigBeeError('MQ was created.')

        mq = Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id='mqtt5_client',
            protocol=MQTTv5,
        )
        mq.on_message = self._on_message
        mq.on_disconnect = self._on_disconnect
        mq.connect(self._mq_host, port=self._mq_port)
        mq.loop_start()

        for topic in itertools.chain(self._temporary_subscribers_map, self._permanent_subscribers_map):
            logging.info(f'ZigBee: Subscribe on "{topic}" when opening.')
            mq.subscribe(topic)

        self._mq = mq

        self._is_opened = True

    @synchronized_method
    def close(self) -> None:
        if self._mq is None:
            logging.warning('MQ wasn\'t created.')
            return

        self.mq.loop_stop()

    @synchronized_method
    def _on_disconnect(self, *args, **kwargs) -> None:
        self._mq = None

    @synchronized_method
    def _on_message(self, client: Client, userdata: typing.Any, message: MQTTMessage) -> None:
        if not message.topic.startswith(f'{self.base_topic}/'):
            return

        payload = json.loads(message.payload.decode())

        for subscriber in itertools.chain(
            self._temporary_subscribers_map[message.topic],
            self._permanent_subscribers_map[message.topic],
        ):
            subscriber(message.topic, payload)

        self._temporary_subscribers_map[message.topic].clear()

        for pattern, key in self._permanent_subscriber_key_regexps_map.items():
            if pattern.fullmatch(message.topic):
                for subscriber in self._permanent_subscribers_map[key]:
                    subscriber(message.topic, payload)

                break

    def _request_data(
        self,
        *,
        topic_for_sending: str,
        topic_for_receiving: str,
        payload: typing.Any = None,
        timeout: datetime.timedelta = datetime.timedelta(seconds=10),
    ) -> dict | None:
        event = threading.Event()
        result = None

        def _func(topic: str, response: dict) -> None:
            nonlocal result

            result = response
            event.set()

        self._subscribe_on_topic(topic_for_receiving, _func)
        self._publish_msg(topic_for_sending, payload)

        event.wait(timeout=timeout.total_seconds())

        if not event.is_set():
            raise exceptions.ZigBeeTimeoutError

        return result

    @synchronized_method
    def _subscribe_on_topic(self, topic: str, func: typing.Callable) -> None:
        if not self._temporary_subscribers_map[topic]:
            self.mq.subscribe(topic)

        self._temporary_subscribers_map[topic].append(func)

    def _publish_msg(self, topic: str, payload: typing.Any = None) -> None:
        if payload is not None:
            payload = json.dumps(payload)

        msg_info: MQTTMessageInfo = self.mq.publish(topic, payload=payload)
        msg_info.wait_for_publish(timeout=10)

    @synchronized_method
    def _subscribe_on_availability(self) -> None:
        def _func(topic: str, payload: dict) -> None:
            friendly_name = topic.split('/')[1]
            is_available = payload['state'] == 'online'
            self._availability_map[friendly_name] = is_available

            if friendly_name in self._devices_map:
                self._devices_map[friendly_name].is_available = is_available
            else:
                self._devices_map[friendly_name] = ZigBeeDevice(
                    friendly_name=friendly_name,
                    ieee_address=friendly_name,
                )

        common_topic = f'{self.base_topic}/+/availability'
        self._permanent_subscriber_key_regexps_map[re.compile(common_topic.replace('+', '.*'))] = common_topic
        self._permanent_subscribers_map[common_topic].append(_func)

    @synchronized_method
    def _set_devices(self, topic: str, payload: list) -> None:
        for raw_device in payload:
            friendly_name = raw_device['friendly_name']

            device = ZigBeeDevice(
                friendly_name=friendly_name,
                ieee_address=raw_device['ieee_address'],
                power_source=raw_device.get('power_source'),
                is_supported=raw_device.get('supported'),
                is_disabled=raw_device.get('disabled'),
                is_available=self._availability_map.get(friendly_name),
                type=raw_device.get('type'),
            )

            if device.friendly_name in self._devices_map:
                for field in dataclasses.fields(device):
                    setattr(self._devices_map[device.friendly_name], field.name, getattr(device, field.name))
            else:
                self._devices_map[device.friendly_name] = device


class BaseZigBeeDevice(BaseSmartDevice, abc.ABC):
    device_type = SmartDeviceType.ZIGBEE
    zig_bee: ZigBee

    def __init__(self, friendly_name: str, *, zig_bee: ZigBee) -> None:
        self.friendly_name = friendly_name
        self.zig_bee = zig_bee
