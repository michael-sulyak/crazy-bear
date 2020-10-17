import logging
import threading
import typing


class Event:
    receivers: typing.List[typing.Callable]
    providing_kwargs: typing.Tuple[str]
    _lock: threading.Lock

    def __init__(self, providing_kwargs: typing.Optional[typing.Iterable[str]] = ()) -> None:
        self.receivers = []
        self._lock = threading.Lock()
        self.providing_kwargs = tuple(providing_kwargs)

    def connect(self, receiver: typing.Callable) -> None:
        assert callable(receiver)

        with self._lock:
            self.receivers.append(receiver)

    def disconnect(self, receiver: typing.Callable) -> None:
        assert callable(receiver)

        with self._lock:
            try:
                index = self.receivers.index(receiver)
                del self.receivers[index]
            except ValueError:
                pass

    def send(self, **kwargs) -> None:
        for receiver in self.receivers:
            try:
                receiver(**kwargs)
            except KeyboardInterrupt as e:
                raise e
            except Exception as e:
                logging.exception(e)

    def process(self, **kwargs) -> typing.Tuple[list, list]:
        results = []
        exceptions = []

        for receiver in self.receivers:
            try:
                result = receiver(**kwargs)
                results.append(result)
            except KeyboardInterrupt as e:
                raise e
            except Exception as e:
                logging.exception(e)
                exceptions.append(e)

        return results, exceptions
