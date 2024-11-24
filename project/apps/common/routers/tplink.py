import threading
import typing

import tplinkrouterc6u
from tplinkrouterc6u.exception import ClientError

from project import config


class TplinkRouter:
    _router: tplinkrouterc6u.AbstractRouter
    _lock: threading.Lock

    def __init__(self, *, password: str, host: str) -> None:
        self._router = tplinkrouterc6u.TplinkRouterProvider.get_client(password=password, host=host)
        self._lock = threading.Lock()

    def get_devices(self) -> typing.Sequence[tplinkrouterc6u.Device]:
        self._check_and_auth()

        try:
            return self._router.get_status().devices
        except ClientError:
            self._relogin()

        return self._router.get_status().devices

    def _check_and_auth(self) -> None:
        if self._router._logged:
            return

        with self._lock:
            if not self._router._logged:
                self._router.authorize()

    def _relogin(self) -> None:
        with self._lock:
            self._router.logout()
            self._router.authorize()


tplink_router = TplinkRouter(
    password=config.ROUTER_PASSWORD,
    host=config.ROUTER_URL,
)
