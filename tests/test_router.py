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

        # Make "cheap" unhealthy
        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)

        # Should skip probe (tx_count=1, not multiple of 10)
        selected = router.select()
        assert selected.id == "mid"


class TestCircuitBreaker:

    def test_excludes_processor_below_threshold(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        # Make "cheap" and "mid" unhealthy
        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)
            health.record("mid", TransactionStatus.DECLINED)

        # Only "expensive" is healthy -- should be selected (not a probe tx)
        selected = router.select()
        assert selected.id == "expensive"

    def test_fallback_when_all_unhealthy(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        # Make all unhealthy, but "mid" with highest rate
        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)
            health.record("expensive", TransactionStatus.DECLINED)
        for _ in range(4):
            health.record("mid", TransactionStatus.APPROVED)
        for _ in range(6):
            health.record("mid", TransactionStatus.DECLINED)

        # All unhealthy: "mid" has 40% (highest), should be fallback
        selected = router.select()
        assert selected.id == "mid"


class TestProbeMechanism:

    def test_probes_unhealthy_processor_every_nth(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        # Make "cheap" unhealthy
        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)

        # Send 9 transactions (tx_count 1..9) -- none should probe
        for _ in range(9):
            selected = router.select()
            assert selected.id != "cheap"

        # 10th transaction should probe the unhealthy processor
        selected = router.select()
        assert selected.id == "cheap"


class TestAutoRecovery:

    def test_processor_recovers_after_successes(self):
        procs = make_processors()
        health = HealthRegistry(list(procs.keys()), window_size=10)
        router = SmartRouter(procs, health)

        # Make "cheap" unhealthy
        for _ in range(10):
            health.record("cheap", TransactionStatus.DECLINED)

        selected = router.select()
        assert selected.id != "cheap"

        # Simulate recovery: 7 successes push out 7 old failures
        # Window becomes: 3 DECLINED + 7 APPROVED = 70% > 60%
        for _ in range(7):
            health.record("cheap", TransactionStatus.APPROVED)

        # "cheap" is healthy again and cheapest -- should be selected
        selected = router.select()
        assert selected.id == "cheap"
