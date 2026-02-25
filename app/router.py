import random
from app.processors import MockProcessor
from app.health import HealthRegistry, ProcessorStatus

PROBE_INTERVAL = 10


class SmartRouter:
    """
    Selects the best processor based on health status and cost.

    Routing logic:
    1. Every PROBE_INTERVAL transactions, send one to a random unhealthy
       processor to check if it has recovered (circuit half-open probe).
    2. Otherwise, filter to processors with HEALTHY status.
    3. Among healthy processors, pick the one with the lowest fee (cost-aware).
    4. If ALL processors are unhealthy, fall back to the one with the
       highest current success rate.
    """

    def __init__(self, processors: dict[str, MockProcessor], health: HealthRegistry):
        self._processors = processors
        self._health = health
        self._tx_count = 0

    def select(self) -> MockProcessor:
        self._tx_count += 1

        healthy = []
        unhealthy = []

        for pid, processor in self._processors.items():
            tracker = self._health.get_tracker(pid)
            if tracker.status == ProcessorStatus.HEALTHY:
                healthy.append(processor)
            else:
                unhealthy.append(processor)

        if unhealthy and self._tx_count % PROBE_INTERVAL == 0:
            return random.choice(unhealthy)

        if healthy:
            return min(healthy, key=lambda p: p.fee_percent)

        best = max(
            self._processors.values(),
            key=lambda p: self._health.get_tracker(p.id).success_rate,
        )
        return best
