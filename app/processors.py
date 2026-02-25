import random
from dataclasses import dataclass, field
from app.models import TransactionRequest, TransactionStatus


class ProcessorError(Exception):
    """Raised when a processor fails to handle a transaction (timeout, network error, etc.)."""

    def __init__(self, processor_id: str, reason: str = "processor unavailable"):
        self.processor_id = processor_id
        self.reason = reason
        super().__init__(f"{processor_id}: {reason}")


@dataclass
class MockProcessor:
    id: str
    name: str
    base_success_rate: float
    fee_percent: float
    error_rate: float = 0.0
    _current_success_rate: float = field(init=False)

    def __post_init__(self):
        self._current_success_rate = self.base_success_rate

    @property
    def success_rate(self) -> float:
        return self._current_success_rate

    @success_rate.setter
    def success_rate(self, value: float):
        self._current_success_rate = max(0.0, min(1.0, value))

    def process(self, request: TransactionRequest) -> TransactionStatus:
        if random.random() < self.error_rate:
            raise ProcessorError(self.id, "connection timeout")

        if random.random() < self._current_success_rate:
            return TransactionStatus.APPROVED
        return TransactionStatus.DECLINED


PROCESSORS: dict[str, MockProcessor] = {
    "processor_a": MockProcessor(
        id="processor_a",
        name="PayFlow Pro",
        base_success_rate=0.85,
        fee_percent=2.9,
    ),
    "processor_b": MockProcessor(
        id="processor_b",
        name="GlobalPay",
        base_success_rate=0.90,
        fee_percent=3.1,
    ),
    "processor_c": MockProcessor(
        id="processor_c",
        name="QuickCharge",
        base_success_rate=0.80,
        fee_percent=2.7,
    ),
}
