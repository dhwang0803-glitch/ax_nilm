"""ANOM-001 StatisticalAnomalyDetector 단위 테스트."""
from datetime import datetime, timedelta

import pytest

from anomaly_detection.src.detectors.statistical import StatisticalAnomalyDetector
from anomaly_detection.src.models.schemas import AnomalyType, DisaggregationResult, Severity


def _make_records(
    appliance: str,
    *,
    n_days: int,
    base_power: float,
    last_week_power: float,
    confidence: float = 0.9,
    interval_hours: int = 1,
) -> list[DisaggregationResult]:
    records = []
    now = datetime(2026, 5, 1)
    cutoff = now - timedelta(weeks=1)
    start = now - timedelta(days=n_days)
    t = start
    while t <= now:
        power = last_week_power if t >= cutoff else base_power
        records.append(
            DisaggregationResult(
                appliance_type=appliance,
                timestamp=t,
                power_w=power,
                confidence=confidence,
                is_on=power > 0,
            )
        )
        t += timedelta(hours=interval_hours)
    return records


class TestConsumptionIncrease:
    def test_detects_when_above_threshold(self):
        records = _make_records("에어컨", n_days=28, base_power=1000, last_week_power=1250)
        events = StatisticalAnomalyDetector(poc_mode=True).detect(records)
        assert any(e.anomaly_type == AnomalyType.CONSUMPTION_INCREASE for e in events)

    def test_no_event_below_threshold(self):
        records = _make_records("에어컨", n_days=28, base_power=1000, last_week_power=1100)
        events = StatisticalAnomalyDetector(poc_mode=True).detect(records)
        assert not any(e.anomaly_type == AnomalyType.CONSUMPTION_INCREASE for e in events)

    def test_high_severity_on_large_increase(self):
        records = _make_records("에어컨", n_days=28, base_power=1000, last_week_power=1500)
        events = [
            e for e in StatisticalAnomalyDetector(poc_mode=True).detect(records)
            if e.anomaly_type == AnomalyType.CONSUMPTION_INCREASE
        ]
        assert events and events[0].severity == Severity.HIGH

    def test_medium_severity_on_moderate_increase(self):
        records = _make_records("에어컨", n_days=28, base_power=1000, last_week_power=1250)
        events = [
            e for e in StatisticalAnomalyDetector(poc_mode=True).detect(records)
            if e.anomaly_type == AnomalyType.CONSUMPTION_INCREASE
        ]
        assert events and events[0].severity == Severity.MEDIUM


class TestConfidenceFilter:
    def test_low_confidence_excluded(self):
        records = _make_records("에어컨", n_days=28, base_power=1000, last_week_power=1500, confidence=0.5)
        events = StatisticalAnomalyDetector(poc_mode=True).detect(records)
        assert events == []

    def test_boundary_confidence_included(self):
        records = _make_records("에어컨", n_days=28, base_power=1000, last_week_power=1500, confidence=0.60)
        events = StatisticalAnomalyDetector(poc_mode=True).detect(records)
        assert len(events) > 0


class TestEdgeCases:
    def test_empty_input(self):
        assert StatisticalAnomalyDetector().detect([]) == []

    def test_insufficient_history_returns_empty(self):
        records = _make_records("에어컨", n_days=5, base_power=1000, last_week_power=1500)
        events = StatisticalAnomalyDetector(poc_mode=True).detect(records)
        # 5일 데이터는 베이스라인(3주) 확보 불가 → 빈 결과
        assert events == []
