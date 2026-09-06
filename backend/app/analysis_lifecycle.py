"""Thread-safe cooperative cancellation for the single backend worker."""
from collections import OrderedDict, deque
from typing import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Event, Lock
from time import monotonic


class AnalysisCancelled(Exception):
    pass


class DuplicateAnalysis(Exception):
    pass


_current_cancel: ContextVar[Event | None] = ContextVar("analysis_cancel", default=None)


def check_analysis_cancelled() -> None:
    event = _current_cancel.get()
    if event is not None and event.is_set():
        raise AnalysisCancelled()


class AnalysisRegistry:
    def __init__(self, clock: Callable[[], float] = monotonic):
        self._lock = Lock()
        self._clock = clock
        self._started: deque[float] = deque()
        self._active: dict[str, Event] = {}
        # Bounded, short-lived tombstones handle cancel arriving before analyze.
        self._recent: OrderedDict[str, tuple[float, str]] = OrderedDict()

    def _prune_metrics(self, now: float) -> None:
        while self._started and self._started[0] <= now - 86400:
            self._started.popleft()

    def metrics(self) -> dict[str, int]:
        """Admitted starts, including failed/cancelled work; resets on restart."""
        with self._lock:
            self._prune_metrics(self._clock())
            return {
                "ongoingAnalyses": len(self._active),
                "analysesLast24Hours": len(self._started),
            }

    def _prune(self):
        now = monotonic()
        while self._recent and next(iter(self._recent.values()))[0] <= now - 300:
            self._recent.popitem(last=False)

    def _remember(self, analysis_id, status):
        self._recent[analysis_id] = (monotonic(), status)
        self._recent.move_to_end(analysis_id)
        while len(self._recent) > 1024:
            self._recent.popitem(last=False)

    @contextmanager
    def track(self, analysis_id: str):
        with self._lock:
            self._prune()
            if analysis_id in self._active:
                raise DuplicateAnalysis()
            if analysis_id in self._recent:
                if self._recent[analysis_id][1] == "cancelled":
                    raise AnalysisCancelled()
                raise DuplicateAnalysis()
            event = Event()
            self._active[analysis_id] = event
            now = self._clock()
            self._prune_metrics(now)
            self._started.append(now)
        token = _current_cancel.set(event)
        try:
            check_analysis_cancelled()
            yield
            check_analysis_cancelled()
        finally:
            _current_cancel.reset(token)
            with self._lock:
                self._active.pop(analysis_id, None)
                self._remember(analysis_id, "cancelled" if event.is_set() else "completed")

    def cancel(self, analysis_id: str) -> str:
        with self._lock:
            self._prune()
            if analysis_id in self._active:
                self._active[analysis_id].set()
                return "cancelling"
            if analysis_id in self._recent:
                return self._recent[analysis_id][1]
            self._remember(analysis_id, "cancelled")
            return "cancelled"


analysis_registry = AnalysisRegistry()
