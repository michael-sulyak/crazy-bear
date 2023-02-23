import datetime
import json
import threading
import typing
from collections import defaultdict

from paho.mqtt.client import Client, MQTTMessage, MQTTMessageInfo, MQTTv5

from . import constants, exceptions
from ..casual_utils.parallel_computing import synchronized_method


class ZigBee:
    _mq_host: str
    _mq_port: int
    _mq: typing.Optional[Client] = None
    _subscribers_map: typing.Dict[str, typing.List[typing.Callable]]
    _permanent_subscribers_map: typing.Dict[str, typing.List[typing.Callable]]
    _topic_results_map: typing.Dict[str, typing.Any]
    _lock: threading.RLock

    def __init__(self, *, mq_host: str, mq_port: int) -> None:
        self._lock = threading.RLock()

        self._mq_host = mq_host
        self._mq_port = mq_port

    @property
    @synchronized_method
    def mq(self) -> Client:
        if self._mq is None:
            self.open()

        return self._mq

    @property
    @synchronized_method
    def devices(self) -> typing.Dict[str, typing.Any]:
        return self._topic_results_map[constants.ZigBeeTopics.DEVICES]

    def set(self, friendly_name: str, payload: dict) -> None:
        self._publish_msg(f'zigbee2mqtt/{friendly_name}/set', payload)

    def get(self, friendly_name: str) -> typing.Any:
        return self._request_data(
            topic_for_sending=f'zigbee2mqtt/{friendly_name}/get',
            topic_for_receiving=f'zigbee2mqtt/{friendly_name}',
            payload={'state': ''},
        )

    def is_health(self) -> bool:
        name = 'health_check'
        response = self._request_data(
            topic_for_sending=f'zigbee2mqtt/bridge/request/{name}',
            topic_for_receiving=f'zigbee2mqtt/bridge/response/{name}',
        )
        return response['status'] == 'ok' and response['data']['healthy']

    def rename_device(self, friendly_name_or_ieee_address: str, new_friendly_name: str) -> bool:
        name = 'device/rename'
        response = self._request_data(
            topic_for_sending=f'zigbee2mqtt/bridge/request/{name}',
            topic_for_receiving=f'zigbee2mqtt/bridge/response/{name}',
            payload={'from': friendly_name_or_ieee_address, 'to': new_friendly_name},
        )
        return response['status'] == 'ok'

    @synchronized_method
    def subscribe_on_topic(self,
                           topic: str,
                           func: typing.Callable) -> None:
        self._permanent_subscribers_map[topic].append(func)
        self._mq.subscribe(topic)

    @synchronized_method
    def open(self) -> None:
        if self._mq is not None:
            raise exceptions.ZigBeeError('MQ was created.')

        mq = Client('mqtt5_client', protocol=MQTTv5)
        mq.on_message = self._on_message
        mq.on_disconnect = self._on_disconnect
        mq.connect(self._mq_host, port=self._mq_port)
        mq.loop_start()

        self._subscribers_map = defaultdict(list)
        self._permanent_subscribers_map = defaultdict(list)
        self._topic_results_map = {
            constants.ZigBeeTopics.DEVICES: [],
        }

        for topic in self._topic_results_map:
            mq.subscribe(topic)

        self._mq = mq

    @synchronized_method
    def close(self) -> None:
        if self.mq is None:
            raise exceptions.ZigBeeError('MQ wasn\'t created.')

        self.mq.loop_stop()

    @synchronized_method
    def _on_disconnect(self, client: Client, userdata: typing.Any, rc) -> None:
        self._mq = None

    @synchronized_method
    def _on_message(self, client: Client, userdata: typing.Any, message: MQTTMessage) -> None:
        if (
                message.topic.startswith('zigbee2mqtt/')
                and not self._subscribers_map[message.topic]
                and not self._permanent_subscribers_map[message.topic]
                and message.topic not in self._topic_results_map
        ):
            return

        payload = json.loads(message.payload.decode())

        for subscriber in self._subscribers_map[message.topic]:
            subscriber(payload)

        if self._subscribers_map[message.topic]:
            self.mq.unsubscribe(message.topic)
            self._subscribers_map[message.topic].clear()

        for subscriber in self._permanent_subscribers_map[message.topic]:
            subscriber(payload)

        if message.topic in self._topic_results_map:
            self._topic_results_map[message.topic] = payload

    @synchronized_method
    def _subscribe_on_topic(self,
                            topic: str,
                            func: typing.Callable, *,
                            ttl: int = 10) -> None:
        subscribed_at = datetime.datetime.now()

        def _decorated_func(*args, **kwargs) -> None:
            if (subscribed_at - datetime.datetime.now()).total_seconds() > ttl:
                return

            func(*args, **kwargs)

        if not self._subscribers_map[topic]:
            self.mq.subscribe(topic)

        self._subscribers_map[topic].append(_decorated_func)

    def _request_data(self, *,
                      topic_for_sending: str,
                      topic_for_receiving: str,
                      payload: typing.Any = None,
                      timeout: int = 10) -> typing.Optional[dict]:
        event = threading.Event()
        result = None

        def _func(response: dict) -> None:
            nonlocal result

            result = response
            event.set()

        self._subscribe_on_topic(topic_for_receiving, _func, ttl=timeout + 10)
        self._publish_msg(topic_for_sending, payload)

        event.wait(timeout=timeout)

        if not event.is_set():
            raise exceptions.ZigBeeTimeoutError

        return result

    def _publish_msg(self, topic: str, payload: typing.Any = None) -> None:
        if payload is not None:
            payload = json.dumps(payload)

        msg_info: MQTTMessageInfo = self.mq.publish(topic, payload=payload)
        msg_info.wait_for_publish(timeout=10)