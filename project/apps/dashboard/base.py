import asyncio
import datetime
import logging

from aiohttp import web

from libs.casual_utils.aio import async_thread
from project.apps import db
from project.apps.core.signals.temp_hum_sensors import HUMIDITY_SUFFIX, TEMPERATURE_SUFFIX
from project.apps.signals.models import Signal
from project.config import SmartDeviceNames


class AioHttpServer:
    host: str
    port: int
    html_content: str
    futures: list

    def __init__(self, *, host: str = '0.0.0.0', port: int = 8000) -> None:
        self.host = host
        self.port = port
        self.runner = None
        self.futures = []

        with open('./project/apps/dashboard/resources/index.html', 'r') as file:
            self.html_content = file.read()

    async def handle_index(self, request: web.Request) -> web.Response:
        return web.Response(text=self.html_content, content_type='text/html')

    async def handle_stats(self, request: web.Request) -> web.Response:
        now = datetime.datetime.now(datetime.timezone.utc)
        day_ago = now - datetime.timedelta(hours=24)

        rooms = []
        rooms_map = {
            device_name.removeprefix(SmartDeviceNames.TEMP_HUM_SENSOR_NAME_PREFIX).replace('_', ' ').title(): {
                'temperature': f'{device_name}{TEMPERATURE_SUFFIX}',
                'humidity': f'{device_name}{HUMIDITY_SUFFIX}',
            }
            for device_name in sorted(SmartDeviceNames.TEMP_HUM_SENSORS)
        }

        for room_name, signals in rooms_map.items():
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

            rooms.append({
                'name': room_name,
                'last': {
                    'temperature': round(last_temp[0], 1) if last_temp else None,
                    'humidity': round(last_hum[0]) if last_hum else None,
                },
                'aggregated': agg_data,
            })

        stats = [{'rooms': rooms}]
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
