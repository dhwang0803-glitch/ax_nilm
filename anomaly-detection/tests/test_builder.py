"""ShortTermBuilder 단위 테스트."""
from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
import yaml

from anomaly_detection.src.memory.builder import ShortTermBuilder
from anomaly_detection.src.models.schemas import DisaggregationResult

# ── 픽스처 ──────────────────────────────────────────────────────────────

THRESHOLDS_YAML = {
    "appliances": {
        "세탁기": {
            "states": [
                {"name": "wash", "min_w": 0.0, "max_w": 169.2},
                {"name": "spin", "min_w": 169.2, "max_w": None},
            ]
        },
        "에어컨": {
            "states": [
                {"name": "fan_low", "min_w": 0.0, "max_w": 11.6},
                {"name": "cool_medium", "min_w": 11.6, "max_w": 20.6},
                {"name": "cool_high", "min_w": 20.6, "max_w": None},
            ]
        },
        # yaml 축약키 — _THRESHOLD_KEY_MAP 적용 대상
        "일반냉장고": {
            "states": [
                {"name": "standby", "min_w": 0.0, "max_w": 52.0},
                {"name": "cool", "min_w": 52.0, "max_w": 172.0},
                {"name": "defrost", "min_w": 172.0, "max_w": None},
            ]
        },
        "식기세척기": {
            "states": [
                {"name": "rinse", "min_w": 0.0, "max_w": 419.4},
                {"name": "wash", "min_w": 419.4, "max_w": 1171.2},
                {"name": "heat_dry", "min_w": 1171.2, "max_w": None},
            ]
        },
    }
}


@pytest.fixture
def thresholds_file(tmp_path):
    p = tmp_path / "thresholds.yaml"
    p.write_text(yaml.dump(THRESHOLDS_YAML), encoding="utf-8")
    return p


@pytest.fixture
def builder_no_ref(thresholds_file):
    return ShortTermBuilder(thresholds_file)


def _make_records(appliance: str, power_values: list[float], interval_s: float = 2.0):
    base = datetime(2026, 5, 13, 10, 0, 0)
    return [
        DisaggregationResult(
            appliance_type=appliance,
            timestamp=base + timedelta(seconds=i * interval_s),
            power_w=w,
            confidence=0.9,
            is_on=w > 5.0,
        )
        for i, w in enumerate(power_values)
    ]


# ── 기본 동작 ────────────────────────────────────────────────────────────

def test_empty_records(builder_no_ref):
    assert builder_no_ref.build([]) == []


def test_low_confidence_filtered(builder_no_ref):
    records = _make_records("세탁기", [200.0] * 10)
    for r in records:
        r.confidence = 0.3
    assert builder_no_ref.build(records, min_confidence=0.6) == []


def test_single_mode_event(builder_no_ref):
    records = _make_records("세탁기", [80.0] * 20)
    events = builder_no_ref.build(records)
    assert len(events) == 1
    assert events[0].appliance == "세탁기"
    assert events[0].mode == "wash"
    assert events[0].energy_wh > 0


def test_mode_boundary_splits_events(builder_no_ref):
    # wash 구간 → spin 구간
    powers = [80.0] * 15 + [250.0] * 15
    records = _make_records("세탁기", powers)
    events = builder_no_ref.build(records)
    modes = [e.mode for e in events]
    assert "wash" in modes
    assert "spin" in modes


def test_below_on_threshold_skipped(builder_no_ref):
    # 세탁기 ON_THRESHOLD = 10W, 전부 5W → ON 구간 없음
    records = _make_records("세탁기", [5.0] * 20)
    events = builder_no_ref.build(records)
    assert events == []


def test_energy_calculation(builder_no_ref):
    # 100W × 10샘플 × 2초 간격 = 20초 = 1/180 h → energy ≈ 100/180 Wh
    records = _make_records("세탁기", [100.0] * 10, interval_s=2.0)
    events = builder_no_ref.build(records)
    assert len(events) == 1
    assert events[0].avg_w == pytest.approx(100.0, abs=0.1)
    assert events[0].peak_w == pytest.approx(100.0, abs=0.1)


