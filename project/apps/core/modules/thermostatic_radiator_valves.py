import datetime
import logging
import math

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.task_queue import IntervalTask, TaskPriorities
from libs.zigbee.devices import ZigBeeDevice
from libs.zigbee.exceptions import ZigBeeError, ZigBeeTimeoutError

from ....config import SmartDeviceNames
from ...common import interface
from ...signals.models import Signal
from ..base import BaseModule, Command
from ..constants import HEATING_BOOSTED_UNTIL, HEATING_PAUSED_UNTIL
from ..signals.mixins import ZigBeeDeviceBatteryCheckerMixin
from ..signals.temp_hum_sensors import TEMPERATURE_SUFFIX


__all__ = ('ThermostaticRadiatorValvesHandler',)


@interface.module(
    title='ThermostaticRadiatorValves',
    description='Pause heating or boost to 30 °C for positive hours, then resume the weekly schedule.',
    commands=(
            interface.Command(
                '/trv',
                'disable',
                interface.Value('hours', python_type=float),
            ),
            interface.Command(
                '/trv',
                'boost',
                interface.Value('hours', python_type=float),
            ),
            interface.Command('/trv', 'enable'),
    ),
)
class ThermostaticRadiatorValvesHandler(
    ZigBeeDeviceBatteryCheckerMixin,
    BaseModule,
):
    task_interval = datetime.timedelta(minutes=1)
    reporting_retry_interval = datetime.timedelta(minutes=30)
    device_names = SmartDeviceNames.THERMOSTATIC_RADIATOR_VALVES
    battery_min_level = 30

    def __init__(self, *, context) -> None:
        # Initialize before BaseModule registers tasks and event handlers.
        self._sensors: tuple[ZigBeeDevice, ...] = tuple(
            context.smart_devices_map[name]
            for name in self.device_names
        )
        self._device_names_to_init = set(self.device_names)
        self._reporting_retry_at = dict.fromkeys(self.device_names, get_current_time())
        self._pending_mode_updates: set[str] = set()
        self._override_until: datetime.datetime | None = None
        self._override_mode: str | None = None
        self._mode_generation = 0
        self._stopped = False

        # Compatibility with the existing signal-handler battery mixin.
        self._context = context
        self._messenger = context.messenger
        self._state = context.state
        self._task_queue = context.task_queue

        missing_mappings = self.device_names - SmartDeviceNames.TEMP_SENSORS_FOR_THERMOSTATIC_RADIATOR_VALVES.keys()
        if missing_mappings:
            raise ValueError(f'Missing temperature sensor mappings for: {sorted(missing_mappings)}')

        super().__init__(context=context)

        for sensor in self._sensors:
            sensor.subscribe_on_update(
                lambda state, device_name=sensor.friendly_name: (
                    self.task_queue.put(
                        self._process_update,
                        kwargs={
                            'state': dict(state),
                            'device_name': device_name,
                            'received_at': get_current_time(),
                        },
                        priority=TaskPriorities.HIGH,
                    )
                ),
            )

    def get_initial_state(self) -> dict:
        return {
            **super().get_initial_state(),
            HEATING_PAUSED_UNTIL: None,
            HEATING_BOOSTED_UNTIL: None,
        }

    def init_repeatable_tasks(self) -> tuple[IntervalTask, ...]:
        return (
            *super().init_repeatable_tasks(),
            IntervalTask(
                target=self.process_by_interval,
                priority=TaskPriorities.MEDIUM,
                interval=self.task_interval,
                run_after=(
                        datetime.datetime.now()
                        + datetime.timedelta(seconds=10)
                ),
            ),
        )

    def process_command(self, command: Command) -> bool:
        if command.name != '/trv':
            return False

        usage = 'Usage: /trv disable <positive hours>, /trv boost <positive hours>, or /trv enable'
        if command.first_arg in {'disable', 'boost'}:
            try:
                if len(command.args) != 2 or command.kwargs:
                    raise ValueError
                hours = float(command.second_arg)
                if not math.isfinite(hours) or hours <= 0:
                    raise ValueError

                duration = datetime.timedelta(hours=hours)
                if duration <= datetime.timedelta():
                    raise ValueError
                deadline = get_current_time() + duration
            except (TypeError, ValueError, OverflowError):
                self.messenger.send_message(usage)
                return True

            self._set_override('off' if command.first_arg == 'disable' else 'heat', deadline)
            return True

        if command.first_arg == 'enable' and len(command.args) == 1 and not command.kwargs:
            self._set_override(None, None)
            return True

        self.messenger.send_message(usage)
        return True

    @synchronized_method
    def _set_override(
            self,
            mode: str | None,
            deadline: datetime.datetime | None,
    ) -> None:
        if self._stopped:
            return

        self._override_mode = mode
        self._override_until = deadline
        self.state[HEATING_PAUSED_UNTIL] = deadline if mode == 'off' else None
        self.state[HEATING_BOOSTED_UNTIL] = deadline if mode == 'heat' else None
        self._mode_generation += 1
        self._pending_mode_updates.update(self.device_names)

        if deadline is not None:
            self.task_queue.put(
                self._resume_if_due,
                kwargs={'generation': self._mode_generation},
                run_after=(
                        datetime.datetime.now()
                        + max(
                    deadline - get_current_time(),
                    datetime.timedelta(),
                )
                ),
                priority=TaskPriorities.MEDIUM,
            )

        errors = self._apply_pending_mode_updates()

        if deadline is None:
            message = 'Radiator valves requested to resume their schedule.'
        else:
            request = 'heat to 30 °C' if mode == 'heat' else 'remain off'
            message = (
                f'Radiator valves requested to {request} until '
                f'{deadline:%Y-%m-%d %H:%M:%S}.'
            )

        if errors:
            message += (
                '\nSome valves could not be updated; '
                'the controller will retry every minute.'
            )

        self.messenger.send_message(message)

    @synchronized_method
    def _resume_if_due(self, *, generation: int) -> None:
        if self._stopped or generation != self._mode_generation:
            return

        if self._expire_override_period():
            errors = self._apply_pending_mode_updates()
            if errors:
                raise ExceptionGroup(
                    'Failed to resume radiator valves',
                    errors,
                )

    def _expire_override_period(self) -> bool:
        if (
                self._override_until is None
                or get_current_time() < self._override_until
        ):
            return False

        self._override_until = None
        self._override_mode = None
        self.state[HEATING_PAUSED_UNTIL] = None
        self.state[HEATING_BOOSTED_UNTIL] = None
        self._mode_generation += 1
        self._pending_mode_updates.update(self.device_names)
        return True

    def _desired_mode_settings(self) -> dict:
        if self._override_mode == 'heat':
            return {'system_mode': 'heat', 'occupied_heating_setpoint': 30}
        return {'system_mode': self._override_mode or 'auto'}

    def _apply_pending_mode_updates(self) -> list[Exception]:
        errors = []

        for device_name in tuple(self._pending_mode_updates):
            sensor = self.context.smart_devices_map[device_name]

            try:
                sensor.set(self._desired_mode_settings())
            except Exception as exc:
                errors.append(exc)
            else:
                self._pending_mode_updates.discard(device_name)

        return errors

    @synchronized_method
    def process_by_interval(self) -> None:
        if self._stopped:
            return

        self._expire_override_period()
        errors = []

        for device_name in tuple(self._device_names_to_init):
            sensor = self.context.smart_devices_map[device_name]

            try:
                sensor.set(self._get_initial_state(device_name))
            except Exception as exc:
                errors.append(exc)
            else:
                self._device_names_to_init.discard(device_name)

        errors.extend(self._apply_pending_mode_updates())

        for sensor in self._sensors:
            try:
                current_temperature = self._get_current_temperature(sensor.friendly_name)

                if current_temperature is not None:
                    sensor.set({
                        'external_temperature_input': current_temperature,
                    })
            except Exception as exc:
                errors.append(exc)

        # Reporting support varies by device/firmware. It must not cause the
        # schedule to be reinitialized or prevent regular temperature updates.
        for device_name, retry_at in tuple(self._reporting_retry_at.items()):
            if device_name in self._device_names_to_init or get_current_time() < retry_at:
                continue

            sensor = self.context.smart_devices_map[device_name]
            if self._configure_reporting(sensor):
                del self._reporting_retry_at[device_name]
                logging.info('Reporting configured for %s', device_name)
            else:
                self._reporting_retry_at[device_name] = get_current_time() + self.reporting_retry_interval
                logging.warning(
                    'Reporting setup incomplete for %s; retrying in %s. '
                    'Valve control will continue; telemetry may be incomplete.',
                    device_name,
                    self.reporting_retry_interval,
                )

        if errors:
            raise ExceptionGroup(
                f'{self.__class__.__name__} Error',
                errors,
            )

    @synchronized_method
    def _process_update(
            self,
            *,
            state: dict,
            device_name: str,
            received_at: datetime.datetime,
    ) -> None:
        if self._stopped:
            return

        running_state = state.get('running_state')

        if running_state is not None:
            Signal.add(
                signal_type=f'{device_name}:state',
                value=int(running_state == 'heat'),
                received_at=received_at,
            )

        battery = state.get('battery')
        if battery is not None:
            self._check_battery(battery, device_name=device_name)

    def _get_initial_state(self, for_device_name: str) -> dict:
        day_temperature = 23
        night_temperature = 21
        daily_schedule = (
            f'00:00/{night_temperature} '
            f'07:00/{day_temperature} '
            f'23:30/{night_temperature}'
        )

        settings = {
            **self._desired_mode_settings(),
            'temperature_sensor_select': 'remote_temperature',
            'smart_temperature_control': False,
            'temperature_accuracy': -1,
            'valve_opening_degree': 100,
            'valve_closing_degree': 100,
            'open_window': 'OFF',
            'frost_protection_temperature': 10,
            'child_lock': 'UNLOCK',
        }

        temperature = self._get_current_temperature(for_device_name)
        if temperature is not None:
            settings['external_temperature_input'] = temperature

        for day in (
                'monday',
                'tuesday',
                'wednesday',
                'thursday',
                'friday',
                'saturday',
                'sunday',
        ):
            settings[f'weekly_schedule_{day}'] = daily_schedule

        return settings

    @staticmethod
    def _get_current_temperature(for_device_name: str) -> float | None:
        temp_sensor_name = SmartDeviceNames.TEMP_SENSORS_FOR_THERMOSTATIC_RADIATOR_VALVES[for_device_name]
        now = get_current_time()
        value = Signal.get_one_aggregated(
            f'{temp_sensor_name}{TEMPERATURE_SUFFIX}',
            datetime_range=(
                now - datetime.timedelta(minutes=5),
                now,
            ),
        )
        return round(value, 1) if value is not None and math.isfinite(value) else None

    @staticmethod
    def _configure_reporting(sensor: ZigBeeDevice) -> bool:
        settings = (
            {
                'attribute': 'localTemp',
                'minimum_report_interval': 60,
                'maximum_report_interval': 3600,
                'reportable_change': 20,  # 0.2 °C
            },
            {
                'attribute': 'occupiedHeatingSetpoint',
                'minimum_report_interval': 10,
                'maximum_report_interval': 3600,
                'reportable_change': 10,  # 0.1 °C
            },
            {
                'attribute': 'systemMode',
                'minimum_report_interval': 10,
                'maximum_report_interval': 3600,
            },
        )

        configured = True
        for setting in settings:
            try:
                accepted = sensor.config_reporting({
                    'endpoint': 1,
                    'cluster': 'hvacThermostat',
                    **setting,
                })
            except (ZigBeeError, ZigBeeTimeoutError, OSError):
                logging.warning(
                    'Reporting request failed for %s: hvacThermostat.%s',
                    sensor.friendly_name,
                    setting['attribute'],
                    exc_info=True,
                )
                # A transport failure could affect every attribute. Retry later
                # rather than block the worker with more requests now.
                return False

            if not accepted:
                configured = False
                logging.warning(
                    'Reporting request rejected for %s: hvacThermostat.%s; '
                    'see Zigbee2MQTT response in the logs',
                    sensor.friendly_name,
                    setting['attribute'],
                )

        return configured

    @synchronized_method
    def disable(self) -> None:
        # Lifecycle shutdown, not the temporary heating-disable command.
        self._stopped = True
        self._mode_generation += 1

        for sensor in self._sensors:
            sensor.unsubscribe()

        super().disable()
