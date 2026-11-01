import datetime
import logging
import threading
import typing

import numpy as np
from sqlalchemy import text
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest

from libs.casual_utils.time import get_current_time
from libs.messengers.utils import ProgressBar, escape_markdown
from libs.task_queue import IntervalTask, TaskPriorities

from ... import db
from ...common import interface
from ...common.exceptions import Shutdown
from ...common.utils import convert_params_to_date_range, is_sleep_hours
from ...core import constants
from ...signals.models import Signal
from .. import events
from ..base import BaseModule, Command
from ..telegram_ui import status_actions
from ..utils.reports import ShortTextReport


@interface.module(
    title='Report',
    description='The module provides a short report with needed data.',
)
class Report(BaseModule):
    _stats_flags_map: typing.ClassVar = {
        'a': 'arduino',
        'e': 'extra_data',
        'i': 'inner_stats',
        'r': 'router_usage',
    }
    _lock_for_status: threading.RLock
    _message_id_for_status: typing.Any = None

    def __init__(self, *args, **kwargs) -> None:
        self._lock_for_status = threading.RLock()
        super().__init__(*args, **kwargs)

    def get_initial_state(self) -> dict[str, typing.Any]:
        return {
            **super().get_initial_state(),
            constants.LAST_CRITICAL_SITUATION_OCCURRED_AT: None,
        }

    def init_repeatable_tasks(self) -> tuple:
        return (
            IntervalTask(
                target=self._update_status,
                priority=TaskPriorities.LOW,
                interval=datetime.timedelta(minutes=1),
            ),
        )

    def process_command(self, command: Command) -> typing.Any:
        with self._lock_for_status:
            self._message_id_for_status = (
                command.callback_message_id if command.name == constants.BotCommands.STATUS else None
            )

        return super().process_command(command)

    @interface.command(
        constants.BotCommands.STATS,
        flags=(interface.Flag('s'),),
    )
    @interface.command(
        constants.BotCommands.STATS,
        interface.Value('number', python_type=int),
        interface.Choices('days', 'hours', 'minutes', 'seconds'),
        flags=(interface.Flag('s'),),
    )
    def _send_stats(self, command: Command) -> None:
        args = command.get_cleaned_args()
        flags = command.get_cleaned_flags()

        try:
            if len(args) not in {0, 2}:
                raise ValueError

            delta_type = args[1] if args else 'hours'
            delta_value = int(args[0]) if args else 24

            if delta_type not in {'days', 'hours', 'minutes', 'seconds'} or delta_value <= 0:
                raise ValueError

            if flags - (self._stats_flags_map.keys() | {'s', 'f'}):
                raise ValueError

            date_range = convert_params_to_date_range(delta_type=delta_type, delta_value=delta_value)
        except (ValueError, OverflowError):
            self.messenger.send_message(
                'Choose a positive history period, for example /stats 6 hours -s.\n'
                'Units: seconds, minutes, hours, days. Use /help commands for flags.',
            )
            return

        if not flags or 'f' in flags:
            flags = set(self._stats_flags_map)
        elif 's' in flags:
            flags = (flags - {'s'}) | {'a', 'e', 'r'}

        events.request_for_statistics.pipe(
            self._pipe_for_collecting_stats,
            date_range=date_range,
            components={self._stats_flags_map[flag] for flag in flags},
        )

    @interface.command(constants.BotCommands.HELP)
    def _send_help(self, command: Command) -> None:
        if not command.first_arg:
            self.messenger.send_message(
                '❓ CrazyBear · Quick guide\n\n'
                '/start — restore the navigation keyboard and show status\n'
                '/status — live home readings (/home is a compatibility alias)\n'
                '/stats -s — a short history for the last 24 h\n'
                '/to lamp — light, brightness, and colors\n'
                '/to security — manual and automatic security\n'
                '/to heating — pause, boost to 30 °C, or resume schedules\n'
                '/to history — choose 1 h, 6 h, 24 h, or 7 days\n'
                '/to all_funcs — camera, help, and system tools\n\n'
                'The bottom keyboard always opens sections.\n'
                'Control each section with the buttons on its message.\n'
                'Use inline Back or Cancel in nested screens.\n'
                'Status has only inline Refresh; open controls from the bottom keyboard.\n'
                'The Telegram command menu lists common commands.\n\n'
                'Advanced: /help commands — all commands\n'
                'Examples: /stats 6 hours -s · /trv disable 1.5 · /trv boost 0.5',
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton(constants.PrettyBotCommands.ALL_COMMANDS, callback_data='ui:commands'),
                ]]),
            )
            return

        if command.first_arg != 'commands':
            self.messenger.send_message('Use /help for the quick guide or /help commands for all commands.')
            return

        docs = sorted(events.getting_doc.process()[0], key=lambda doc: doc.title)

        for doc in docs:
            if doc.commands:
                self.messenger.send_message(doc.to_str(), use_markdown=True)

    def _update_status(self) -> None:
        with self._lock_for_status:
            if (
                self._message_id_for_status
                and (
                    self.messenger.last_message_id != self._message_id_for_status
                    or get_current_time() - self.messenger.last_sent_at >= datetime.timedelta(hours=48)
                )
            ):
                self._message_id_for_status = None

            if not self._message_id_for_status:
                if (
                    self.messenger.last_sent_at
                    and get_current_time() - self.messenger.last_sent_at > datetime.timedelta(minutes=10)
                    and not is_sleep_hours()
                ):
                    logging.info('Send full status again after timeout.')
                    self._send_status()

                return

            logging.debug('Update status')
            self._send_status()

    def _pipe_for_collecting_stats(self, receivers: typing.Sequence, kwargs: dict) -> typing.Iterator:
        with ProgressBar(self.messenger, title='Collecting stats\\.\\.\\.') as progress_bar:
            count = len(receivers)
            plots: list[np.ndarray] = []
            exceptions = []

            for i in range(count):
                try:
                    result = yield
                except Shutdown:
                    raise
                except Exception as e:
                    exceptions.append(e)
                    continue

                if result is not None:
                    if isinstance(result, tuple | list):
                        plots.extend(result)
                    else:
                        plots.append(result)

                progress_bar.set((i + 1) / count)

            for exception in exceptions:
                logging.exception(exception)
                self.messenger.exception(exception)

            if plots:
                self.messenger.send_images(images=plots)
            else:
                self.messenger.send_message('There is still little data')

        yield None

    @interface.command(constants.BotCommands.START)
    @interface.command(constants.BotCommands.HOME)
    @interface.command(constants.BotCommands.STATUS)
    def _send_status(self, command: Command | None = None) -> None:
        if command is not None or self._message_id_for_status is None:
            self.messenger.ensure_navigation(
                force=command is not None and command.name in {constants.BotCommands.START, constants.BotCommands.HOME},
            )

        report = ShortTextReport(state=self.state)
        message = (
            f'{report.generate()}\n\n'
            f'🕒 Updated: `{escape_markdown(report.now.strftime("%d.%m.%Y, %H:%M:%S"), entity_type="code")}`'
        )

        with self._lock_for_status:
            try:
                self._message_id_for_status = self.messenger.send_message(
                    message,
                    message_id=self._message_id_for_status,
                    use_markdown=True,
                    reply_markup=status_actions(),
                )
            except BadRequest as exc:
                if not self._message_id_for_status or str(exc).casefold() not in {
                    "message can't be edited",
                    'message to edit not found',
                }:
                    raise

                logging.info('Replacing uneditable status message %s: %s', self._message_id_for_status, exc)
                # Clear before sending so a failed replacement cannot leave a stale ID.
                self._message_id_for_status = None
                self._message_id_for_status = self.messenger.send_message(
                    message,
                    use_markdown=True,
                    reply_markup=status_actions(),
                )

    @interface.command(constants.BotCommands.DB_STATS)
    def _send_db_stats(self) -> None:
        sql = """
        SELECT table_name, pg_size_pretty(pg_relation_size(quote_ident(table_name))) AS table_size
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_size;
        """

        with db.db_engine.connect() as connection:
            result = connection.execute(text(sql)).mappings().all()

        sections = [
            '💾 Database usage\n\n' + '\n'.join(
                f'{row["table_name"]}: {row["table_size"]}' for row in result
            ),
            '📊 Stored readings\n\n' + '\n'.join(
                f'{name}: {count:,}' for name, count in Signal.get_table_stats().items()
            ),
        ]

        for section in sections:
            lines = section.splitlines(keepends=True)
            chunk = ''

            for line in lines:
                if len(chunk) + len(line) > 3500:
                    self.messenger.send_message(chunk.rstrip())
                    chunk = ''

                chunk += line

            if chunk:
                self.messenger.send_message(chunk.rstrip())