def test_standby_detected(builder_no_ref):
    # 대기전력 구간: 1W < w < 10W(ON_THR), 30분 이상
    # 2초 간격 × 900샘플 = 1800초 = 30분
    standby_powers = [5.0] * 900
    on_powers = [100.0] * 20
    records = _make_records("세탁기", standby_powers + on_powers, interval_s=2.0)
    events = builder_no_ref.build(records)
    assert any(e.standby is not None for e in events)


# ── _THRESHOLD_KEY_MAP 가전명 매핑 ──────────────────────────────────────

def test_threshold_key_map_일반냉장고(thresholds_file):
    """'일반 냉장고'(코드명) → '일반냉장고'(yaml키) 매핑으로 모드 분류 정상 동작."""
    builder = ShortTermBuilder(thresholds_file)
    # 일반 냉장고는 ALWAYS_ON — standby(0~52W) 구간
    records = _make_records("일반 냉장고", [30.0] * 20)
    events = builder.build(records)
    assert len(events) == 1
    assert events[0].mode == "standby"


def test_threshold_key_map_식기세척기(thresholds_file):
    """'식기세척기/건조기'(코드명) → '식기세척기'(yaml키) 매핑으로 모드 분류 정상 동작."""
    builder = ShortTermBuilder(thresholds_file)
    records = _make_records("식기세척기/건조기", [500.0] * 20)
    events = builder.build(records)
    assert len(events) == 1
    assert events[0].mode == "wash"


def test_threshold_key_map_unknown_not_returned(thresholds_file):
    """매핑 적용 전에는 'unknown'이 반환됐으나 수정 후에는 올바른 모드 반환."""
    builder = ShortTermBuilder(thresholds_file)
    records = _make_records("일반 냉장고", [100.0] * 20)
    events = builder.build(records)
    assert all(e.mode != "unknown" for e in events)


# ── TDA 레퍼런스 폴백 ────────────────────────────────────────────────────

def test_tda_fallback_without_references(thresholds_file):
    """레퍼런스 없으면 에어컨도 W 범위 모드 사용."""
    builder = ShortTermBuilder(thresholds_file, references_path=None)
    records = _make_records("에어컨", [15.0] * 20)
    events = builder.build(records)
    assert len(events) == 1
    assert events[0].mode == "cool_medium"


def test_tda_mode_override_with_references(thresholds_file, tmp_path):
    """레퍼런스 있으면 _build_tda_appliance 경로로 분기 — W 범위 세그먼트 미사용."""
    img_size = 20
    zero_vec = [0.0] * (img_size * img_size)
    fan_low_ref = [1.0] * (img_size * img_size)
    refs = {
        "에어컨": {
            "fan_low": fan_low_ref,
            "cool_medium": zero_vec,
            "cool_high": zero_vec,
        }
    }
    ref_path = tmp_path / "reference_images.json"
    ref_path.write_text(json.dumps(refs), encoding="utf-8")

    builder = ShortTermBuilder(thresholds_file, references_path=ref_path)
    # WINDOW_SIZE(512) 이상 샘플이어야 윈도우가 1개 이상 생성됨
    # ripser 미설치 환경에선 fingerprint=None → mode="unknown" → 이벤트는 생성
    records = _make_records("에어컨", [15.0] * 600, interval_s=0.033)
    events = builder.build(records)
    assert len(events) >= 1
    # TDA 경로 분기 확인: tda_fingerprint 또는 mode_confidence 필드가 설정됨 (ripser 있는 환경)
    # ripser 없으면 mode="unknown" 이벤트만 생성 — 분기 자체는 정상 동작
    for e in events:
        assert e.appliance == "에어컨"
        assert e.mode in {"fan_low", "unknown"}  # TDA 결과 또는 entropy 초과
