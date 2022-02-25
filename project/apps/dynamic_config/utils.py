import threading
import typing

from . import models
from .events import dynamic_config_is_updated
from .models import DynamicConstant
from ..common.utils import synchronized_method


def get_config() -> typing.Dict[str, typing.Any]:
    constants = models.DynamicConstant.all()

    return {
        constant.name: constant.value
        for constant in constants
    }


class DynamicConfigProxy:
    _lock: threading.RLock
    _cache: typing.Optional[dict] = None

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def __getitem__(self, name: str) -> typing.Any:
        return self._get().get(name)

    def __setitem__(self, name: str, value: typing.Any) -> None:
        with self._lock:
            DynamicConstant.set(name, value)
            self._clear()

        dynamic_config_is_updated.send()

    def __delitem__(self, name: str) -> None:
        with self._lock:
            DynamicConstant.delete(name)
            self._clear()

        dynamic_config_is_updated.send()

    @synchronized_method
    def _get(self) -> dict:
        if self._cache is None:
            self._cache = get_config()

        return self._cache

    @synchronized_method
    def _clear(self) -> None:
        self._cache = None


dynamic_config = DynamicConfigProxy()
