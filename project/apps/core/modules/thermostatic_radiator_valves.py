import datetime
import math

from libs.casual_utils.parallel_computing import synchronized_method
from libs.casual_utils.time import get_current_time
from libs.task_queue import IntervalTask, TaskPriorities
from libs.zigbee.devices import BaseZigBeeDevice, ZigBeeDevice

from ....config import SmartDeviceNames
from ...common import interface
from ...signals.models import Signal
from ..base import BaseModule, Command
from ..signals.mixins import ZigBeeDeviceBatteryCheckerMixin
from ..signals.temp_hum_sensors import TEMPERATURE_SUFFIX


__all__ = ('ThermostaticRadiatorValvesHandler',)


@interface.module(
    title='ThermostaticRadiatorValves',
    description='Controls radiator valves and temporarily disables heating.',
    commands=(
            interface.Command(
                '/trv',
                'disable',
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
    device_names = SmartDeviceNames.THERMOSTATIC_RADIATOR_VALVES
    battery_min_level = 30

    def __init__(self, *, context) -> None:
        # Initialize before BaseModule registers tasks and event handlers.
        self._sensors: tuple[ZigBeeDevice, ...] = tuple(
            context.smart_devices_map[name]
            for name in self.device_names
        )
        self._device_names_to_init = set(self.device_names)
        self._pending_mode_updates: set[str] = set()
        self._disabled_until: datetime.datetime | None = None
        self._mode_generation = 0
        self._stopped = False

        # Compatibility with the existing signal-handler battery mixin.
        self._context = context
        self._messenger = context.messenger
        self._state = context.state
        self._task_queue = context.task_queue

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

        if command.first_arg == 'disable':
            try:
                hours = float(command.second_arg)
                if not math.isfinite(hours) or hours <= 0:
                    raise ValueError

                duration = datetime.timedelta(hours=hours)
                deadline = get_current_time() + duration
            except (TypeError, ValueError, OverflowError):
                self.messenger.send_message(
                    'Usage: /trv disable <positive number of hours>',
                )
                return True

            self._set_disabled_until(deadline)
            return True

        if command.first_arg == 'enable':
            self._set_disabled_until(None)
            return True

        return False

    @synchronized_method
    def _set_disabled_until(
            self,
            deadline: datetime.datetime | None,
    ) -> None:
        if self._stopped:
            return

        self._disabled_until = deadline
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
            message = (
                'Radiator valves requested to remain off until '
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

        if self._expire_disable_period():
            errors = self._apply_pending_mode_updates()
            if errors:
                raise ExceptionGroup(
                    'Failed to resume radiator valves',
                    errors,
                )

    def _expire_disable_period(self) -> bool:
        if (
                self._disabled_until is None
                or get_current_time() < self._disabled_until
        ):
            return False

        self._disabled_until = None
        self._mode_generation += 1
        self._pending_mode_updates.update(self.device_names)
        return True

    def _desired_system_mode(self) -> str:
        return 'off' if self._disabled_until is not None else 'auto'

    def _apply_pending_mode_updates(self) -> list[Exception]:
        errors = []

        for device_name in tuple(self._pending_mode_updates):
            sensor = self.context.smart_devices_map[device_name]

            try:
                sensor.set({
                    'system_mode': self._desired_system_mode(),
                })
            except Exception as exc:
                errors.append(exc)
            else:
                self._pending_mode_updates.discard(device_name)

        return errors

    @synchronized_method
    def process_by_interval(self) -> None:
        if self._stopped:
            return

        self._expire_disable_period()
        errors = []

        for device_name in tuple(self._device_names_to_init):
            sensor = self.context.smart_devices_map[device_name]

            try:
                sensor.set(self._get_initial_state())
                self._configure_reporting(sensor)
            except Exception as exc:
                errors.append(exc)
            else:
                self._device_names_to_init.discard(device_name)

        errors.extend(self._apply_pending_mode_updates())

        current_temperature = self._get_current_temperature()

        if current_temperature is not None:
            for sensor in self._sensors:
                try:
                    sensor.set({
                        'external_temperature_input': current_temperature,
                    })
                except Exception as exc:
                    errors.append(exc)

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

    def _get_initial_state(self) -> dict:
        day_temperature = 23
        night_temperature = 21
        daily_schedule = (
            f'00:00/{night_temperature} '
            f'07:00/{day_temperature} '
            f'23:30/{night_temperature}'
        )

        settings = {
            'system_mode': self._desired_system_mode(),
            'temperature_sensor_select': 'remote_temperature',
            'smart_temperature_control': False,
            'temperature_accuracy': -1,
            'valve_opening_degree': 100,
            'valve_closing_degree': 100,
            'open_window': 'OFF',
            'frost_protection_temperature': 10,
            'child_lock': 'UNLOCK',
        }

        temperature = self._get_current_temperature()
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
    def _get_current_temperature() -> float | None:
        now = get_current_time()
        value = Signal.get_one_aggregated(
            f'{SmartDeviceNames.TEMP_HUM_SENSOR_BEDROOM}{TEMPERATURE_SUFFIX}',
            datetime_range=(
                now - datetime.timedelta(minutes=5),
                now,
            ),
        )
        return round(value, 1) if value is not None else None

    @staticmethod
    def _configure_reporting(sensor: BaseZigBeeDevice) -> None:
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

        for setting in settings:
            if not sensor.config_reporting({
                'endpoint': 1,
                'cluster': 'hvacThermostat',
                **setting,
            }):
                raise RuntimeError(
                    f'Cannot configure reporting for '
                    f'{sensor.friendly_name}: {setting["attribute"]}',
                )

    @synchronized_method
    def disable(self) -> None:
        # Lifecycle shutdown, not the temporary heating-disable command.
        self._stopped = True
        self._mode_generation += 1

        for sensor in self._sensors:
            sensor.unsubscribe()

        super().disable()
