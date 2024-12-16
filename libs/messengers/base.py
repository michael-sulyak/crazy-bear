import abc
import datetime
import typing
from dataclasses import dataclass

from . import mixins


class BaseMessenger(mixins.BaseCVMixin, abc.ABC):
    last_message_id: typing.Any

    @property
    @abc.abstractmethod
    def last_sent_at(self) -> datetime.datetime | None:
        pass

    @abc.abstractmethod
    def send_message(self, text: str, *args, **kwargs) -> typing.Any:
        pass

    @abc.abstractmethod
    def send_image(self, image: typing.Any, *, caption: str | None = None) -> None:
        pass

    @abc.abstractmethod
    def send_images(self, images: typing.Any) -> None:
        pass

    @abc.abstractmethod
    def send_file(self, file: typing.Any, *, caption: str | None = None) -> None:
        pass

    @abc.abstractmethod
    def warning(self, text: str) -> None:
        pass

    @abc.abstractmethod
    def error(self, text: str) -> None:
        pass

    @abc.abstractmethod
    def exception(self, exp: Exception) -> None:
        pass

    @abc.abstractmethod
    def start_typing(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass

    @abc.abstractmethod
    def remove_message(self, message_id: int) -> None:
        pass


@dataclass
class UserInfo:
    username: str | None
    name: str | None


@dataclass
class ChatInfo:
    id: int


@dataclass
class MessageInfo:
    user: UserInfo
    chat: ChatInfo
    text: str
