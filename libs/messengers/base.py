import abc
import contextlib
import contextvars
import datetime
import typing
from dataclasses import dataclass

from . import mixins


_text_feedback: contextvars.ContextVar[tuple[object, list[str]] | None] = contextvars.ContextVar(
    'messenger_text_feedback', default=None,
)


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

    def ensure_navigation(self, *, force: bool = False) -> None:
        """Install persistent navigation when supported by the transport."""

        pass

    @contextlib.contextmanager
    def capture_feedback(self) -> typing.Iterator[list[str]]:
        """Collect routine text replies for a single synchronous panel action."""

        feedback: list[str] = []
        token = _text_feedback.set((self, feedback))

        try:
            yield feedback
        finally:
            _text_feedback.reset(token)

    def record_feedback(self, text: str) -> bool:
        capture = _text_feedback.get()

        if capture is not None and capture[0] is self:
            capture[1].append(text)
            return True

        return False

    def close(self) -> None:
        pass

    @abc.abstractmethod
    def remove_message(self, message_id: int) -> None:
        pass


@dataclass
class UserInfo:
    username: str | None
    name: str | None
    id: int | None = None


@dataclass
class ChatInfo:
    id: int


@dataclass
class MessageInfo:
    user: UserInfo
    chat: ChatInfo
    text: str
    # Only populated for an inline button on a Telegram message.
    callback_message_id: int | None = None
