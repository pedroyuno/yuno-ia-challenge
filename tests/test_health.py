from app.health import ProcessorHealthTracker, HealthRegistry, ProcessorStatus, HEALTH_THRESHOLD
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

    def test_mixed_results_above_threshold(self):
        tracker = ProcessorHealthTracker("p1")
        for _ in range(7):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(3):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.7
        assert tracker.status == ProcessorStatus.HEALTHY

    def test_mixed_results_below_threshold(self):
        tracker = ProcessorHealthTracker("p1")
        for _ in range(4):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(6):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.4
        assert tracker.status == ProcessorStatus.UNHEALTHY

    def test_exactly_at_threshold(self):
        tracker = ProcessorHealthTracker("p1")
        for _ in range(6):
            tracker.record(TransactionStatus.APPROVED)
        for _ in range(4):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.6
        assert tracker.status == ProcessorStatus.HEALTHY

    def test_sliding_window_evicts_old_results(self):
        tracker = ProcessorHealthTracker("p1", window_size=5)
        # Fill window with failures
        for _ in range(5):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.success_rate == 0.0
        assert tracker.status == ProcessorStatus.UNHEALTHY

        # Push in successes -- old failures drop off
        for _ in range(5):
            tracker.record(TransactionStatus.APPROVED)
        assert tracker.success_rate == 1.0
        assert tracker.status == ProcessorStatus.HEALTHY
        assert tracker.total_attempts == 5  # window size, not total ever

    def test_recovery_transition(self):
        tracker = ProcessorHealthTracker("p1", window_size=10)
        # Start unhealthy
        for _ in range(10):
            tracker.record(TransactionStatus.DECLINED)
        assert tracker.status == ProcessorStatus.UNHEALTHY

        # Gradually recover
        for _ in range(6):
            tracker.record(TransactionStatus.APPROVED)
        # Window: 4 failures + 6 successes = 60%
        assert tracker.success_rate == 0.6
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
