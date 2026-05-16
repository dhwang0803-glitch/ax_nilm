"""공유 입력 타입 — nilm-engine DisaggregationResult 인터페이스 계약."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class DisaggregationResult:
    """nilm-engine 출력 스키마.

    confidence < 0.6 구간은 모니터링 레이어에서 자동 제외.
    """

    appliance_type: str
    timestamp: datetime
    power_w: float
    confidence: float
    is_on: bool = False
