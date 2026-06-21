import asyncio
import datetime
import logging

from aiohttp import web

from libs.casual_utils.aio import async_thread
from libs.qingping.base import Measurement
from project.apps import db
from project.apps.common.state import State
from project.apps.core.constants import AIR_MONITOR_STATE, AIR_MONITOR_CO2
from project.apps.core.signals.temp_hum_sensors import HUMIDITY_SUFFIX, TEMPERATURE_SUFFIX
from project.apps.signals.models import Signal
from project.config import SmartDeviceNames


class AioHttpServer:
    state: State
    host: str
    port: int
    html_content: str
    futures: list

    def __init__(self, *, state: State, host: str = '0.0.0.0', port: int = 8000) -> None:
        self.state = state
        self.host = host
        self.port = port
        self.runner = None
        self.futures = []

        with open('./project/apps/dashboard/resources/index.html') as file:
            self.html_content = file.read()

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=self.html_content, content_type='text/html')

    async def handle_stats(self, request: web.Request) -> web.Response:
        now = datetime.datetime.now(datetime.UTC)
        day_ago = now - datetime.timedelta(hours=24)

        places = []
        places_map = {
            device_name.removeprefix(SmartDeviceNames.TEMP_HUM_SENSOR_NAME_PREFIX).replace('_', ' ').title(): {
                'temperature': f'{device_name}{TEMPERATURE_SUFFIX}',
                'humidity': f'{device_name}{HUMIDITY_SUFFIX}',
            }
            for device_name in sorted(SmartDeviceNames.TEMP_HUM_SENSORS)
        }

        for place_name, signals in places_map.items():
            session = db.get_db_session()
            last_temp = (
                session.query(Signal.value)
                .filter(
                    Signal.type == signals['temperature'],
                    Signal.received_at >= day_ago,
                )
                .order_by(Signal.received_at.desc())
                .first()
            )
            last_hum = (
                session.query(Signal.value)
                .filter(
                    Signal.type == signals['humidity'],
                    Signal.received_at >= day_ago,
                )
                .order_by(Signal.received_at.desc())
                .first()
            )

            # Get aggregated (hourly) temperature and humidity for the last 24 hours
            agg_temp = Signal.get_aggregated(
                signals['temperature'],
                datetime_range=(day_ago, now),
                date_trunc='hour',
            )
            agg_hum = Signal.get_aggregated(
                signals['humidity'],
                datetime_range=(day_ago, now),
                date_trunc='hour',
            )

            agg_data = []
            temp_by_time = {row.aggregated_time.isoformat(): row.value for row in agg_temp}
            hum_by_time = {row.aggregated_time.isoformat(): row.value for row in agg_hum}
            all_times = sorted(set(temp_by_time) | set(hum_by_time))
            for t in all_times:
                current_temp_by_time = temp_by_time.get(t)
                current_hum_by_time = hum_by_time.get(t)

                agg_data.append({
                    'time': t,
                    'temperature': current_temp_by_time and round(current_temp_by_time, 1),
                    'humidity': current_hum_by_time and round(current_hum_by_time, 1),
                })

            places.append({
                'name': place_name,
                'last': {
                    'temperature': round(last_temp[0], 1) if last_temp else None,
                    'humidity': round(last_hum[0]) if last_hum else None,
                },
                'aggregated': agg_data,
            })

        air_monitor_state: Measurement | None = self.state[AIR_MONITOR_STATE]

        if air_monitor_state:
            agg_co2 = Signal.get_aggregated(
                AIR_MONITOR_CO2,
                datetime_range=(day_ago, now),
                date_trunc='hour',
            )

            agg_data = [
                {
                    'time': row.aggregated_time.isoformat(),
                    'co2': row.value and round(row.value),
                }
                for row in agg_co2
            ]

            air_monitor = {
                'temperature': air_monitor_state.temperature_celsius,
                'humidity': air_monitor_state.humidity_percent,
                'co2': air_monitor_state.co2,
                'pm10': air_monitor_state.pm10,
                'pm25': air_monitor_state.pm25,
                'history': agg_data,
            }
        else:
            air_monitor = None

        stats = {'places': places, 'air_monitor': air_monitor}
        return web.json_response(stats)

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
        self.futures.append(asyncio.run_coroutine_threadsafe(self.start_server(), loop))

    def stop(self) -> None:
        if not self.runner:
            return

        async def shutdown() -> None:
            await self.runner.cleanup()
            logging.info('Server stopped.')

        loop = async_thread.get_loop()
        self.futures.append(asyncio.run_coroutine_threadsafe(shutdown(), loop))
