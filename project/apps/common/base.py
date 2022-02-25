import abc


class BaseReceiver(abc.ABC):
    @abc.abstractmethod
    def disconnect(self) -> None:
        pass
