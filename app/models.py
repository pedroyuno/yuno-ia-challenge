import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Currency(str, Enum):
    COP = "COP"
    PEN = "PEN"
    CLP = "CLP"


class TransactionStatus(str, Enum):
    APPROVED = "approved"
    DECLINED = "declined"


class TransactionRequest(BaseModel):
    amount: float = Field(..., gt=0, description="Transaction amount")
    currency: Currency = Field(..., description="ISO currency code")
    description: Optional[str] = None
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Client-supplied key to prevent duplicate processing. "
        "If the same key is sent twice, the original response is returned.",
    )
    request_id: Optional[str] = Field(
        default=None,
        description="Client-supplied trace ID propagated through the response for observability.",
    )


class TransactionResponse(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    amount: float
    currency: Currency
    status: TransactionStatus
    processor_id: str
    processor_name: str
    fee_percent: float
    message: str
    request_id: Optional[str] = None


class ProcessorHealthResponse(BaseModel):
    processor_id: str
    processor_name: str
    success_rate: float
    status: str
    total_attempts: int
    total_successes: int
    fee_percent: float
    is_routing_enabled: bool


class HealthResponse(BaseModel):
    processors: list[ProcessorHealthResponse]
    health_threshold: float
