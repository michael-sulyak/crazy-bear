import collections
import datetime
import threading
import typing


class ThreadPool:
    _timedelta_for_part_sync: datetime.timedelta
    _threads: typing.Deque[typing.Tuple[threading.Thread, datetime.datetime]]
    _lock = threading.Lock()

    def __init__(self, timedelta_for_part_sync: typing.Optional[datetime.timedelta] = None) -> None:
        if timedelta_for_part_sync is None:
            timedelta_for_part_sync = datetime.timedelta(seconds=20)

        self._timedelta_for_part_sync = timedelta_for_part_sync
        self._threads = collections.deque()

    def run(self,
            target: typing.Callable,
            args: typing.Tuple = None,
            kwargs: typing.Dict[str, typing.Any] = None) -> None:
        if args is None:
            args = tuple()

        if kwargs is None:
            args = {}

        with self._lock:
            thread = threading.Thread(target=target, args=args, kwargs=kwargs)
            thread.start()

            now = datetime.datetime.now()
            self._threads.append((thread, now,))

    def sync(self) -> None:
        with self._lock:
            for thread, started_at in self._threads:
                thread.join()

            self._threads.clear()

    def part_sync(self) -> None:
        with self._lock:
            now = datetime.datetime.now()

            while self._threads:
                thread, started_at = self._threads[0]

                if now - started_at > self._timedelta_for_part_sync:
                    thread.join()
                    self._threads.popleft()
                else:
                    break
