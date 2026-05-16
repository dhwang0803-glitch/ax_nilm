"""compressor EWM 갱신 단위 테스트."""
from __future__ import annotations

from datetime import datetime

import pytest

from anomaly_detection.src.memory.compressor import compress
from anomaly_detection.src.memory.schemas import ApplianceBaseline, ModeBaseline, ShortTermEvent


def _event(appliance, mode, energy_wh, duration_min, peak_w=100.0):
    return ShortTermEvent(
        appliance=appliance,
        mode=mode,
        started_at=datetime(2026, 5, 13, 10, 0),
        duration_min=duration_min,
        energy_wh=energy_wh,
        avg_w=energy_wh / (duration_min / 60),
        peak_w=peak_w,
        tda_fingerprint=None,
        standby=None,
    )


def test_compress_empty_events():
    result = compress([], {})
    assert result == {}


def test_compress_new_appliance():
    events = [_event("에어컨", "fan_low", 500.0, 60.0)]
    result = compress(events, {})
    assert "에어컨" in result
    baseline = result["에어컨"]
    assert "fan_low" in baseline.modes
    assert baseline.modes["fan_low"].avg_energy_wh == pytest.approx(500.0)
    assert baseline.modes["fan_low"].avg_duration_min == pytest.approx(60.0)
    assert baseline.modes["fan_low"].sample_count == 1


def test_compress_ewm_update():
    """EWM: alpha=0.2 → new = 0.2*new + 0.8*old."""
    existing = {
        "에어컨": ApplianceBaseline(
            appliance="에어컨",
            modes={"fan_low": ModeBaseline(avg_energy_wh=1000.0, avg_duration_min=90.0, tda_reference=None, sample_count=5)},
        )
    }
    events = [_event("에어컨", "fan_low", 500.0, 60.0)]
    result = compress(events, existing)

    updated = result["에어컨"].modes["fan_low"]
    expected_energy = 0.2 * 500.0 + 0.8 * 1000.0
    expected_duration = 0.2 * 60.0 + 0.8 * 90.0
    assert updated.avg_energy_wh == pytest.approx(expected_energy, rel=1e-3)
    assert updated.avg_duration_min == pytest.approx(expected_duration, rel=1e-3)
    assert updated.sample_count == 6


def test_compress_multiple_events_same_mode():
    """같은 모드 이벤트 여러 개 → 순차 EWM 적용.

    1번째: seed → 200, 2번째: 0.2*400 + 0.8*200 = 240
    """
    events = [
        _event("세탁기", "wash", 200.0, 30.0),
        _event("세탁기", "wash", 400.0, 50.0),
    ]
    result = compress(events, {})
    mode = result["세탁기"].modes["wash"]
    expected_energy = 0.2 * 400.0 + 0.8 * 200.0   # = 240
    expected_duration = 0.2 * 50.0 + 0.8 * 30.0   # = 34
    assert mode.avg_energy_wh == pytest.approx(expected_energy, rel=1e-3)
    assert mode.avg_duration_min == pytest.approx(expected_duration, rel=1e-3)


def test_compress_multiple_modes():
    events = [
        _event("세탁기", "wash", 200.0, 30.0),
        _event("세탁기", "spin", 600.0, 10.0),
    ]
    result = compress(events, {})
    assert "wash" in result["세탁기"].modes
    assert "spin" in result["세탁기"].modes


def test_compress_preserves_existing_unobserved_mode():
    """당일 이벤트 없는 모드는 장기 메모리 그대로 유지."""
    existing = {
        "세탁기": ApplianceBaseline(
            appliance="세탁기",
            modes={
                "wash": ModeBaseline(avg_energy_wh=200.0, avg_duration_min=30.0, tda_reference=None, sample_count=3),
                "spin": ModeBaseline(avg_energy_wh=600.0, avg_duration_min=10.0, tda_reference=None, sample_count=3),
            },
        )
    }
    events = [_event("세탁기", "wash", 250.0, 35.0)]
    result = compress(events, existing)
    # spin은 오늘 이벤트 없음 → 기존값 유지
    assert result["세탁기"].modes["spin"].avg_energy_wh == pytest.approx(600.0)
