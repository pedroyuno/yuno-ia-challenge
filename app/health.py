from collections import deque
from enum import Enum
from app.models import TransactionStatus

HEALTH_THRESHOLD = 0.60
WINDOW_SIZE = 100


class ProcessorStatus(str, Enum):
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class ProcessorHealthTracker:
    """Tracks success/failure over a sliding window of the last N transactions."""

    def __init__(self, processor_id: str, window_size: int = WINDOW_SIZE):
        self.processor_id = processor_id
        self.window_size = window_size
        self._results: deque[bool] = deque(maxlen=window_size)

    def record(self, status: TransactionStatus):
        self._results.append(status == TransactionStatus.APPROVED)

    @property
    def total_attempts(self) -> int:
        return len(self._results)

    @property
    def total_successes(self) -> int:
        return sum(self._results)

    @property
    def success_rate(self) -> float:
        if not self._results:
            return 1.0  # assume healthy until proven otherwise
        return self.total_successes / self.total_attempts

    @property
    def status(self) -> ProcessorStatus:
        if self.success_rate >= HEALTH_THRESHOLD:
            return ProcessorStatus.HEALTHY
        return ProcessorStatus.UNHEALTHY


class HealthRegistry:
    """Central registry of health trackers for all processors."""

    def __init__(self, processor_ids: list[str], window_size: int = WINDOW_SIZE):
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
            tracker._results.clear()
