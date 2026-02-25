import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from app.config import settings
from app.models import (
    TransactionRequest,
    TransactionResponse,
    TransactionStatus,
    HealthResponse,
    ProcessorHealthResponse,
)
from app.processors import PROCESSORS, ProcessorError
from app.health import HealthRegistry
from app.router import SmartRouter

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Zephyr Smart Routing Engine",
    description="Health-aware payment routing with automatic failover",
    version="1.0.0",
)

health_registry = HealthRegistry(list(PROCESSORS.keys()))
smart_router = SmartRouter(PROCESSORS, health_registry)

# In-memory idempotency store: idempotency_key -> cached TransactionResponse.
# In production this would be backed by Redis with a TTL.
_idempotency_store: dict[str, TransactionResponse] = {}


@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(request: TransactionRequest):
    if request.idempotency_key and request.idempotency_key in _idempotency_store:
        return _idempotency_store[request.idempotency_key]

    processor = smart_router.select()

    try:
        status = processor.process(request)
    except ProcessorError as exc:
        logger.warning("Processor %s error: %s", processor.id, exc.reason)
        status = TransactionStatus.DECLINED
        health_registry.record(processor.id, status)
        response = TransactionResponse(
            amount=request.amount,
            currency=request.currency,
            status=status,
            processor_id=processor.id,
            processor_name=processor.name,
            fee_percent=processor.fee_percent,
            message=f"Processor error: {exc.reason}",
            request_id=request.request_id,
        )
        if request.idempotency_key:
            _idempotency_store[request.idempotency_key] = response
        return response

    health_registry.record(processor.id, status)

    message = (
        "Transaction approved"
        if status == TransactionStatus.APPROVED
        else "Transaction declined by processor"
    )

    response = TransactionResponse(
        amount=request.amount,
        currency=request.currency,
        status=status,
        processor_id=processor.id,
        processor_name=processor.name,
        fee_percent=processor.fee_percent,
        message=message,
        request_id=request.request_id,
    )

    if request.idempotency_key:
        _idempotency_store[request.idempotency_key] = response

    return response


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    return (STATIC_DIR / "health.html").read_text()


@app.get("/health", response_model=HealthResponse)
def get_health():
    trackers = health_registry.get_all_trackers()
    processors = []

    for pid, tracker in trackers.items():
        proc = PROCESSORS[pid]
        processors.append(
            ProcessorHealthResponse(
                processor_id=proc.id,
                processor_name=proc.name,
                success_rate=round(tracker.success_rate, 4),
                status=tracker.status.value,
                total_attempts=tracker.total_attempts,
                total_successes=tracker.total_successes,
                fee_percent=proc.fee_percent,
                is_routing_enabled=tracker.success_rate >= settings.health_threshold,
            )
        )

    return HealthResponse(
        processors=processors,
        health_threshold=settings.health_threshold,
    )


# --- Simulation endpoints ---


@app.post("/simulate/outage/{processor_id}")
def simulate_outage(processor_id: str):
    if processor_id not in PROCESSORS:
        raise HTTPException(status_code=404, detail=f"Processor '{processor_id}' not found")
    processor = PROCESSORS[processor_id]
    processor.success_rate = 0.10
    return {
        "message": f"Outage simulated for {processor.name}",
        "processor_id": processor_id,
        "success_rate": processor.success_rate,
    }


@app.post("/simulate/recover/{processor_id}")
def simulate_recover(processor_id: str):
    if processor_id not in PROCESSORS:
        raise HTTPException(status_code=404, detail=f"Processor '{processor_id}' not found")
    processor = PROCESSORS[processor_id]
    processor.success_rate = processor.base_success_rate
    return {
        "message": f"Processor {processor.name} recovered",
        "processor_id": processor_id,
        "success_rate": processor.success_rate,
    }


@app.post("/simulate/reset")
def simulate_reset():
    for processor in PROCESSORS.values():
        processor.success_rate = processor.base_success_rate
    health_registry.reset()
    smart_router._tx_count = 0
    _idempotency_store.clear()
    return {"message": "All processors and health data reset"}
