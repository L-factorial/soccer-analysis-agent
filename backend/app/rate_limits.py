"""Process-wide, thread-safe admission limits for analysis and commentary."""

from collections import deque
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from math import ceil
from threading import BoundedSemaphore, Lock
from time import monotonic


class LimitExceeded(Exception):
    def __init__(self, code: str, message: str, retry_after: int) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class InMemoryRateLimiter:
    """Global limits for one worker; state resets when the process restarts.

    Commentary uses rolling 60-second and 24-hour windows. Admitted attempts
    consume quota even if generation fails; rejected attempts consume nothing.
    """

    def __init__(self, *, clock: Callable[[], float] = monotonic) -> None:
        self._analysis_slots = BoundedSemaphore(5)
        self._commentary_lock = Lock()
        self._commentary_requests: deque[float] = deque()
        self._clock = clock

    @contextmanager
    def analysis_slot(self) -> Iterator[None]:
        if not self._analysis_slots.acquire(blocking=False):
            raise LimitExceeded(
                "analysis_capacity_exceeded",
                "Five analyses are already running. Please try again later.",
                1,
            )
        try:
            yield
        finally:
            self._analysis_slots.release()

    def reserve_commentary(self) -> None:
        with self._commentary_lock:
            now = self._clock()
            while self._commentary_requests and self._commentary_requests[0] <= now - 86400:
                self._commentary_requests.popleft()

            recent = [timestamp for timestamp in self._commentary_requests if timestamp > now - 60]
            waits = []
            if len(recent) >= 3:
                waits.append(recent[-3] + 60 - now)
            if len(self._commentary_requests) >= 24:
                waits.append(self._commentary_requests[0] + 86400 - now)
            if waits:
                raise LimitExceeded(
                    "commentary_rate_limit_exceeded",
                    "Commentary is limited to 3 requests per minute and 24 per day. Please try again later.",
                    max(1, ceil(max(waits))),
                )
            self._commentary_requests.append(now)


rate_limiter = InMemoryRateLimiter()
