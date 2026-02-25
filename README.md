# Zephyr Smart Routing Engine

A health-aware payment routing engine that intelligently distributes transactions across multiple payment processors with automatic failover and recovery.

Built for the Yuno Engineering Challenge — solving Zephyr Delivery's processor outage problem where a single processor failure caused $127K in lost GMV.

## Quick Start

### Option A: Docker (one command)

```bash
docker-compose up --build
```

### Option B: Local Python

```bash
pip3 install -r requirements.txt
python3 -m uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`. Live health dashboard at `http://localhost:8000/dashboard`.

### Run Tests

```bash
python3 -m pytest tests/ -v
```

### Run the Failover Demo

```bash
# Server must be running first
python3 demo.py
```

## Architecture

```
app/
  config.py       Environment-based configuration (Pydantic Settings)
  main.py         API endpoints (FastAPI)
  processors.py   Mock payment processor simulators
  health.py       Thread-safe sliding window health tracker
  router.py       Smart routing engine with circuit breaker
  models.py       Request/response schemas (Pydantic)
  static/
    health.html   Real-time health dashboard
tests/
  test_health.py       Health tracker unit tests (14 tests)
  test_router.py       Router logic unit tests (7 tests)
  test_idempotency.py  Idempotency, tracing, and error handling tests (8 tests)
demo.py                Interactive failover demo script
test_scenario.py       Automated failover demo (no interaction)
Dockerfile             Container image
docker-compose.yml     One-command startup
```

### Request Flow

```
Client request
    |
    v
POST /transactions
    |-- Check idempotency_key → return cached response if duplicate
    |
    v
SmartRouter.select()
    |-- Filter out UNHEALTHY processors (success rate < 60%)
    |-- HEALTHY (>=80%) and DEGRADED (>=60%) are both eligible
    |-- Pick cheapest (lowest fee) among eligible
    |-- Every Nth txn: probe a random unhealthy processor
    |-- Fallback: if all unhealthy, pick highest success rate
    |
    v
MockProcessor.process()
    |-- Random success/failure based on configured rate
    |-- May raise ProcessorError (caught, recorded as DECLINED)
    |
    v
HealthRegistry.record()  [thread-safe]
    |-- Append result to sliding window (last 100 txns)
    |-- Recalculate success rate and status
    |
    v
Response to client (with transaction_id, timestamp, request_id)
```

## API Reference

### POST /transactions

Submit a payment transaction. The routing engine selects the best processor automatically.

**Request:**
```json
{
  "amount": 25000,
  "currency": "COP",
  "description": "Order #1234",
  "idempotency_key": "order-1234-attempt-1",
  "request_id": "trace-abc-123"
}
```

Supported currencies: `COP`, `PEN`, `CLP`.

- `idempotency_key` (optional): If the same key is sent twice, the original response is returned without re-processing. Prevents double-charging.
- `request_id` (optional): Client-supplied trace ID, echoed in the response for end-to-end observability.

**Response:**
```json
{
  "transaction_id": "814536c0-1896-4238-8c89-ce2bcb45f9e7",
  "timestamp": "2026-02-25T14:30:00.123456+00:00",
  "amount": 25000.0,
  "currency": "COP",
  "status": "approved",
  "processor_id": "processor_c",
  "processor_name": "QuickCharge",
  "fee_percent": 2.7,
  "message": "Transaction approved",
  "request_id": "trace-abc-123"
}
```

### GET /health

Real-time health metrics for all processors.

**Response:**
```json
{
  "processors": [
    {
      "processor_id": "processor_a",
      "processor_name": "PayFlow Pro",
      "success_rate": 0.85,
      "status": "healthy",
      "total_attempts": 44,
      "total_successes": 37,
      "fee_percent": 2.9,
      "is_routing_enabled": true
    },
    {
      "processor_id": "processor_c",
      "processor_name": "QuickCharge",
      "success_rate": 0.12,
      "status": "unhealthy",
      "total_attempts": 100,
      "total_successes": 12,
      "fee_percent": 2.7,
      "is_routing_enabled": false
    }
  ],
  "health_threshold": 0.6
}
```

### GET /dashboard

Live health dashboard (HTML page, auto-refreshes every 2 seconds).

### POST /simulate/outage/{processor_id}

