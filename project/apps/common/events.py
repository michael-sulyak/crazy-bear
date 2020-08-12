import logging
import threading
import typing


class Event:
    receivers: typing.List[typing.Callable]
    lock: threading.Lock
    providing_kwargs: typing.Tuple

    def __init__(self, providing_kwargs: typing.Optional[typing.Iterable] = ()) -> None:
        self.receivers = []
        self.lock = threading.Lock()
        self.providing_kwargs = tuple(providing_kwargs)

    def connect(self, receiver: typing.Callable) -> None:
        assert callable(receiver)

        with self.lock:
            self.receivers.append(receiver)

    def disconnect(self, receiver: typing.Callable) -> None:
        assert callable(receiver)

        with self.lock:
            try:
                index = self.receivers.index(receiver)
                del self.receivers[index]
            except ValueError:
                pass

    def send(self, **kwargs) -> None:
        for receiver in self.receivers:
            try:
                receiver(**kwargs)
            except Exception as e:
                logging.exception(e)
