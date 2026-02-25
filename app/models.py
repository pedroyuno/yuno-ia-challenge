from pydantic import BaseModel, Field
from enum import Enum
from typing import Optional
import uuid


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


class TransactionResponse(BaseModel):
    transaction_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    amount: float
    currency: Currency
    status: TransactionStatus
    processor_id: str
    processor_name: str
    fee_percent: float
    message: str
