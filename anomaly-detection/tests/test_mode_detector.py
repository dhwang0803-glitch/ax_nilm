"""mode_detector 단위 테스트."""
from __future__ import annotations

import numpy as np
import pytest

from anomaly_detection.src.tda.mode_detector import classify_mode, compute_fingerprint


def _sine_signal(n=200, freq=0.1):
    return np.sin(2 * np.pi * freq * np.arange(n)).astype(np.float32)


# ── compute_fingerprint ───────────────────────────────────────────────────

def test_fingerprint_short_signal_returns_none():
    assert compute_fingerprint(np.zeros(10), max_w=1.0) is None


def test_fingerprint_flat_signal_returns_none():
    assert compute_fingerprint(np.ones(200), max_w=1.0) is None


def test_fingerprint_returns_correct_length():
    sig = _sine_signal(300)
    fp = compute_fingerprint(sig, max_w=1.0)
    if fp is not None:  # ripser 미설치 환경에선 None
        assert len(fp) == 20 * 20


def test_fingerprint_reproducible():
    sig = _sine_signal(300)
    fp1 = compute_fingerprint(sig, max_w=1.0)
    fp2 = compute_fingerprint(sig, max_w=1.0)
    if fp1 is not None and fp2 is not None:
        assert fp1 == fp2


# ── classify_mode ─────────────────────────────────────────────────────────

def test_classify_mode_no_references():
    assert classify_mode("에어컨", [0.1] * 400, {}) is None


def test_classify_mode_none_fingerprint():
    refs = {"에어컨": {"fan_low": [1.0] * 400}}
    assert classify_mode("에어컨", None, refs) is None


def test_classify_mode_unknown_appliance():
    refs = {"에어컨": {"fan_low": [1.0] * 400}}
    assert classify_mode("냉장고", [0.1] * 400, refs) is None


def test_classify_mode_skips_zero_references():
    """영벡터 레퍼런스는 비교 대상에서 제외."""
    refs = {
        "에어컨": {
            "fan_low": [0.0] * 400,   # 영벡터 — 스킵
            "cool_medium": [1.0] * 400,
        }
    }
    fp = [0.9] * 400
    result = classify_mode("에어컨", fp, refs)
    assert result == "cool_medium"


def test_classify_mode_nearest_reference():
    """L2 거리 기준 가장 가까운 상태 반환.

    영벡터는 스킵되므로 두 레퍼런스 모두 non-zero로 설정.
    """
    fan_ref  = [1.0] * 400          # fan_low 레퍼런스: 전부 1
    cool_ref = [0.1] * 400          # cool_medium 레퍼런스: 전부 0.1

    refs = {"에어컨": {"fan_low": fan_ref, "cool_medium": cool_ref}}

    fp_fan = [0.95] * 400           # fan_ref에 가까움
    assert classify_mode("에어컨", fp_fan, refs) == "fan_low"

    fp_cool = [0.15] * 400          # cool_ref에 가까움
    assert classify_mode("에어컨", fp_cool, refs) == "cool_medium"
