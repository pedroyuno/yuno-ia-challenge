import random
from fastapi import FastAPI
from app.models import TransactionRequest, TransactionResponse, TransactionStatus
from app.processors import PROCESSORS

app = FastAPI(
    title="Zephyr Smart Routing Engine",
    description="Health-aware payment routing with automatic failover",
    version="0.1.0",
)


@app.post("/transactions", response_model=TransactionResponse)
def create_transaction(request: TransactionRequest):
    processor = random.choice(list(PROCESSORS.values()))
    status = processor.process(request)

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
