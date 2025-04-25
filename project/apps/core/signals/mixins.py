class ZigBeeDeviceBatteryCheckerMixin:
    def _check_battery(self, battery: int, *, device_name: str) -> None:
        if battery < 30:
            self._messenger.warning(f'Battery is low ({battery}%)!\nSensor: "{device_name}"')
