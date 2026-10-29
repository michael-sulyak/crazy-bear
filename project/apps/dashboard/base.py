import asyncio
import datetime
import logging

from aiohttp import web

from libs.casual_utils.aio import async_thread
from libs.qingping.base import Measurement
from project.apps import db
from project.apps.common.state import State
from project.apps.common.utils import is_heating_season
from project.apps.core.constants import AIR_MONITOR_CO2, AIR_MONITOR_STATE
from project.apps.core.signals.temp_hum_sensors import (
    HUMIDITY_SUFFIX,
    TEMPERATURE_SUFFIX,
)
from project.apps.signals.models import Signal
from project.config import SmartDeviceNames


class AioHttpServer:
    state: State
    host: str
    port: int
    html_content: str
    futures: list

    def __init__(
            self,
            *,
            state: State,
            host: str = '0.0.0.0',
            port: int = 8000,
    ) -> None:
        self.state = state
        self.host = host
        self.port = port
        self.runner = None
        self.futures = []

        with open(
                './project/apps/dashboard/resources/index.html',
                encoding='utf-8',
        ) as file:
            self.html_content = file.read()

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(
            text=self.html_content,
            content_type='text/html',
        )

    async def handle_stats(self, request: web.Request) -> web.Response:
        now = datetime.datetime.now(datetime.UTC)
        day_ago = now - datetime.timedelta(hours=24)
        month_ago = now - datetime.timedelta(days=30)
        freshness_cutoff = now - datetime.timedelta(hours=1)

        session = db.get_db_session()

        try:
            def latest_value(signal_type: str, digits: int):
                row = (
                    session.query(Signal.value)
                    .filter(
                        Signal.type == signal_type,
                        Signal.received_at >= freshness_cutoff,
                        Signal.received_at <= now,
                    )
                    .order_by(Signal.received_at.desc())
                    .first()
                )

                if row is None or row[0] is None:
                    return None

                value = float(row[0])

                return round(value, digits) if digits else round(value)

            places = []

            for device_name in sorted(SmartDeviceNames.TEMP_HUM_SENSORS):
                temperature_type = f'{device_name}{TEMPERATURE_SUFFIX}'
                humidity_type = f'{device_name}{HUMIDITY_SUFFIX}'

                agg_temp = Signal.get_aggregated(
                    temperature_type,
                    datetime_range=(day_ago, now),
                    date_trunc='hour',
                )
                agg_hum = Signal.get_aggregated(
                    humidity_type,
                    datetime_range=(day_ago, now),
                    date_trunc='hour',
                )

                temp_by_time = {
                    row.aggregated_time.isoformat(): row.value
                    for row in agg_temp
                }
                hum_by_time = {
                    row.aggregated_time.isoformat(): row.value
                    for row in agg_hum
                }

                history = []

                for timestamp in sorted(set(temp_by_time) | set(hum_by_time)):
                    temperature = temp_by_time.get(timestamp)
                    humidity = hum_by_time.get(timestamp)

                    history.append({
                        'time': timestamp,
                        'temperature': (
                            round(float(temperature), 1)
                            if temperature is not None
                            else None
                        ),
                        'humidity': (
                            round(float(humidity), 1)
                            if humidity is not None
                            else None
                        ),
                    })

                places.append({
                    'name': (
                        device_name
                        .removeprefix(
                            SmartDeviceNames.TEMP_HUM_SENSOR_NAME_PREFIX,
                        )
                        .replace('_', ' ')
                        .title()
                    ),
                    'latest': {
                        'temperature': latest_value(temperature_type, 1),
                        'humidity': latest_value(humidity_type, 0),
                    },
                    'history': history,
                })

            air_monitor_state: Measurement | None = self.state[
                AIR_MONITOR_STATE
            ]

            if air_monitor_state is not None:
                agg_co2 = Signal.get_aggregated(
                    AIR_MONITOR_CO2,
                    datetime_range=(day_ago, now),
                    date_trunc='hour',
                )

                air_monitor = {
                    'latest': {
                        'temperature': air_monitor_state.temperature_celsius,
                        'humidity': air_monitor_state.humidity_percent,
                        'co2': air_monitor_state.co2,
                        'pm10': air_monitor_state.pm10,
                        'pm25': air_monitor_state.pm25,
                    },
                    'history': [
                        {
                            'time': row.aggregated_time.isoformat(),
                            'co2': (
                                round(float(row.value))
                                if row.value is not None
                                else None
                            ),
                        }
                        for row in agg_co2
                    ],
                }
            else:
                air_monitor = None

            radiators = (
                self._get_radiator_stats(
                    session,
                    now=now,
                    day_ago=day_ago,
                    month_ago=month_ago,
                )
                if is_heating_season()
                else None
            )

            data = {
                'places': places,
                'air_monitor': air_monitor,
                'radiators': radiators,
            }
        finally:
            session.close()

        return web.json_response(data)

    async def start_server(self) -> None:
        app = web.Application()
        app.router.add_get('/', self.handle_index)
        app.router.add_get('/api/stats', self.handle_stats)

        self.runner = web.AppRunner(app)
        await self.runner.setup()

        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        logging.info(f'Serving at http://{self.host}:{self.port}')

    def start(self) -> None:
        loop = async_thread.get_loop()
        self.futures.append(
            asyncio.run_coroutine_threadsafe(self.start_server(), loop),
        )

    def stop(self) -> None:
        if not self.runner:
            return

        async def shutdown() -> None:
            await self.runner.cleanup()
            logging.info('Server stopped.')

        loop = async_thread.get_loop()
        self.futures.append(
            asyncio.run_coroutine_threadsafe(shutdown(), loop),
        )

    @staticmethod
    def _summarize_heating(
            events: list[tuple[datetime.datetime, bool | None]],
            *,
            start: datetime.datetime,
            end: datetime.datetime,
    ) -> tuple[list[dict], dict]:
        state = None

        # Find the state active at the beginning of the requested window.
        for timestamp, heating in events:
            if timestamp > start:
                break

            state = heating

        history = [
            {
                'time': start.isoformat(),
                'heating': state,
            },
        ]

        cursor = start
        known_seconds = 0
        heating_seconds = 0

        for timestamp, next_state in events:
            if timestamp <= start:
                continue

            if timestamp > end:
                break

            duration = (timestamp - cursor).total_seconds()

            if state is not None:
                known_seconds += duration

                if state:
                    heating_seconds += duration

            # Repeated reports do not need additional graph points.
            if next_state != state:
                history.append({
                    'time': timestamp.isoformat(),
                    'heating': next_state,
                })

            state = next_state
            cursor = timestamp

        # Carry the final reported state forward to the end of the window.
        duration = (end - cursor).total_seconds()

        if state is not None:
            known_seconds += duration

            if state:
                heating_seconds += duration

        end_time = end.isoformat()

        if history[-1]['time'] != end_time:
            history.append({
                'time': end_time,
                'heating': state,
            })

        window_seconds = (end - start).total_seconds()

        summary = {
            'heating_percent': (
                round(100 * heating_seconds / known_seconds, 1)
                if known_seconds > 0
                else None
            ),
            'coverage_percent': (
                round(100 * known_seconds / window_seconds, 1)
                if window_seconds > 0
                else 0
            ),
        }

        return history, summary

    def _get_radiator_stats(
            self,
            session,
            *,
            now: datetime.datetime,
            day_ago: datetime.datetime,
            month_ago: datetime.datetime,
    ) -> list[dict]:
        radiators = []

        for device_name in sorted(
                SmartDeviceNames.THERMOSTATIC_RADIATOR_VALVES,
        ):
            signal_type = f'{device_name}:state'

            # The most recent report before the window establishes the
            # initial state. Without it, time before the first report is unknown.
            previous = (
                session.query(Signal.received_at, Signal.value)
                .filter(
                    Signal.type == signal_type,
                    Signal.received_at < month_ago,
                )
                .order_by(Signal.received_at.desc())
                .first()
            )

            rows = (
                session.query(Signal.received_at, Signal.value)
                .filter(
                    Signal.type == signal_type,
                    Signal.received_at >= month_ago,
                    Signal.received_at <= now,
                )
                .order_by(Signal.received_at.asc())
                .all()
            )

            if previous is not None:
                rows = [previous, *rows]

            events = []

            for row in rows:
                timestamp = row.received_at

                # This assumes naive database timestamps, if present,
                # are stored in UTC.
                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(tzinfo=datetime.UTC)
                else:
                    timestamp = timestamp.astimezone(datetime.UTC)

                if row.value == 1:
                    heating = True
                elif row.value == 0:
                    heating = False
                else:
                    heating = None

                events.append((timestamp, heating))

            events.sort(key=lambda event: event[0])

            day_history, day_summary = self._summarize_heating(
                events,
                start=day_ago,
                end=now,
            )

            _, month_summary = self._summarize_heating(
                events,
                start=month_ago,
                end=now,
            )

            radiators.append({
                'name': (
                    device_name
                    .removeprefix(
                        SmartDeviceNames.THERMOSTATIC_RADIATOR_VALVE_NAME_PREFIX,
                    )
                    .replace('_', ' ')
                    .title()
                ),
                'latest': {
                    'time': events[-1][0].isoformat() if events else None,
                    'heating': day_history[-1]['heating'],
                },
                'history': day_history,
                'heating_summary': {
                    'last_24_hours': day_summary,
                    'last_30_days': month_summary,
                },
            })

        return radiators
