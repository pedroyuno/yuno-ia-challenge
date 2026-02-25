# Zephyr Smart Routing Engine

A health-aware payment routing engine that intelligently distributes transactions across multiple payment processors with automatic failover and recovery.

Built for the Yuno Engineering Challenge — solving Zephyr Delivery's processor outage problem where a single processor failure caused $127K in lost GMV.

## Quick Start

```bash
# Install dependencies
pip3 install -r requirements.txt

# Start the server
python3 -m uvicorn app.main:app --reload

# Run unit tests
python3 -m pytest tests/ -v

# Run the failover demo (server must be running)
python3 test_scenario.py
```

The API will be available at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

## Architecture

```
app/
  main.py         API endpoints (FastAPI)
  processors.py   Mock payment processor simulators
  health.py       Sliding window health tracker
  router.py       Smart routing engine with circuit breaker
  models.py       Request/response schemas (Pydantic)
tests/
  test_health.py  Health tracker unit tests (11 tests)
  test_router.py  Router logic unit tests (6 tests)
test_scenario.py  End-to-end failover demo script
```

### Request Flow

```
Client request
    |
    v
POST /transactions
    |
    v
SmartRouter.select()
    |-- Filter to HEALTHY processors (success rate >= 60%)
    |-- Pick cheapest (lowest fee) among healthy ones
    |-- Every 10th txn: probe a random unhealthy processor
    |-- Fallback: if all unhealthy, pick highest success rate
    |
    v
MockProcessor.process()
    |-- Random success/failure based on configured rate
    |
    v
HealthRegistry.record()
    |-- Append result to sliding window (last 100 txns)
    |-- Recalculate success rate and status
    |
    v
Response to client
```

## API Reference

### POST /transactions

Submit a payment transaction. The routing engine selects the best processor automatically.

**Request:**
```json
{
  "amount": 25000,
  "currency": "COP",
  "description": "Order #1234"
}
```

Supported currencies: `COP`, `PEN`, `CLP`.

**Response:**
```json
{
  "transaction_id": "814536c0-1896-4238-8c89-ce2bcb45f9e7",
  "amount": 25000.0,
  "currency": "COP",
  "status": "approved",
  "processor_id": "processor_c",
  "processor_name": "QuickCharge",
  "fee_percent": 2.7,
  "message": "Transaction approved"
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

Reset all processors and clear all health data.

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

## Routing Algorithm

The smart router makes decisions based on two factors: **health** and **cost**.

### Health Tracking (Sliding Window)

Each processor has a sliding window of the last 100 transaction results. The success rate is calculated as `successes / total_attempts` within that window. A fresh processor with no data is assumed healthy (100% rate).

Why a sliding window instead of time-based? It's simpler, deterministic, and doesn't depend on clock synchronization. Old results naturally drop off as new ones arrive.

### Circuit Breaker

Processors are classified as:
- **Healthy**: success rate >= 60% — eligible for routing
- **Unhealthy**: success rate < 60% — excluded from routing

The 60% threshold is defined in `app/health.py` (`HEALTH_THRESHOLD`).

### Routing Selection

1. **Filter** to healthy processors only
2. **Select** the one with the lowest fee (cost-aware)
3. If all processors are unhealthy, **fall back** to the one with the highest current success rate

### Probe Mechanism (Auto-Recovery)

Without probes, an excluded processor would never get new transactions and could never recover. Every 10th transaction, the router sends one to a random unhealthy processor to test if it has recovered. As probes succeed, the processor's sliding window improves until it crosses back above the 60% threshold and re-enters the healthy pool.

The probe interval is defined in `app/router.py` (`PROBE_INTERVAL`).

## Testing

### Unit Tests (17 tests)

```bash
python3 -m pytest tests/ -v
```

**Health tracker tests** (`tests/test_health.py`):
- Empty tracker assumes healthy
- Success rate calculation with all successes, all failures, mixed results
- Exact threshold boundary (60%)
- Sliding window eviction of old results
- Recovery transition from unhealthy to healthy
- Registry multi-processor tracking and reset

**Router tests** (`tests/test_router.py`):
- Selects cheapest processor when all healthy
- Skips cheapest when it's unhealthy
- Excludes multiple unhealthy processors
- Falls back to highest success rate when all unhealthy
- Probes unhealthy processor every Nth transaction
- Auto-recovery after enough successful probes

### Failover Demo

```bash
python3 test_scenario.py
```

Runs 240 transactions across 3 phases:
1. **Normal**: all healthy, traffic goes to cheapest processor
2. **Outage**: QuickCharge drops to 10%, traffic shifts to PayFlow Pro
3. **Recovery**: QuickCharge restored, gradually re-enters via probes

## Design Decisions

**Why in-memory state?** This is a prototype. No database means zero setup, instant startup, and simpler code. For production, the health windows would be stored in Redis or a similar low-latency store.

**Why 100-transaction window?** Large enough to smooth out noise, small enough to react quickly to real degradation. In production, a time-based window (e.g., last 5 minutes) would adapt better to varying traffic volumes.

**Why probe every 10th transaction?** Balances recovery speed with risk. Too frequent and you waste traffic on a broken processor. Too infrequent and recovery takes forever. The 10% probe rate is a reasonable starting point.

**Why cost-aware routing?** The challenge mentions processors have different fees. When multiple processors are equally healthy, choosing the cheapest one saves the merchant money. This was a low-effort addition with real business value.

**Why fall back instead of rejecting?** When all processors are unhealthy, the system picks the least-bad option rather than refusing all transactions. In a payment context, a 40% success rate is still better than 0%.

## Future Improvements

Ideas not implemented but worth considering for production:

- **Currency-specific routing**: route COP transactions to processors with better Colombian bank coverage
- **Amount-based routing**: some processors handle high-value transactions better
- **Latency tracking**: prefer faster processors for better user experience
- **Weighted distribution**: spread traffic across healthy processors instead of all-or-nothing
- **Persistent health data**: survive server restarts with Redis-backed windows
- **Webhook notifications**: alert ops team when a circuit breaker trips
