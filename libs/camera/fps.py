import datetime
import time
import typing


class FPSTracker:
    _started_at: datetime.datetime | None = None
    _finished_at: datetime.datetime | None = None
    _last_updated_at: datetime.datetime | None = None
    _num_frames: int | None = None
    _new_started_at: datetime.datetime | None = None
    _new_num_frames: int | None = None
    _timedelta_for_duplicate: datetime.timedelta = datetime.timedelta(seconds=5)
    _timedelta_for_reset: datetime.timedelta = datetime.timedelta(seconds=10)

    def start(self) -> None:
        """Start the timer."""

        self._started_at = datetime.datetime.now()
        self._last_updated_at = self._started_at
        self._num_frames = 0
        self._finished_at = None

    def stop(self) -> None:
        """Stop the timer."""

        self._finished_at = datetime.datetime.now()

    def update(self, fps: int | None = None) -> None:
        """
        Increment the total number of frames examined during the
        start and end intervals.
        """

        assert self._started_at is not None
        assert self._num_frames is not None
        assert self._last_updated_at is not None

        now = datetime.datetime.now()
        diff = now - self._started_at

        if diff > self._timedelta_for_duplicate:
            if not self._new_started_at:
                self._new_started_at = now
                self._new_num_frames = 1
            elif diff > self._timedelta_for_reset:
                self._started_at = self._new_started_at
                self._num_frames = self._new_num_frames
                self._new_started_at = None
                self._new_num_frames = None
            else:
                assert self._new_num_frames is not None
                self._new_num_frames += 1

        self._num_frames += 1

        if fps is not None:
            time_to_sleep = 1 / fps - (now - self._last_updated_at).total_seconds()

            if time_to_sleep > 0:
                time.sleep(time_to_sleep)

        self._last_updated_at = datetime.datetime.now()

    def elapsed(self) -> float:
        """
        Return the total number of seconds between the start and
        end interval.
        """

        assert self._finished_at is not None
        assert self._started_at is not None

        finished_at = self._finished_at or datetime.datetime.now()
        return (finished_at - self._started_at).total_seconds()

    def fps(self) -> float:
        """Compute the (approximate) frames per second."""

        assert self._num_frames is not None

        return self._num_frames / self.elapsed()
