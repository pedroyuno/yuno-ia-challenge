import threading
from collections import deque
from enum import Enum

from app.config import settings
from app.models import TransactionStatus


class ProcessorStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ProcessorHealthTracker:
    """Tracks success/failure over a sliding window of the last N transactions.

    Thread-safe: all reads and writes to the window are protected by a lock
    so concurrent requests don't corrupt the deque or produce torn reads.
    """

    def __init__(self, processor_id: str, window_size: int = settings.window_size):
        self.processor_id = processor_id
        self.window_size = window_size
        self._results: deque[bool] = deque(maxlen=window_size)
        self._lock = threading.Lock()

    def record(self, status: TransactionStatus):
        with self._lock:
            self._results.append(status == TransactionStatus.APPROVED)

    @property
    def total_attempts(self) -> int:
        with self._lock:
            return len(self._results)

    @property
    def total_successes(self) -> int:
        with self._lock:
            return sum(self._results)

    @property
    def success_rate(self) -> float:
        with self._lock:
            if not self._results:
                return 1.0
            return sum(self._results) / len(self._results)

    @property
    def status(self) -> ProcessorStatus:
        rate = self.success_rate
        if rate >= settings.degraded_threshold:
            return ProcessorStatus.HEALTHY
        if rate >= settings.health_threshold:
            return ProcessorStatus.DEGRADED
        return ProcessorStatus.UNHEALTHY


class HealthRegistry:
    """Central registry of health trackers for all processors."""

    def __init__(self, processor_ids: list[str], window_size: int = settings.window_size):
        self._trackers = {
            pid: ProcessorHealthTracker(pid, window_size)
            for pid in processor_ids
        }

    def record(self, processor_id: str, status: TransactionStatus):
        self._trackers[processor_id].record(status)

    def get_tracker(self, processor_id: str) -> ProcessorHealthTracker:
        return self._trackers[processor_id]

    def get_all_trackers(self) -> dict[str, ProcessorHealthTracker]:
        return dict(self._trackers)

    def reset(self):
        for tracker in self._trackers.values():
            with tracker._lock:
                tracker._results.clear()
