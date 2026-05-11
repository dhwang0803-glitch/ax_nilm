"""settlement/calculator.py 단위 테스트 — 에너지캐시백 기준."""
from datetime import date

import pytest

from src.settlement.calculator import (
    ApplianceSavings,
    calc_cashback,
    get_cashback_unit_rate,
)


# ── 단가 구간 ─────────────────────────────────────────────────────────────────

def test_unit_rate_below_min():
    assert get_cashback_unit_rate(0.02) == 0.0


def test_unit_rate_at_min_threshold():
    assert get_cashback_unit_rate(0.03) == 30.0


def test_unit_rate_tier_50():
    assert get_cashback_unit_rate(0.07) == 50.0


def test_unit_rate_tier_70():
    assert get_cashback_unit_rate(0.15) == 70.0


def test_unit_rate_tier_100():
    assert get_cashback_unit_rate(0.25) == 100.0


# ── 캐시백 산정 ───────────────────────────────────────────────────────────────

_MONTH = date(2025, 7, 1)


def test_cashback_no_savings():
    """사용량 증가 시 캐시백 0."""
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=110.0,
        baseline_method="2year_avg",
    )
    assert result.savings_kwh == pytest.approx(-10.0)
    assert result.cashback_krw == 0


def test_cashback_below_3pct():
    """절감률 3% 미만 — 미지급."""
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=98.0,   # 2% 절감
        baseline_method="2year_avg",
    )
    assert result.savings_rate == pytest.approx(0.02)
    assert result.cashback_krw == 0


def test_cashback_3pct_tier():
    """절감률 3% → 30원/kWh."""
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=97.0,   # 3% 절감 → 3kWh × 30원 = 90원
        baseline_method="2year_avg",
    )
    assert result.cashback_rate == 30.0
    assert result.cashback_krw == 90


def test_cashback_5pct_tier():
    """절감률 7% → 50원/kWh."""
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=93.0,   # 7% 절감 → 7kWh × 50원 = 350원
        baseline_method="2year_avg",
    )
    assert result.cashback_rate == 50.0
    assert result.cashback_krw == 350


def test_cashback_30pct_cap():
    """절감률 40% → 30% 상한 적용."""
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=60.0,   # 40% 절감 → 캡 30% 적용 → 30kWh × 100원 = 3000원
        baseline_method="2year_avg",
    )
    assert result.savings_rate == pytest.approx(0.40)
    assert result.effective_savings_kwh == pytest.approx(30.0)
    assert result.cashback_rate == 100.0
    assert result.cashback_krw == 3000


def test_cashback_proxy_cluster_method():
    result = calc_cashback(
        household_id="house_new",
        billing_month=_MONTH,
        baseline_kwh=200.0,
        actual_kwh=180.0,  # 10% 절감 → 20kWh × 70원 = 1400원
        baseline_method="proxy_cluster",
    )
    assert result.baseline_method == "proxy_cluster"
    assert result.cashback_rate == 70.0
    assert result.cashback_krw == 1400


# ── 보정식 ────────────────────────────────────────────────────────────────────

def test_untracked_savings_normal():
    """전체 절감 > 가전 합 → 기타 절감 양수."""
    appliances = [
        ApplianceSavings(
            channel_num=2, appliance_code="에어컨",
            channel_baseline_kwh=2.0, channel_actual_kwh=1.5,   # 0.5kWh 절감
        ),
        ApplianceSavings(
            channel_num=4, appliance_code="세탁기",
            channel_baseline_kwh=0.5, channel_actual_kwh=0.3,   # 0.2kWh 절감
        ),
    ]
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=90.0,   # 전체 10kWh 절감
        baseline_method="2year_avg",
        appliance_savings=appliances,
    )
    # 전체 10.0, 가전 합 0.7 → 기타 9.3
    assert result.untracked_savings_kwh == pytest.approx(9.3)
    assert not result.has_nilm_overestimate


def test_nilm_overestimate_flag():
    """가전 합 > 전체 절감 → NILM 과대추정 플래그."""
    appliances = [
        ApplianceSavings(
            channel_num=2, appliance_code="에어컨",
            channel_baseline_kwh=5.0, channel_actual_kwh=1.0,   # 4.0kWh 절감 (과대추정)
        ),
    ]
    result = calc_cashback(
        household_id="house_067",
        billing_month=_MONTH,
        baseline_kwh=100.0,
        actual_kwh=97.0,   # 전체 3kWh 절감
        baseline_method="2year_avg",
        appliance_savings=appliances,
    )
    # 전체 3.0, 가전 합 4.0 → -1.0 (과대추정)
    assert result.untracked_savings_kwh == pytest.approx(-1.0)
    assert result.has_nilm_overestimate
