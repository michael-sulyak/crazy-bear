
from telegram.helpers import escape_markdown as telegram_escape_markdown

from .base import BaseMessenger


class ProgressBar:
    messenger: BaseMessenger
    title: str
    message_id: int
    _last_progress: float
    _last_title: str

    def __init__(self, messenger: BaseMessenger, *, title: str | None = None) -> None:
        self.messenger = messenger
        self.title = '' if title is None else f'{title}\n'

    def __enter__(self) -> 'ProgressBar':
        self.message_id = self.messenger.send_message(
            f'{self.title}{self._generate_bar(0)}',
            reply_markup=None,
            use_markdown=True,
        )
        self._last_progress = 0
        self._last_title = self.title
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.messenger.remove_message(self.message_id)

    def set(self, progress: float, *, title: str | None = None) -> None:
        if title is not None:
            if title == '':
                self.title = ''
            else:
                self.title = f'{title}\n'

        progress = round(progress, 2)

        if self._last_title != self.title or self._last_progress != progress:
            self.messenger.send_message(
                f'{self.title}{self._generate_bar(progress)}',
                message_id=self.message_id,
                reply_markup=None,
                use_markdown=True,
            )
            self._last_progress = progress
            self._last_title = self.title

    @staticmethod
    def _generate_bar(progress: float) -> str:
        a, b, length = '█', '▁', 20
        s = int(progress * length)
        return f'`{a * s}{b * (length - s)} {str(int(progress * 100)).rjust(3, " ")}%`'


def escape_markdown(text: str, entity_type: str | None = None) -> str:
    return telegram_escape_markdown(text, version=2, entity_type=entity_type)
