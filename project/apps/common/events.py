import logging
import threading
import typing
from dataclasses import dataclass

from libs.casual_utils.parallel_computing import synchronized_method
from .base import BaseReceiver
from .exceptions import Shutdown


__all__ = (
    'Event',
    'Receiver',
)


class Event:
    # todo: add parallel processing
    receivers: tuple[typing.Callable, ...]
    providing_kwargs: tuple[str, ...]
    _lock: threading.RLock

    def __init__(self, *, providing_kwargs: typing.Iterable[str] = ()) -> None:
        self.receivers = ()
        self.providing_kwargs = tuple(providing_kwargs)
        self._lock = threading.RLock()

    def connect(self, func: typing.Callable) -> 'Receiver':
        assert callable(func)

        with self._lock:
            self.receivers = (*self.receivers, func,)

        return Receiver(func=func, event=self)

    def disconnect(self, receiver: typing.Callable) -> None:
        assert callable(receiver)

        with self._lock:
            self.receivers = tuple(
                receiver_
                for receiver_ in self.receivers
                if receiver != receiver_
            )

    @synchronized_method
    def send(self, **kwargs) -> None:
        for receiver in self.receivers:
            try:
                receiver(**kwargs)
            except Shutdown:
                raise
            except Exception as e:
                logging.exception(e)

    @synchronized_method
    def process(self, **kwargs) -> typing.Tuple[list, list]:
        results = []
        exceptions = []

        for receiver in self.receivers:
            try:
                result = receiver(**kwargs)
                results.append(result)
            except Shutdown:
                raise
            except Exception as e:
                logging.exception(e)
                exceptions.append(e)

        return results, exceptions

    @synchronized_method
    def pipe(self, func: typing.Callable, **kwargs) -> typing.Any:
        handler = func(receivers=self.receivers, kwargs=kwargs)
        next(handler)

        for receiver in self.receivers:
            try:
                receiver_result = receiver(**kwargs)
            except Shutdown:
                raise
            except Exception as e:
                logging.exception(e)
                handler.throw(e)
            else:
                handler.send(receiver_result)

        try:
            next(handler)
        except StopIteration as e:
            return e.value
        else:
            logging.exception('Wrong value')


@dataclass
class Receiver(BaseReceiver):
    event: Event
    func: typing.Callable

    def disconnect(self) -> None:
        self.event.disconnect(self.func)
