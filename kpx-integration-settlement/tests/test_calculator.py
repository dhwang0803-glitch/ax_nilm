"""settlement/calculator.py 단위 테스트."""
import pytest

from src.settlement.calculator import ApplianceSavings, calc_savings
from src.settlement.cbl import mid_6_of_10


# ── CBL ───────────────────────────────────────────────────────────────────────

def test_mid_6_of_10_normal():
    values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    # 하위2(1,2) + 상위2(9,10) 제외 → [3,4,5,6,7,8] 평균 = 5.5
    assert mid_6_of_10(values) == pytest.approx(5.5)


def test_mid_6_of_10_fallback_less_than_6():
    values = [1.0, 2.0, 3.0]
    assert mid_6_of_10(values) == pytest.approx(2.0)


def test_mid_6_of_10_empty():
    assert mid_6_of_10([]) == 0.0


# ── 공식식 ────────────────────────────────────────────────────────────────────

def test_calc_savings_positive():
    result = calc_savings(
        household_id="house_067",
        event_id="evt_001",
        cbl_kwh=3.0,
        actual_kwh=2.0,
        settlement_rate=1200.0,
        cbl_method="mid_6_10",
    )
    assert result.savings_kwh == pytest.approx(1.0)
    assert result.refund_krw == 1200


def test_calc_savings_no_refund_when_negative():
    result = calc_savings(
        household_id="house_067",
        event_id="evt_002",
        cbl_kwh=1.0,
        actual_kwh=2.0,
        settlement_rate=1200.0,
        cbl_method="mid_6_10",
    )
    assert result.savings_kwh == pytest.approx(-1.0)
    assert result.refund_krw == 0


# ── 보정식 ────────────────────────────────────────────────────────────────────

def test_untracked_savings_normal():
    appliances = [
        ApplianceSavings("에어컨", 1, 2.0, 1.5),   # savings=0.5
        ApplianceSavings("세탁기", 3, 0.5, 0.3),   # savings=0.2
    ]
    result = calc_savings(
        household_id="house_067",
        event_id="evt_003",
        cbl_kwh=3.0,
        actual_kwh=2.0,
        settlement_rate=1200.0,
        cbl_method="mid_6_10",
        appliance_savings=appliances,
    )
    # 전체 절감 1.0, 가전 합 0.7 → 기타 0.3
    assert result.untracked_savings_kwh == pytest.approx(0.3)
    assert not result.has_nilm_overestimate


def test_nilm_overestimate_flag():
    appliances = [
        ApplianceSavings("에어컨", 1, 2.0, 0.5),   # savings=1.5 (과대추정)
    ]
    result = calc_savings(
        household_id="house_067",
        event_id="evt_004",
        cbl_kwh=3.0,
        actual_kwh=2.0,
        settlement_rate=1200.0,
        cbl_method="mid_6_10",
        appliance_savings=appliances,
    )
    # 전체 절감 1.0, 가전 합 1.5 → 기타 -0.5 (과대추정)
    assert result.untracked_savings_kwh == pytest.approx(-0.5)
    assert result.has_nilm_overestimate


class ApplianceSavings:
    def __init__(self, appliance_code, channel_num, channel_cbl_kwh, channel_actual_kwh):
        self.appliance_code = appliance_code
        self.channel_num = channel_num
        self.channel_cbl_kwh = channel_cbl_kwh
        self.channel_actual_kwh = channel_actual_kwh

    @property
    def savings_kwh(self):
        return self.channel_cbl_kwh - self.channel_actual_kwh
