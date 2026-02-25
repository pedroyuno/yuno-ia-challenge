from app.processors import MockProcessor
from app.health import HealthRegistry
from app.router import SmartRouter
from app.models import TransactionStatus


def make_processors() -> dict[str, MockProcessor]:
    return {
        "cheap": MockProcessor(id="cheap", name="Cheap", base_success_rate=0.9, fee_percent=2.0),
        "mid": MockProcessor(id="mid", name="Mid", base_success_rate=0.9, fee_percent=3.0),
        "expensive": MockProcessor(id="expensive", name="Expensive", base_success_rate=0.9, fee_percent=4.0),
    }


class TestCostAwareRouting:

    def test_selects_cheapest_when_all_healthy(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()))
        router = SmartRouter(procs, health)

        selected = router.select()
        assert selected.id == "cheap"

    def test_skips_cheapest_when_unhealthy(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)

        selected = router.select()
        assert selected.id == "mid"

    def test_routes_to_degraded_processor_if_cheapest(self):
        """DEGRADED processors (60-80% rate) are still eligible for routing."""
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        # Make "cheap" degraded (70% success rate)
        for _ in range(7):
            health.record("cheap", TransactionStatus.APPROVED)
        for _ in range(3):
            health.record("cheap", TransactionStatus.DECLINED)

        selected = router.select()
        assert selected.id == "cheap"


class TestCircuitBreaker:

    def test_excludes_processor_below_threshold(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)
            health.record("mid", TransactionStatus.DECLINED)

        selected = router.select()
        assert selected.id == "expensive"

    def test_fallback_when_all_unhealthy(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)
            health.record("expensive", TransactionStatus.DECLINED)
        for _ in range(4):
            health.record("mid", TransactionStatus.APPROVED)
        for _ in range(6):
            health.record("mid", TransactionStatus.DECLINED)

        selected = router.select()
        assert selected.id == "mid"


class TestProbeMechanism:

    def test_probes_unhealthy_processor_every_nth(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)

        for _ in range(9):
            selected = router.select()
            assert selected.id != "cheap"

        selected = router.select()
        assert selected.id == "cheap"


class TestAutoRecovery:

    def test_processor_recovers_after_successes(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)

        selected = router.select()
        assert selected.id != "cheap"

        # 7 successes push out 7 old failures -> 70% -> DEGRADED -> still eligible
        for _ in range(7):
            health.record("cheap", TransactionStatus.APPROVED)

        selected = router.select()
        assert selected.id == "cheap"
