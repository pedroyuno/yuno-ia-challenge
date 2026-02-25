import random
from app.config import settings
from app.processors import MockProcessor
from app.health import HealthRegistry, ProcessorStatus


class SmartRouter:
    """
    Selects the best processor based on health status and cost.

    Routing logic:
    1. Every PROBE_INTERVAL transactions, send one to a random unhealthy
       processor to check if it has recovered (circuit half-open probe).
    2. Otherwise, filter to processors that are not UNHEALTHY (i.e., both
       HEALTHY and DEGRADED processors are eligible for routing).
    3. Among eligible processors, pick the one with the lowest fee (cost-aware).
    4. If ALL processors are unhealthy, fall back to the one with the
       highest current success rate.

    Why fixed-interval probing over exponential backoff:
    Exponential backoff is standard for client retries, but for circuit-breaker
    probes the goal is different — we want predictable, bounded recovery time.
    With exponential backoff, a processor that was down for 10 minutes could
    take another 10+ minutes of backing off before being probed, even though
    it recovered instantly. Fixed-interval probing guarantees recovery detection
    within at most PROBE_INTERVAL transactions regardless of outage duration.

    Why cheapest-first over weighted distribution:
    Deterministic cheapest-first is simpler and easier to verify in tests and
    demos. For production with high traffic, weighted distribution across
    healthy processors would reduce single-processor hotspots and provide
    better resilience — but for a prototype with 3 processors, the complexity
    isn't justified.
    """

    def __init__(self, processors: dict[str, MockProcessor], health: HealthRegistry):
        self._processors = processors
        self._health = health
        self._tx_count = 0

    def select(self) -> MockProcessor:
        self._tx_count += 1

        eligible = []
        unhealthy = []

        for pid, processor in self._processors.items():
            tracker = self._health.get_tracker(pid)
            if tracker.status == ProcessorStatus.UNHEALTHY:
                unhealthy.append(processor)
            else:
                eligible.append(processor)

        if unhealthy and self._tx_count % settings.probe_interval == 0:
            return random.choice(unhealthy)

        if eligible:
            return min(eligible, key=lambda p: p.fee_percent)

        best = max(
            self._processors.values(),
            key=lambda p: self._health.get_tracker(p.id).success_rate,
        )
        return best
