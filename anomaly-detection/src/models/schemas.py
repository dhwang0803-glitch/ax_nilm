"""ANOM-000: 이상 탐지 파이프라인 공유 데이터 타입."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class Severity(Enum):
    """ANOM-000-1: 이상 이벤트 심각도 — AlertNotifier 라우팅 기준."""

    HIGH = "HIGH"      # 즉시 푸시 알림 | 최대 전력 > 기준 +30%
    MEDIUM = "MEDIUM"  # 일일 요약 포함 | 소비량 > 3개월 평균 +20%
    LOW = "LOW"        # 주간 리포트 포함 | 주기성 패턴 편차


_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.HIGH: 0,
    Severity.MEDIUM: 1,
    Severity.LOW: 2,
}


class AnomalyType(Enum):
    """ANOM-000-2: 이상 유형 — DiagnosisReporter 분기 기준."""

    CONSUMPTION_INCREASE = "CONSUMPTION_INCREASE"  # 소비량 > 3개월 평균 +20%
    ABNORMAL_RUNTIME = "ABNORMAL_RUNTIME"          # 작동시간 > 기준값 +30%
    PERIODICITY_CHANGE = "PERIODICITY_CHANGE"      # 요일/시간대 패턴 편차
    PEAK_INCREASE = "PEAK_INCREASE"                # 최대 전력 > 기준값 +30%


@dataclass
class DisaggregationResult:
    """nilm-engine NILM-005 출력 스키마 (인터페이스 계약).

    confidence < 0.6 구간은 StatisticalAnomalyDetector에서 자동 제외.
    """

    appliance_type: str
    timestamp: datetime
    power_w: float
    confidence: float
    is_on: bool = False


@dataclass
class AnomalyEvent:
    """ANOM-000-3: 탐지된 이상 1건."""

    appliance_type: str
    anomaly_type: AnomalyType
    severity: Severity
    detected_at: datetime
    description: str
    recommended_action: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
