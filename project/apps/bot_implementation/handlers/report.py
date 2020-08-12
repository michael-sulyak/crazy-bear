from datetime import datetime

from emoji import emojize

from .. import constants
from ..utils import get_weather
from ...messengers.base import BaseCommandHandler, Command


__all__ = (
    'Report',
)


class Report(BaseCommandHandler):
    support_commands = {
        constants.BotCommands.REPORT,
    }

    def process_command(self, command: Command) -> None:
        if command.name == constants.BotCommands.REPORT:
            report = self._create_report()
            self.messenger.send_message(report)

    @staticmethod
    def _create_report() -> str:
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

        return (
            f'{greeting}\n\n'
            f'{weather}'
        )
