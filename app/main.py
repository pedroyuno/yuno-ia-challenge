from fastapi import FastAPI, HTTPException
from app.models import (
    TransactionRequest,
    TransactionResponse,
    TransactionStatus,
    HealthResponse,
    ProcessorHealthResponse,
)
from app.processors import PROCESSORS
from app.health import HealthRegistry, HEALTH_THRESHOLD
from app.router import SmartRouter

app = FastAPI(
    title="Zephyr Smart Routing Engine",
    description="Health-aware payment routing with automatic failover",
    version="0.3.0",
)

health_registry = HealthRegistry(list(PROCESSORS.keys()))
smart_router = SmartRouter(PROCESSORS, health_registry)


@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(request: TransactionRequest):
    processor = smart_router.select()
    status = processor.process(request)
    health_registry.record(processor.id, status)

    message = (
        "Transaction approved"
        if status == TransactionStatus.APPROVED
        else "Transaction declined by processor"
    )

    return TransactionResponse(
        amount=request.amount,
        currency=request.currency,
        status=status,
        processor_id=processor.id,
        processor_name=processor.name,
        fee_percent=processor.fee_percent,
        message=message,
    )


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
                is_routing_enabled=tracker.success_rate >= HEALTH_THRESHOLD,
            )
        )

    return HealthResponse(
        processors=processors,
        health_threshold=HEALTH_THRESHOLD,
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
    return {"message": "All processors and health data reset"}