Drop a processor's success rate to 10% (simulates downtime).

```bash
curl -X POST http://localhost:8000/simulate/outage/processor_c
```

### POST /simulate/recover/{processor_id}

Restore a processor to its original success rate.

```bash
curl -X POST http://localhost:8000/simulate/recover/processor_c
```

### POST /simulate/reset

Reset all processors, health data, and idempotency store.

```bash
curl -X POST http://localhost:8000/simulate/reset
```

Processor IDs: `processor_a`, `processor_b`, `processor_c`.

## Mock Processors

| Processor     | Name         | Base Success Rate | Fee   |
|---------------|--------------|-------------------|-------|
| processor_a   | PayFlow Pro  | 85%               | 2.9%  |
| processor_b   | GlobalPay    | 90%               | 3.1%  |
| processor_c   | QuickCharge  | 80%               | 2.7%  |

## Configuration

All settings are configurable via environment variables (prefixed with `ZEPHYR_`):

| Variable                  | Default | Description                                |
|---------------------------|---------|--------------------------------------------|
| `ZEPHYR_HEALTH_THRESHOLD` | 0.60    | Below this rate, processor is UNHEALTHY    |
| `ZEPHYR_DEGRADED_THRESHOLD`| 0.80   | Below this rate (but above health), DEGRADED |
| `ZEPHYR_WINDOW_SIZE`      | 100     | Sliding window size (number of transactions) |
| `ZEPHYR_PROBE_INTERVAL`   | 10      | Every Nth txn probes an unhealthy processor |

Example:
```bash
ZEPHYR_HEALTH_THRESHOLD=0.50 ZEPHYR_WINDOW_SIZE=200 python3 -m uvicorn app.main:app
```

## Routing Algorithm

The smart router makes decisions based on two factors: **health** and **cost**.

### Health Tracking (Sliding Window)

Each processor has a sliding window of the last N transaction results (default 100). The success rate is calculated as `successes / total_attempts` within that window. A fresh processor with no data is assumed healthy (100% rate). The tracker is thread-safe — a per-tracker `threading.Lock` protects all reads and writes to the deque, ensuring concurrent requests don't produce corrupted state.

Why a sliding window instead of time-based? It's simpler, deterministic, and doesn't depend on clock synchronization. Old results naturally drop off as new ones arrive. For production with varying traffic volumes, a time-based window (e.g., last 5 minutes) would adapt better — a sliding window of 100 can represent 10 seconds of traffic at peak or 10 minutes during low traffic.

### Processor Statuses

Processors are classified into three states for observability:
- **Healthy**: success rate >= 80% — fully operational
- **Degraded**: success rate >= 60% but < 80% — still routed to, but signaling trouble
- **Unhealthy**: success rate < 60% — circuit open, excluded from routing

Both HEALTHY and DEGRADED processors are eligible for routing. The distinction exists for observability: a degraded processor is a warning signal that operators can act on before it fully fails.

### Routing Selection

1. **Filter** to eligible processors (HEALTHY or DEGRADED)
2. **Select** the one with the lowest fee (cost-aware)
3. If all processors are unhealthy, **fall back** to the one with the highest current success rate

### Probe Mechanism (Auto-Recovery)

Without probes, an excluded processor would never get new transactions and could never recover. Every Nth transaction (default 10), the router sends one to a random unhealthy processor to test if it has recovered. As probes succeed, the processor's sliding window improves until it crosses back above the 60% threshold and re-enters the eligible pool.

### Error Handling

If a processor raises an error (timeout, network failure), the transaction is recorded as DECLINED and the client receives a clean error response (not a 500). This ensures processor failures degrade the health window naturally rather than crashing the endpoint.

## Idempotency

Payment APIs must be idempotent — submitting the same transaction twice should not charge the customer twice. The `idempotency_key` field in the request enables this: if the client retries with the same key, the server returns the cached response from the first attempt without re-processing.

The in-memory store is cleared on `/simulate/reset`. In production, this would be backed by Redis with a TTL (e.g., 24 hours) to limit memory usage while covering realistic retry windows.

## Testing

### Unit Tests (29 tests)

```bash
python3 -m pytest tests/ -v
```

