import abc
import typing

from . import mixins


class BaseMessenger(mixins.BaseCVMixin, abc.ABC):
    @abc.abstractmethod
    def send_message(self, text: str, *args, **kwargs) -> None:
        pass

    @abc.abstractmethod
    def send_image(self, image: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        pass

    @abc.abstractmethod
    def send_images(self, images: typing.Any) -> None:
        pass

    @abc.abstractmethod
    def send_file(self, file: typing.Any, *, caption: typing.Optional[str] = None) -> None:
        pass

    @abc.abstractmethod
    def error(self, text: str) -> None:
        pass

    @abc.abstractmethod
    def exception(self, exp: Exception) -> None:
        pass

    @abc.abstractmethod
    def start_typing(self, *args, **kwargs):
        pass

    @abc.abstractmethod
    def get_updates(self) -> typing.Iterator['Message']:
        pass
