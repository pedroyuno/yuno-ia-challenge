from fastapi.testclient import TestClient
from app.main import app, _idempotency_store, health_registry, smart_router
from app.processors import PROCESSORS


client = TestClient(app)


def _reset():
    for p in PROCESSORS.values():
        p.success_rate = p.base_success_rate
    health_registry.reset()
    smart_router._tx_count = 0
    _idempotency_store.clear()


class TestIdempotency:

    def test_duplicate_key_returns_same_response(self):
        _reset()
        payload = {"amount": 100, "currency": "COP", "idempotency_key": "key-123"}

        first = client.post("/transactions", json=payload).json()
        second = client.post("/transactions", json=payload).json()

        assert first["transaction_id"] == second["transaction_id"]
        assert first["status"] == second["status"]
        assert first["processor_id"] == second["processor_id"]
        assert first["timestamp"] == second["timestamp"]

    def test_different_keys_processed_independently(self):
        _reset()
        r1 = client.post("/transactions", json={"amount": 100, "currency": "COP", "idempotency_key": "a"}).json()
        r2 = client.post("/transactions", json={"amount": 100, "currency": "COP", "idempotency_key": "b"}).json()

        assert r1["transaction_id"] != r2["transaction_id"]

    def test_no_key_processes_every_time(self):
        _reset()
        payload = {"amount": 100, "currency": "COP"}

        r1 = client.post("/transactions", json=payload).json()
        r2 = client.post("/transactions", json=payload).json()

        assert r1["transaction_id"] != r2["transaction_id"]

    def test_reset_clears_idempotency_store(self):
        _reset()
        payload = {"amount": 100, "currency": "COP", "idempotency_key": "reset-test"}

        first = client.post("/transactions", json=payload).json()
        client.post("/simulate/reset")
        second = client.post("/transactions", json=payload).json()

        assert first["transaction_id"] != second["transaction_id"]


class TestRequestIdPropagation:

    def test_request_id_echoed_in_response(self):
        _reset()
        resp = client.post("/transactions", json={
            "amount": 500, "currency": "PEN", "request_id": "trace-abc-123"
        }).json()
        assert resp["request_id"] == "trace-abc-123"

    def test_no_request_id_returns_null(self):
        _reset()
        resp = client.post("/transactions", json={"amount": 500, "currency": "PEN"}).json()
        assert resp["request_id"] is None


class TestProcessorErrorHandling:

    def test_processor_error_returns_declined_not_500(self):
        _reset()
        PROCESSORS["processor_c"].error_rate = 1.0
        try:
            # Force routing to processor_c by making it the only option
            # (it's cheapest, and all are healthy initially)
            resp = client.post("/transactions", json={"amount": 100, "currency": "COP"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "declined"
            assert "error" in data["message"].lower()
        finally:
            PROCESSORS["processor_c"].error_rate = 0.0

    def test_processor_error_recorded_as_declined(self):
        _reset()
        PROCESSORS["processor_c"].error_rate = 1.0
        try:
            client.post("/transactions", json={"amount": 100, "currency": "COP"})
            health = client.get("/health").json()
            proc_c = next(p for p in health["processors"] if p["processor_id"] == "processor_c")
            assert proc_c["total_attempts"] == 1
            assert proc_c["total_successes"] == 0
        finally:
            PROCESSORS["processor_c"].error_rate = 0.0
