"""ANOM-002 PatternAnomalyDetector 단위 테스트."""
from datetime import datetime, timedelta

import numpy as np
import pytest

from anomaly_detection.src.detectors.pattern import PatternAnomalyDetector
from anomaly_detection.src.models.schemas import AnomalyType, DisaggregationResult


def _normal_records(appliance: str, n_days: int = 30) -> list[DisaggregationResult]:
    rng = np.random.default_rng(0)
    records = []
    t = datetime(2026, 4, 1)
    for _ in range(n_days * 24):
        power = 1000.0 if 8 <= t.hour <= 22 else 100.0
        records.append(
            DisaggregationResult(
                appliance_type=appliance,
                timestamp=t,
                power_w=power + rng.normal(0, 10),
                confidence=0.9,
                is_on=power > 500,
            )
        )
        t += timedelta(hours=1)
    return records


def _anomalous_records(appliance: str, n_days: int = 7) -> list[DisaggregationResult]:
    rng = np.random.default_rng(1)
    records = []
    t = datetime(2026, 5, 1)
    for _ in range(n_days * 24):
        records.append(
            DisaggregationResult(
                appliance_type=appliance,
                timestamp=t,
                power_w=3000.0 + rng.normal(0, 50),
                confidence=0.9,
                is_on=True,
            )
        )
        t += timedelta(hours=1)
    return records


class TestPatternAnomalyDetector:
    def test_detects_anomaly_after_fit(self):
        detector = PatternAnomalyDetector(contamination=0.1, random_state=42)
        detector.fit(_normal_records("냉장고"))
        events = detector.detect(_anomalous_records("냉장고"))
        assert len(events) > 0

    def test_no_model_returns_empty_isolation_events(self):
        detector = PatternAnomalyDetector()
        events = detector.detect(_normal_records("냉장고", n_days=7))
        # Isolation Forest 이벤트 없음 (미학습); 주기성 이벤트도 베이스라인 없어 없음
        assert events == []

    def test_anomaly_event_has_correct_type(self):
        detector = PatternAnomalyDetector(contamination=0.3, random_state=42)
        detector.fit(_normal_records("냉장고"))
        events = detector.detect(_anomalous_records("냉장고"))
        assert all(e.anomaly_type == AnomalyType.PERIODICITY_CHANGE for e in events)

    def test_fit_skips_insufficient_data(self):
        detector = PatternAnomalyDetector()
        tiny = _normal_records("냉장고", n_days=1)[:5]
        detector.fit(tiny)
        assert "냉장고" not in detector._models
