import logging
import threading
import typing
from dataclasses import dataclass

from .exceptions import Shutdown
from .utils import synchronized_method


__all__ = (
    'Event',
    'Receiver',
)


class Event:
    receivers: typing.List[typing.Callable]
    providing_kwargs: typing.Tuple[str]
    _lock: threading.Lock

    def __init__(self, *, providing_kwargs: typing.Optional[typing.Iterable[str]] = ()) -> None:
        self.receivers = []
        self._lock = threading.Lock()
        self.providing_kwargs = tuple(providing_kwargs)

    @synchronized_method
    def connect(self, func: typing.Callable) -> 'Receiver':
        assert callable(func)

        self.receivers.append(func)

        return Receiver(func=func, event=self)

    @synchronized_method
    def disconnect(self, receiver: typing.Callable) -> None:
        assert callable(receiver)

        try:
            index = self.receivers.index(receiver)
            del self.receivers[index]
        except ValueError:
            pass

    def send(self, **kwargs) -> None:
        for receiver in self.receivers:
            try:
                receiver(**kwargs)
            except Shutdown:
                raise
            except Exception as e:
                logging.exception(e)

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
class Receiver:
    event: Event
    func: typing.Callable

    def disconnect(self) -> None:
        self.event.disconnect(self.func)
