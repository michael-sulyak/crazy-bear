import typing

from .base import BaseMessenger


class ProgressBar:
    messenger: BaseMessenger
    title: str
    message_id: int

    def __init__(self, messenger: BaseMessenger, *, title: typing.Optional[str] = None) -> None:
        self.messenger = messenger
        self.title = '' if title is None else f'{title}\n'

    def __enter__(self) -> 'ProgressBar':
        self.message_id = self.messenger.send_message(
            f'{self.title}{self._generate_bar(0)}',
            reply_markup=None,
        )
        self.messenger.start_typing()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.messenger.remove_message(self.message_id)

    def set(self, progress: float) -> None:
        self.messenger.send_message(
            f'{self.title}{self._generate_bar(progress)}',
            message_id=self.message_id,
            reply_markup=None,
        )
        self.messenger.start_typing()

    @staticmethod
    def _generate_bar(progress: float) -> str:
        a, b, length = '█', '▁', 20
        s = int(progress * length)
        return f'`{a * s}{b * (length - s)} {str(int(progress * 100)).rjust(3, " ")}%`'
