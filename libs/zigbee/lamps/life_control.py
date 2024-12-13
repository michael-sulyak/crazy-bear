import datetime
import functools
import threading
import typing
from time import sleep

from ...casual_utils.parallel_computing import synchronized_method
from ..devices import BaseZigBeeDevice


__all__ = ('LCSmartLamp',)


def method_with_transition(func: typing.Callable) -> typing.Callable:
    @functools.wraps(func)
    def wrap_func(self, *args, **kwargs) -> typing.Any:
        time_to_sleep = (self._can_run_after - datetime.datetime.now()).total_seconds()

        if time_to_sleep > 0:
            sleep(time_to_sleep)

        result = func(self, *args, **kwargs)

        self._can_run_after = datetime.datetime.now() + datetime.timedelta(seconds=kwargs.get('transition', 0))

        return result

    return wrap_func


class LCSmartLamp(BaseZigBeeDevice):
    """
    This class is made to support LifeControl MCLH-01.

    Note: MCLH-01 has unstable behaviour in some cases.
    """

    color_temps = (
        'coolest',
        'cool',
        'neutral',
        'warm',
    )
    color_temps_map: typing.ClassVar = {
        'coolest': 250,
        'cool': 250,
        'neutral': 350,
        'warm': 150,
    }
    colors_map: typing.ClassVar = {
        'yellow': (
            249,
            215,
            28,
        ),
        'blue': (
            30,
            144,
            255,
        ),
        'green': (
            154,
            205,
            50,
        ),
        'red': (
            128,
            0,
            0,
        ),
        'white': (
            254,
            254,
            254,
        ),
    }
    MIN_BRIGHTNESS = 0
    MAX_BRIGHTNESS = 254
    _can_run_after: datetime.datetime
    _lock: threading.RLock

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._can_run_after = datetime.datetime.now()
        self._lock = threading.RLock()

    @synchronized_method
    @method_with_transition
    def turn_on(self, *, color_temp: str = 'neutral', brightness: int = 254, transition: int = 0) -> None:
        assert self.MIN_BRIGHTNESS <= brightness <= self.MAX_BRIGHTNESS
        assert not isinstance(color_temp, str) or color_temp in self.color_temps
        assert not isinstance(color_temp, int) or 150 <= color_temp <= 500

        self.zig_bee.set(
            self.friendly_name,
            {
                'state': 'ON',
                'color_temp': color_temp,
                'brightness': brightness,
                'transition': transition,
            },
        )

    @synchronized_method
    def reset(self) -> None:
        self.turn_off()

    @synchronized_method
    @method_with_transition
    def turn_off(self, *, transition: int = 0) -> None:
        self.zig_bee.set(self.friendly_name, {'state': 'OFF', 'transition': transition})

    @synchronized_method
    @method_with_transition
    def set_color(self, rgb: tuple[int, int, int], *, transition: int = 0) -> None:
        self.zig_bee.set(
            self.friendly_name,
            {
                'color': {'rgb': ','.join(map(str, rgb))},
                'transition': transition,
            },
        )

    @synchronized_method
    @method_with_transition
    def set_color_by_name(self, name: str, *, transition: int = 0) -> None:
        self.set_color(self.colors_map[name], transition=transition)

    @synchronized_method
    @method_with_transition
    def set_color_temp(self, value: str | int, *, transition: int = 0) -> None:
        assert not isinstance(value, str) or value in self.color_temps
        assert not isinstance(value, int) or 150 <= value <= 500
        self.zig_bee.set(self.friendly_name, {'color_temp': value, 'transition': transition})

    @synchronized_method
    def set_color_temp_startup(self, value: str | int) -> None:
        assert not isinstance(value, str) or value in self.color_temps
        assert not isinstance(value, int) or 150 <= value <= 500
        self.zig_bee.set(self.friendly_name, {'color_temp_startup': value})

    @synchronized_method
    @method_with_transition
    def set_brightness(self, value: int, *, transition: int = 0) -> None:
        assert self.MIN_BRIGHTNESS <= value <= self.MAX_BRIGHTNESS
        self.zig_bee.set(self.friendly_name, {'brightness': value, 'transition': transition})

    @synchronized_method
    @method_with_transition
    def step_brightness(self, value: int, *, transition: int = 0) -> None:
        self.zig_bee.set(self.friendly_name, {'brightness_step': value, 'transition': transition})

    @synchronized_method
    @method_with_transition
    def step_color_temp(self, value: int, *, transition: int = 0) -> None:
        self.zig_bee.set(self.friendly_name, {'color_temp_step': value, 'transition': transition})

    @synchronized_method
    def get_state(self) -> dict:
        return self.zig_bee.get_state(self.friendly_name)

    @synchronized_method
    def is_on(self) -> bool:
        state = self.get_state()
        return state['state'] == 'ON'

    @synchronized_method
    def is_off(self) -> bool:
        state = self.get_state()
        return state['state'] == 'OFF'

    @synchronized_method
    def test(self) -> None:
        self.turn_off()
        sleep(2)

        self.turn_on(transition=1)
        sleep(2)

        self.set_color(
            (
                255,
                0,
                0,
            ),
            transition=1,
        )
        sleep(2)

        self.set_color(
            (
                0,
                255,
                0,
            ),
            transition=1,
        )
        sleep(2)

        self.set_color(
            (
                0,
                0,
                255,
            ),
            transition=1,
        )
        sleep(2)

        self.set_color(
            (
                255,
                255,
                255,
            ),
            transition=1,
        )
        sleep(2)

        self.set_brightness(0, transition=1)
        sleep(2)

        for brightness in range(0, 254, 50):
            self.set_brightness(brightness, transition=1)
            sleep(2)

        self.set_brightness(254, transition=1)
        sleep(2)

        for color in self.colors_map.values():
            self.set_color(color, transition=1)
            sleep(2)

        self.turn_off(transition=1)
