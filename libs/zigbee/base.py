import dataclasses
import datetime
import json
import logging
import threading
import typing
import uuid
from collections import defaultdict

from paho.mqtt.client import (
    Client,
    MQTTMessage,
    MQTTMessageInfo,
    MQTTv5,
    topic_matches_sub,
)
from paho.mqtt.enums import CallbackAPIVersion, MQTTErrorCode

from project.apps.common.exceptions import Shutdown

from . import exceptions
from .constants import COORDINATOR_FRIENDLY_NAME, ZigBeePowerSources


Subscriber = typing.Callable[[str, typing.Any], None]


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
    base_topic = 'zigbee2mqtt'
    reporting_config_topic = (
        f'{base_topic}/bridge/request/device/reporting/configure'
    )

    def __init__(self, *, mq_host: str, mq_port: int) -> None:
        self._lock = threading.RLock()
        self._connected = threading.Event()

        self._mq_host = mq_host
        self._mq_port = mq_port
        self._mq: Client | None = None
        self._is_opened = False
        self._network_thread_id: int | None = None

        self._temporary_subscribers_map: dict[
            str, list[Subscriber],
        ] = defaultdict(list)
        self._permanent_subscribers_map: dict[
            str, list[Subscriber],
        ] = defaultdict(list)

        self._devices_map: dict[str, ZigBeeDevice] = {}
        self._availability_map: dict[str, bool] = {}

        # Kept subscribed for this connection, even when the last temporary
        # listener is removed. This avoids subscribe/unsubscribe races.
        self._subscribed_topics: set[str] = set()

        self._permanent_subscribers_map[
            f'{self.base_topic}/bridge/devices'
        ].append(self._set_devices)

        self._subscribe_on_availability()

    @property
    def permanent_subscribers_map(
            self,
    ) -> dict[str, tuple[Subscriber, ...]]:
        with self._lock:
            return {
                topic: tuple(callbacks)
                for topic, callbacks in self._permanent_subscribers_map.items()
                if callbacks
            }

    @property
    def temporary_subscribers_map(
            self,
    ) -> dict[str, tuple[Subscriber, ...]]:
        with self._lock:
            return {
                topic: tuple(callbacks)
                for topic, callbacks in self._temporary_subscribers_map.items()
                if callbacks
            }

    @property
    def availability_map(self) -> dict[str, bool]:
        with self._lock:
            return self._availability_map.copy()

    @property
    def devices(self) -> tuple[ZigBeeDevice, ...]:
        with self._lock:
            return tuple(self._devices_map.values())

    @property
    def mq(self) -> Client:
        self.open()

        with self._lock:
            assert self._mq is not None
            return self._mq

    def open(self) -> None:
        with self._lock:
            if self._mq is not None:
                return

            client = Client(
                callback_api_version=CallbackAPIVersion.VERSION2,
                client_id=f'zigbee-{uuid.uuid4().hex}',
                protocol=MQTTv5,
                reconnect_on_failure=True,
            )
            client.on_message = self._on_message
            client.on_connect = self._on_connect
            client.on_disconnect = self._on_disconnect

            self._mq = client
            self._is_opened = True

            try:
                client.connect(self._mq_host, port=self._mq_port)
                client.loop_start()
            except Exception:
                self._mq = None
                self._is_opened = False
                self._connected.clear()
                raise

    def close(self) -> None:
        self._assert_not_network_thread('close')

        with self._lock:
            client = self._mq
            if client is None:
                return

            self._is_opened = False
            self._connected.clear()

        # Never hold the shared lock while joining the network thread.
        try:
            client.disconnect()
        finally:
            client.loop_stop()

            with self._lock:
                if self._mq is client:
                    self._mq = None
                    self._network_thread_id = None
                    self._subscribed_topics.clear()

    def set(self, friendly_name: str, payload: dict) -> None:
        self._publish_msg(
            f'{self.base_topic}/{friendly_name}/set',
            payload,
        )

    def config_reporting(
            self,
            payload: dict,
            *,
            timeout: datetime.timedelta = datetime.timedelta(minutes=1),
    ) -> bool:
        request = dict(payload)
        request.setdefault('transaction', uuid.uuid4().hex)

        response = self._request_data(
            topic_for_sending=(
                f'{self.base_topic}/bridge/request/device/reporting/configure'
            ),
            topic_for_receiving=(
                f'{self.base_topic}/bridge/response/device/reporting/configure'
            ),
            payload=request,
            timeout=timeout,
        )

        assert response is not None

        return response.get('status') == 'ok'

    def read_reporting(
            self,
            payload: dict,
            *,
            timeout: datetime.timedelta = datetime.timedelta(minutes=1),
    ) -> dict:
        request = dict(payload)
        request.setdefault('transaction', uuid.uuid4().hex)

        response = self._request_data(
            topic_for_sending=(
                f'{self.base_topic}/bridge/request/device/reporting/read'
            ),
            topic_for_receiving=(
                f'{self.base_topic}/bridge/response/device/reporting/read'
            ),
            payload=request,
            timeout=timeout,
        )

        assert response is not None
        return response

    def get_state(
            self,
            friendly_name: str,
            *,
            timeout: datetime.timedelta = datetime.timedelta(seconds=10),
    ) -> typing.Any:
        # Only supported for devices exposing a readable "state" property.
        # Device state responses do not support bridge transactions.
        return self._request_data(
            topic_for_sending=f'{self.base_topic}/{friendly_name}/get',
            topic_for_receiving=f'{self.base_topic}/{friendly_name}',
            payload={'state': ''},
            timeout=timeout,
        )

    def is_health(self) -> bool:
        response = self._request_data(
            topic_for_sending=(
                f'{self.base_topic}/bridge/request/health_check'
            ),
            topic_for_receiving=(
                f'{self.base_topic}/bridge/response/health_check'
            ),
            payload={'transaction': uuid.uuid4().hex},
        )

        assert response is not None

        return (
                response.get('status') == 'ok'
                and response.get('data', {}).get('healthy') is True
        )

    def subscribe_on_topic(
            self,
            topic: str,
            func: Subscriber,
    ) -> None:
        with self._lock:
            self._permanent_subscribers_map[topic].append(func)
            self._ensure_subscription_locked(topic)

        logging.info('ZigBee: "%s" subscribes on "%s".', func, topic)

    def subscribe_on_state(
            self,
            friendly_name: str,
            func: Subscriber,
    ) -> None:
        self.subscribe_on_topic(
            f'{self.base_topic}/{friendly_name}',
            func,
        )

    def unsubscribe_from_topic(self, topic: str) -> None:
        with self._lock:
            self._permanent_subscribers_map.pop(topic, None)
            # Keep the broker subscription until disconnect. Incoming
            # messages without local listeners are simply ignored.

    def unsubscribe_from_state(self, friendly_name: str) -> None:
        self.unsubscribe_from_topic(
            f'{self.base_topic}/{friendly_name}',
        )

    def _ensure_subscription_locked(self, topic: str) -> None:
        """Caller must hold self._lock."""
        if (
                not self._connected.is_set()
                or self._mq is None
                or topic in self._subscribed_topics
        ):
            return

        result, _ = self._mq.subscribe(topic, qos=1)

        if result != MQTTErrorCode.MQTT_ERR_SUCCESS:
            raise exceptions.ZigBeeError(
                f'Failed to subscribe to {topic!r}: {result}',
            )

        self._subscribed_topics.add(topic)

    def _on_connect(
            self,
            client: Client,
            userdata: typing.Any,
            connect_flags: typing.Any,
            reason_code: typing.Any,
            properties: typing.Any,
    ) -> None:
        with self._lock:
            self._network_thread_id = threading.get_ident()

            if reason_code.is_failure:
                logging.error(
                    'ZigBee MQTT connection failed: %s',
                    reason_code,
                )
                self._connected.clear()
                return

            self._subscribed_topics.clear()
            self._connected.set()

            topics = (
                    set(self._permanent_subscribers_map)
                    | set(self._temporary_subscribers_map)
            )

            for topic in topics:
                self._ensure_subscription_locked(topic)

    def _on_disconnect(
            self,
            client: Client,
            userdata: typing.Any,
            disconnect_flags: typing.Any,
            reason_code: typing.Any,
            properties: typing.Any,
    ) -> None:
        with self._lock:
            self._connected.clear()
            self._subscribed_topics.clear()
            is_opened = self._is_opened

        if is_opened:
            logging.warning(
                'ZigBee MQTT disconnected: %s',
                reason_code,
            )

    def _on_message(
            self,
            client: Client,
            userdata: typing.Any,
            message: MQTTMessage,
    ) -> None:
        if not message.topic.startswith(f'{self.base_topic}/'):
            return

        # Retained data must not complete a fresh request.
        is_retained = bool(message.retain)

        try:
            payload = json.loads(message.payload.decode())
        except (UnicodeDecodeError, ValueError):
            logging.warning(
                'Invalid JSON on ZigBee topic %s',
                message.topic,
            )
            return

        with self._lock:
            temporary_callbacks = (
                []
                if is_retained
                else list(
                    self._temporary_subscribers_map.get(message.topic, ()),
                )
            )

            permanent_callbacks = [
                callback
                for topic_filter, callbacks
                in self._permanent_subscribers_map.items()
                if topic_matches_sub(topic_filter, message.topic)
                for callback in callbacks
            ]

        # Important: no shared lock is held while invoking callbacks.
        for callback in temporary_callbacks + permanent_callbacks:
            try:
                callback(message.topic, payload)
            except Shutdown:
                raise
            except Exception:
                logging.exception('Failed processing ZigBee message')

    def _assert_not_network_thread(self, operation: str) -> None:
        if threading.get_ident() == self._network_thread_id:
            raise exceptions.ZigBeeError(
                f'{operation} cannot block the MQTT callback thread. '
                'Run it in a worker thread instead.',
            )

    def _request_data(
            self,
            *,
            topic_for_sending: str,
            topic_for_receiving: str,
            payload: typing.Any = None,
            timeout: datetime.timedelta = datetime.timedelta(seconds=10),
    ) -> dict | None:
        self._assert_not_network_thread('_request_data')

        client = self.mq
        timeout_seconds = timeout.total_seconds()

        if not self._connected.wait(timeout=timeout_seconds):
            raise exceptions.ZigBeeTimeoutError(
                'Timed out waiting for the MQTT connection',
            )

        event = threading.Event()
        result: dict | None = None

        transaction = (
            payload.get('transaction')
            if isinstance(payload, dict)
            else None
        )

        def receive_response(topic: str, response: typing.Any) -> None:
            nonlocal result

            if not isinstance(response, dict):
                return

            if (
                    transaction is not None
                    and response.get('transaction') != transaction
            ):
                return

            if event.is_set():
                return

            result = response
            event.set()

        self._subscribe_on_topic(
            topic_for_receiving,
            receive_response,
        )

        try:
            # SUBSCRIBE and PUBLISH are queued in order on the same client.
            # A subscription rejection is not separately handled here;
            # it will cause this request to time out.
            self._publish_msg(
                topic_for_sending,
                payload,
                client=client,
            )

            if not event.wait(timeout=timeout_seconds):
                raise exceptions.ZigBeeTimeoutError(
                    f'Timed out waiting for {topic_for_receiving!r}; '
                    f'transaction={transaction!r}',
                )

            return result
        finally:
            self._remove_temporary_subscriber(
                topic_for_receiving,
                receive_response,
            )

    def _subscribe_on_topic(
            self,
            topic: str,
            func: Subscriber,
    ) -> None:
        with self._lock:
            self._temporary_subscribers_map[topic].append(func)

            try:
                self._ensure_subscription_locked(topic)
            except Exception:
                self._temporary_subscribers_map[topic].remove(func)

                if not self._temporary_subscribers_map[topic]:
                    del self._temporary_subscribers_map[topic]

                raise

    def _remove_temporary_subscriber(
            self,
            topic: str,
            func: Subscriber,
    ) -> None:
        with self._lock:
            callbacks = self._temporary_subscribers_map.get(topic)

            if callbacks is None:
                return

            if func in callbacks:
                callbacks.remove(func)

            if not callbacks:
                del self._temporary_subscribers_map[topic]

    def _publish_msg(
            self,
            topic: str,
            payload: typing.Any = None,
            *,
            client: Client | None = None,
    ) -> None:
        if payload is not None:
            payload = json.dumps(payload)

        if client is None:
            client = self.mq

        msg_info: MQTTMessageInfo = client.publish(
            topic,
            payload=payload,
            qos=1,
            retain=False,
        )

        if msg_info.rc != MQTTErrorCode.MQTT_ERR_SUCCESS:
            raise exceptions.ZigBeeError(
                f'Failed to publish to {topic!r}: {msg_info.rc}',
            )

        # Publishing is allowed inside an MQTT callback, but waiting there
        # would block the network thread responsible for the acknowledgement.
        if threading.get_ident() == self._network_thread_id:
            return

        msg_info.wait_for_publish(timeout=10)

        if not msg_info.is_published():
            raise exceptions.ZigBeeTimeoutError(
                f'Timed out publishing to {topic!r}',
            )

    def _subscribe_on_availability(self) -> None:
        def receive_availability(
                topic: str,
                payload: typing.Any,
        ) -> None:
            if not isinstance(payload, dict):
                return

            prefix = f'{self.base_topic}/'
            suffix = '/availability'
            friendly_name = topic[len(prefix):-len(suffix)]
            is_available = payload.get('state') == 'online'

            with self._lock:
                self._availability_map[friendly_name] = is_available

                device = self._devices_map.get(friendly_name)

                if device is None:
                    device = ZigBeeDevice(
                        friendly_name=friendly_name,
                        ieee_address=friendly_name,
                    )
                    self._devices_map[friendly_name] = device

                device.is_available = is_available

        # "#" also supports friendly names containing "/".
        self._permanent_subscribers_map[
            f'{self.base_topic}/#'
        ].append(self._availability_message_filter(receive_availability))

    @staticmethod
    def _availability_message_filter(
            callback: Subscriber,
    ) -> Subscriber:
        def filtered(topic: str, payload: typing.Any) -> None:
            if topic.endswith('/availability'):
                callback(topic, payload)

        return filtered

    def _set_devices(
            self,
            topic: str,
            payload: typing.Any,
    ) -> None:
        if not isinstance(payload, list):
            return

        with self._lock:
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

                existing = self._devices_map.get(friendly_name)

                if existing is None:
                    self._devices_map[friendly_name] = device
                else:
                    for field in dataclasses.fields(device):
                        setattr(
                            existing,
                            field.name,
                            getattr(device, field.name),
                        )
