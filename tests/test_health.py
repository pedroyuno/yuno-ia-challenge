from app.health import ProcessorHealthTracker, HealthRegistry, ProcessorStatus
from app.config import settings
from app.models import TransactionStatus


class TestProcessorHealthTracker:

    def test_empty_tracker_assumes_healthy(self):
        tracker = ProcessorHealthTracker("p1")
        assert tracker.success_rate == 1.0
        assert tracker.status == ProcessorStatus.HEALTHY
        assert tracker.total_attempts == 0

    def test_all_successes(self):
        tracker = ProcessorHealthTracker("p1")
        for _ in range(10):
            tracker.record(TransactionStatus.APPROVED)
        assert tracker.success_rate == 1.0
        assert tracker.status == ProcessorStatus.HEALTHY
        assert tracker.total_attempts == 10
        assert tracker.total_successes == 10

    def test_all_failures(self):
        tracker = ProcessorHealthTracker("p1")
        for _ in range(10):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.0
        assert tracker.status == ProcessorStatus.UNHEALTHY

    def test_mixed_results_above_degraded_threshold(self):
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(9):
            tracker.record(TransactionStatus.APPROVED)
        tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.9
        assert tracker.status == ProcessorStatus.HEALTHY

    def test_degraded_status_between_thresholds(self):
        """Success rate >= 60% but < 80% should be DEGRADED."""
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(7):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(3):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.7
        assert tracker.status == ProcessorStatus.DEGRADED

    def test_exactly_at_health_threshold_is_degraded(self):
        """60% exactly is above UNHEALTHY but below HEALTHY — should be DEGRADED."""
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(6):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(4):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.6
        assert tracker.status == ProcessorStatus.DEGRADED

    def test_exactly_at_degraded_threshold_is_healthy(self):
        """80% exactly should be HEALTHY."""
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(8):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(2):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.8
        assert tracker.status == ProcessorStatus.HEALTHY

    def test_below_health_threshold_is_unhealthy(self):
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(4):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(6):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.4
        assert tracker.status == ProcessorStatus.UNHEALTHY

    def test_sliding_window_evicts_old_results(self):
        tracker = ProcessorHealthTracker("p1", window_size=5)
        for _ in range(5):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.0
        assert tracker.status == ProcessorStatus.UNHEALTHY

        for _ in range(5):
            tracker.record(TransactionStatus.APPROVED)
        assert tracker.success_rate == 1.0
        assert tracker.status == ProcessorStatus.HEALTHY
        assert tracker.total_attempts == 5

    def test_recovery_transition(self):
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(10):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.status == ProcessorStatus.UNHEALTHY

        for _ in range(6):
            tracker.record(TransactionStatus.APPROVED)
        # Window: 4 failures + 6 successes = 60% -> DEGRADED
        assert tracker.success_rate == 0.6
        assert tracker.status == ProcessorStatus.DEGRADED

    def test_full_recovery_to_healthy(self):
        tracker = ProcessorHealthTracker("p1", window_size=10)
        for _ in range(10):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.status == ProcessorStatus.UNHEALTHY

        for _ in range(8):
            tracker.record(TransactionStatus.APPROVED)
        # Window: 2 failures + 8 successes = 80% -> HEALTHY
        assert tracker.success_rate == 0.8
        assert tracker.status == ProcessorStatus.HEALTHY


class TestHealthRegistry:

    def test_tracks_multiple_processors(self):
        registry = HealthRegistry(["p1", "p2"])
        registry.record("p1", TransactionStatus.APPROVED)
        registry.record("p2", TransactionStatus.DECLINED)

        assert registry.get_tracker("p1").success_rate == 1.0
        assert registry.get_tracker("p2").success_rate == 0.0

    def test_reset_clears_all_data(self):
        registry = HealthRegistry(["p1", "p2"])
        registry.record("p1", TransactionStatus.APPROVED)
        registry.record("p2", TransactionStatus.DECLINED)
        registry.reset()

        assert registry.get_tracker("p1").total_attempts == 0
        assert registry.get_tracker("p2").total_attempts == 0

    def test_get_all_trackers(self):
        registry = HealthRegistry(["p1", "p2", "p3"])
        trackers = registry.get_all_trackers()
        assert len(trackers) == 3
        assert set(trackers.keys()) == {"p1", "p2", "p3"}
