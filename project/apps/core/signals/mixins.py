class ZigBeeDeviceBatteryCheckerMixin:
    battery_min_level: int = 50

    def _check_battery(self, battery: int | None, *, device_name: str) -> None:
        if battery is None:
            return

        if battery <= self.battery_min_level:
            self._messenger.warning(f'Battery is low ({battery}%)!\nSensor: "{device_name}"')
