"""AnomalyDetectionService: 이상 탐지 파이프라인 오케스트레이터."""
from __future__ import annotations

import yaml

from anomaly_detection.src.detectors.pattern import PatternAnomalyDetector
from anomaly_detection.src.detectors.statistical import StatisticalAnomalyDetector
from anomaly_detection.src.models.schemas import (
    AnomalyEvent,
    DisaggregationResult,
    _SEVERITY_ORDER,
)


class AnomalyDetectionService:
    """이상 탐지 파이프라인 public API.

    사용법:
        svc = AnomalyDetectionService.from_yaml("config/anomaly.yaml")
        svc.fit_pattern_detector(baseline_records)
        events = svc.run(current_records)
    """

    def __init__(self, config: dict) -> None:
        thr = config.get("thresholds", {})
        poc = config.get("poc_mode", {})
        if_cfg = config.get("pattern_detector", {}).get("isolation_forest", {})

        self.statistical = StatisticalAnomalyDetector(
            consumption_threshold=thr.get("consumption_increase_pct", 0.20),
            consumption_high=thr.get("consumption_high_pct", 0.35),
            runtime_threshold=thr.get("runtime_increase_pct", 0.30),
            runtime_high=thr.get("runtime_high_pct", 0.50),
            peak_threshold=thr.get("peak_increase_pct", 0.30),
            peak_high=thr.get("peak_high_pct", 0.50),
            min_confidence=thr.get("min_confidence", 0.60),
            poc_mode=poc.get("enabled", True),
        )
        self.pattern = PatternAnomalyDetector(
            contamination=if_cfg.get("contamination", 0.05),
            n_estimators=if_cfg.get("n_estimators", 100),
            random_state=if_cfg.get("random_state", 42),
        )

    @classmethod
    def from_yaml(cls, config_path: str) -> AnomalyDetectionService:
        with open(config_path) as f:
            return cls(yaml.safe_load(f))

    def fit_pattern_detector(self, baseline_records: list[DisaggregationResult]) -> None:
        """패턴 탐지기를 정상 기간 데이터로 학습."""
        self.pattern.fit(baseline_records)

    def run(self, records: list[DisaggregationResult]) -> list[AnomalyEvent]:
        """이상 탐지 실행 → AnomalyEvent 리스트 반환."""
        events: list[AnomalyEvent] = []
        events.extend(self.statistical.detect(records))
        events.extend(self.pattern.detect(records))
        return _deduplicate(events)


def _deduplicate(events: list[AnomalyEvent]) -> list[AnomalyEvent]:
    """동일 (기기, 유형) 중복 이벤트 → 가장 높은 심각도 유지."""
    seen: dict[tuple, AnomalyEvent] = {}
    for event in events:
        key = (event.appliance_type, event.anomaly_type)
        if key not in seen or _SEVERITY_ORDER[event.severity] < _SEVERITY_ORDER[seen[key].severity]:
            seen[key] = event
    return list(seen.values())
