import abc
import datetime
import typing
from dataclasses import dataclass

from . import mixins


class BaseMessenger(mixins.BaseCVMixin, abc.ABC):
    last_message_id: typing.Any
    last_sent_at: typing.Optional[datetime.datetime]

    @abc.abstractmethod
    def send_message(self, text: str, *args, **kwargs) -> typing.Any:
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
    def start_typing(self, *args, **kwargs) -> None:
        pass

    def close(self) -> None:
        pass

    @abc.abstractmethod
    def remove_message(self, message_id: int) -> None:
        pass


@dataclass
class UserInfo:
    username: typing.Optional[str]
    name: typing.Optional[str]


@dataclass
class ChatInfo:
    id: int


@dataclass
class MessageInfo:
    user: UserInfo
    chat: ChatInfo
    text: str
