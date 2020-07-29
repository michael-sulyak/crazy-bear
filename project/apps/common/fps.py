import datetime
import typing


class FPSTracker:
    _started_at: typing.Optional[datetime.datetime] = None
    _finished_at: typing.Optional[datetime.datetime] = None
    _num_frames: typing.Optional[int] = None
    _new_started_at: typing.Optional[datetime.datetime] = None
    _new_num_frames: typing.Optional[int] = None
    _timedelta_for_duplicate: datetime.timedelta = datetime.timedelta(seconds=5)
    _timedelta_for_reset: datetime.timedelta = datetime.timedelta(seconds=10)

    def start(self):
        """Start the timer."""

        self._started_at = datetime.datetime.now()
        self._num_frames = 0
        self._finished_at = None

        return self

    def stop(self):
        """Stop the timer."""

        self._finished_at = datetime.datetime.now()

    def update(self):
        """
        Increment the total number of frames examined during the
        start and end intervals.
        """

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
                self._new_num_frames += 1

        self._num_frames += 1

    def elapsed(self):
        """
        Return the total number of seconds between the start and
        end interval.
        """

        finished_at = self._finished_at or datetime.datetime.now()
        return (finished_at - self._started_at).total_seconds()

    def fps(self):
        """Compute the (approximate) frames per second."""

        return self._num_frames / self.elapsed()
