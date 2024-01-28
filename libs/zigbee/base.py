import itertools
import json
import logging
import re
import threading
import typing
from collections import defaultdict

from paho.mqtt.client import Client, MQTTMessage, MQTTMessageInfo, MQTTv5

from . import exceptions
from ..casual_utils.parallel_computing import synchronized_method


class ZigBee:
    _base_topic: str = 'zigbee2mqtt'
    _mq_host: str
    _mq_port: int
    _mq: Client | None = None
    _temporary_subscribers_map: dict[str, list[typing.Callable]]
    _permanent_subscribers_map: dict[str, list[typing.Callable]]
    _permanent_subscriber_key_regexps_map: dict[re.Pattern, str]
    _devices: list[dict[str, typing.Any]]
    _availability_map: dict[str, bool]
    _lock: threading.RLock

    def __init__(self, *, mq_host: str, mq_port: int) -> None:
        self._lock = threading.RLock()

        self._temporary_subscribers_map = defaultdict(list)
        self._permanent_subscribers_map = defaultdict(list)
        self._availability_map = {}
        self._permanent_subscriber_key_regexps_map = {}
        self._devices = []

        def _set_devices(topic: str, payload: list) -> None:
            self._devices = payload

        self._permanent_subscribers_map[f'{self._base_topic}/bridge/devices'].append(_set_devices)

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
    def devices(self) -> list[dict[str, typing.Any]]:
        return self._devices

    def set(self, friendly_name: str, payload: dict) -> None:
        self._publish_msg(f'{self._base_topic}/{friendly_name}/set', payload)

    def get_state(self, friendly_name: str) -> typing.Any:
        return self._request_data(
            topic_for_sending=f'{self._base_topic}/{friendly_name}/get',
            topic_for_receiving=f'{self._base_topic}/{friendly_name}',
            payload={'state': ''},
        )

    def is_health(self) -> bool:
        name = 'health_check'

        response = self._request_data(
            topic_for_sending=f'{self._base_topic}/bridge/request/{name}',
            topic_for_receiving=f'{self._base_topic}/bridge/response/{name}',
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
    def subscribe_on_topic(self,
                           topic: str,
                           func: typing.Callable) -> None:
        if '+' in topic:
            self._permanent_subscriber_key_regexps_map[re.compile(topic.replace('+', '.*'))] = topic

        self._permanent_subscribers_map[topic].append(func)
        self.mq.subscribe(topic)

        logging.info(f'ZigBee: {func} subscribes on {topic}')
        logging.info(f'ZigBee: {self._permanent_subscriber_key_regexps_map = }')
        logging.info(f'ZigBee: {self._permanent_subscribers_map = }')

    @synchronized_method
    def open(self) -> None:
        if self._mq is not None:
            raise exceptions.ZigBeeError('MQ was created.')

        mq = Client('mqtt5_client', protocol=MQTTv5)
        mq.on_message = self._on_message
        mq.on_disconnect = self._on_disconnect
        mq.connect(self._mq_host, port=self._mq_port)
        mq.loop_start()

        for topic in itertools.chain(self._temporary_subscribers_map, self._permanent_subscribers_map):
            logging.info(f'ZigBee: Subscribe on {topic}')
            mq.subscribe(topic)

        self._mq = mq

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
        if not message.topic.startswith(f'{self._base_topic}/'):
            return

        payload = json.loads(message.payload.decode())

        for subscriber in itertools.chain(
            self._temporary_subscribers_map[message.topic],
            self._permanent_subscribers_map[message.topic],
        ):
            logging.info(f'ZigBee: Processed temp message {message.topic} ({payload}) for {subscriber}')
            subscriber(message.topic, payload)

        self._temporary_subscribers_map[message.topic].clear()

        for pattern, key in self._permanent_subscriber_key_regexps_map.items():
            if pattern.fullmatch(message.topic):
                for subscriber in self._permanent_subscribers_map[key]:
                    logging.info(f'ZigBee: Processed temp message {message.topic} ({payload}) for {subscriber}')
                    subscriber(message.topic, payload)

                break
        else:
            # If we don't find subscribers, then we need to unsubscribe from the topic:
            if not self._permanent_subscribers_map[message.topic]:
                logging.info(f'ZigBee: Unsubscribe from {message.topic}')
                self.mq.unsubscribe(message.topic)

    def _request_data(self, *,
                      topic_for_sending: str,
                      topic_for_receiving: str,
                      payload: typing.Any = None,
                      timeout: int = 10) -> dict | None:
        event = threading.Event()
        result = None

        def _func(topic: str, response: dict) -> None:
            nonlocal result

            result = response
            event.set()

        self._subscribe_on_topic(topic_for_receiving, _func)
        self._publish_msg(topic_for_sending, payload)

        event.wait(timeout=timeout)

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
            self._availability_map[friendly_name] = payload['state'] == 'online'

        common_topic = f'{self._base_topic}/+/availability'
        self._permanent_subscriber_key_regexps_map[
            re.compile(common_topic.replace('+', '.*'))
        ] = common_topic
        self._permanent_subscribers_map[common_topic].append(_func)
