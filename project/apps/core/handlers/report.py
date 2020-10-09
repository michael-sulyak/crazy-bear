import typing
from datetime import datetime

from emoji import emojize

from ..base import BaseCommandHandler, Command
from ...common.utils import get_weather
from ...messengers.constants import BotCommands


__all__ = (
    'Report',
)


class Report(BaseCommandHandler):
    def process_command(self, command: Command) -> typing.Any:
        if command.name == BotCommands.REPORT:
            self._send_report()
            return True

        return False

    def _send_report(self) -> None:
        now = datetime.now()
        hour = now.hour

        if hour < 12:
            greeting = f'{emojize(":sunrise:")} ️*Good morning!*'
        elif 12 <= hour <= 17:
            greeting = f'{emojize(":sunset:")} ️*Good afternoon!*'
        elif 17 <= hour <= 24:
            greeting = f'{emojize(":night_with_stars:")} ️*Good evening!*'
        else:
            greeting = ''

        weather_data = get_weather()
        weather = f'{emojize(":thermometer:")} ️The weather in {weather_data["name"]}: *{weather_data["main"]["temp"]}℃*'
        weather += (
            f' ({weather_data["main"]["temp_min"]} .. {weather_data["main"]["temp_max"]}), '
            if weather_data["main"]["temp_min"] != weather_data["main"]["temp_max"] else ', '
        )
        weather += f'{weather_data["weather"][0]["description"]}.'

        self.messenger.send_message(
            f'{greeting}\n\n'
            f'{weather}'
        )
