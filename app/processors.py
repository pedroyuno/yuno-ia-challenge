import random
from dataclasses import dataclass, field
from app.models import TransactionRequest, TransactionStatus


@dataclass
class MockProcessor:
    id: str
    name: str
    base_success_rate: float
    fee_percent: float
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