**Health tracker tests** (`tests/test_health.py` — 14 tests):
- Empty tracker assumes healthy
- Success rate calculation with all successes, all failures, mixed results
- Degraded status between 60-80% (3 threshold boundary tests)
- Full recovery transition: unhealthy -> degraded -> healthy
- Sliding window eviction of old results
- Registry multi-processor tracking and reset

**Router tests** (`tests/test_router.py` — 7 tests):
- Selects cheapest processor when all healthy
- Skips cheapest when it's unhealthy
- Routes to degraded processor if it's cheapest
- Excludes multiple unhealthy processors
- Falls back to highest success rate when all unhealthy
- Probes unhealthy processor every Nth transaction
- Auto-recovery after enough successful probes

**Idempotency, tracing, and error tests** (`tests/test_idempotency.py` — 8 tests):
- Duplicate idempotency key returns same response
- Different keys processed independently
- No key processes every time
- Reset clears idempotency store
- Request ID echoed in response
- Absent request ID returns null
- Processor error returns DECLINED (not 500)
- Processor error recorded in health window

### Failover Demo

```bash
python3 demo.py
```

Interactive demo with 3 phases (300 transactions total):
1. **Normal**: all healthy, traffic goes to cheapest processor
2. **Outage**: QuickCharge drops to 10%, traffic shifts to PayFlow Pro
3. **Recovery**: QuickCharge restored, gradually re-enters via probes

Open `http://localhost:8000/dashboard` alongside to watch it live.

## Design Decisions

**Why fixed-interval probing over exponential backoff?** Exponential backoff is standard for client retries, but circuit-breaker probes have a different goal. With exponential backoff, a processor that was down for 10 minutes could take another 10+ minutes before being probed again, even if it recovered instantly. Fixed-interval probing (every 10th transaction) guarantees recovery detection within a bounded window regardless of outage duration. The tradeoff is that during a long outage we "waste" 10% of transactions on a dead processor — acceptable for a prototype, and in production the probe rate could be adaptive.

**Why cheapest-first over weighted distribution?** Deterministic cheapest-first is easier to reason about, test, and demonstrate. The routing decision is always explainable: "we picked processor X because it has the lowest fee among healthy processors." For production with high traffic, weighted distribution across healthy processors would reduce single-processor hotspots and provide better load resilience. But for a prototype with 3 processors, the added complexity of probability-weighted selection isn't justified by the benefits.

**Why three status levels (healthy/degraded/unhealthy)?** Two states (healthy/unhealthy) work for routing decisions, but three states provide better observability. A processor at 65% success rate is technically still routed to, but operators should know it's degrading before it hits the 60% threshold and gets fully excluded. The DEGRADED state is a warning signal without changing routing behavior — the circuit breaker only trips at the UNHEALTHY threshold.

**Why idempotency?** In payment systems, network failures and client retries are expected. Without idempotency, a timeout followed by a retry could result in the customer being charged twice. The `idempotency_key` pattern is a standard solution: the server caches the response keyed by a client-supplied identifier, and returns the cached result for duplicate keys. This is not optional for production payment APIs — it's a fundamental requirement.

**Why in-memory state?** This is a prototype. No database means zero setup, instant startup, and simpler code. For production, the health windows would be stored in Redis or a similar low-latency store, and the idempotency store would use Redis with a TTL.

**Why 100-transaction window?** Large enough to smooth out noise, small enough to react quickly to real degradation. In production, a time-based window (e.g., last 5 minutes) would adapt better to varying traffic volumes.

**Why fall back instead of rejecting?** When all processors are unhealthy, the system picks the least-bad option rather than refusing all transactions. In a payment context, a 40% success rate is still better than 0%.

## Future Improvements

Ideas not implemented but worth considering for production:

- **Currency-specific routing**: route COP transactions to processors with better Colombian bank coverage
- **Amount-based routing**: some processors handle high-value transactions better
- **Latency tracking**: prefer faster processors for better user experience
- **Weighted distribution**: spread traffic across healthy processors instead of all-or-nothing
- **Persistent health data**: survive server restarts with Redis-backed windows
- **Webhook notifications**: alert ops team when a circuit breaker trips
- **Adaptive probe rate**: increase probe frequency during business hours, decrease overnight
- **PSP error code awareness**: distinguish between "insufficient funds" (customer issue) and "gateway timeout" (processor issue) to avoid penalizing processors for customer-side declines
