"""에너지캐시백 산정 — 기준선 대비 절감률 → 단가 → 캐시백 금액.

공식식:   절감량(kWh) = 기준선 - 실측 사용량
보정식:   유효 절감량 = 기준선 × min(절감률, 30%)  ← 30% 상한 적용
내부식:   가전별 절감 기여 = 가전별 기준선 - 가전별 실측 (NILM 분해 결과)

캐시백 단가 구조 (KEPCO 에너지마켓플레이스 기준, 변경 가능):
  절감률 3% 미만      → 미지급
  3% 이상 ~ 5% 미만  → 30원/kWh
  5% 이상 ~ 10% 미만 → 50원/kWh
  10% 이상 ~ 20% 미만→ 70원/kWh
  20% 이상 (30% 캡)  → 100원/kWh
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


# 절감률 구간별 단가 (오름차순 — (최소 절감률, 단가)) — KEPCO 2024년 1월분 기준
_CASHBACK_TIERS: list[tuple[float, float]] = [
    (0.20, 100.0),
    (0.10,  70.0),
    (0.05,  50.0),
    (0.03,  30.0),
]
_MIN_SAVINGS_RATE = 0.03   # 3% 미만 미지급
_MAX_SAVINGS_RATE = 0.30   # 30% 초과분 미인정


def get_cashback_unit_rate(savings_rate: float) -> float:
    """절감률 → 단가(원/kWh). 3% 미만이면 0."""
    if savings_rate < _MIN_SAVINGS_RATE:
        return 0.0
    for threshold, rate in _CASHBACK_TIERS:
        if savings_rate >= threshold:
            return rate
    return 0.0


@dataclass
class ApplianceSavings:
    channel_num: int
    appliance_code: str
    channel_baseline_kwh: float
    channel_actual_kwh: float

    @property
    def savings_kwh(self) -> float:
        return self.channel_baseline_kwh - self.channel_actual_kwh


@dataclass
class CashbackResult:
    household_id: str
    billing_month: date
    baseline_kwh: float        # 기준선 (2개년 동월 평균)
    actual_kwh: float          # 실측 사용량
    savings_kwh: float         # 절감량 (음수 = 사용 증가)
    savings_rate: float        # 절감률
    effective_savings_kwh: float  # 유효 절감량 (30% 상한 적용)
    cashback_rate: float       # 적용 단가 (원/kWh)
    cashback_krw: int          # 캐시백 금액
    baseline_method: str       # "2year_avg" | "proxy_cluster"
    appliance_savings: list[ApplianceSavings] = field(default_factory=list)

    @property
    def appliance_total_kwh(self) -> float:
        """내부식: 가전별 절감량 합산."""
        return sum(a.savings_kwh for a in self.appliance_savings)

    @property
    def untracked_savings_kwh(self) -> float:
        """보정식: 미분류 절감량. 음수 = NILM 과대추정."""
        return self.savings_kwh - self.appliance_total_kwh

    @property
    def has_nilm_overestimate(self) -> bool:
        return self.untracked_savings_kwh < 0

    def appliance_cashback_contributions(self) -> list[tuple[str, float, int]]:
        """가전별 캐시백 기여분 목록 (절감량 내림차순).

        단가는 가구 전체 절감률로 결정되므로 모든 가전에 동일 단가 적용.

        Returns:
            [(appliance_code, savings_kwh, cashback_krw), ...]
        """
        result = []
        for a in self.appliance_savings:
            if a.savings_kwh > 0:
                contrib_krw = int(a.savings_kwh * self.cashback_rate)
                result.append((a.appliance_code, round(a.savings_kwh, 3), contrib_krw))
        return sorted(result, key=lambda x: x[2], reverse=True)


def calc_cashback(
    household_id: str,
    billing_month: date,
    baseline_kwh: float,
    actual_kwh: float,
    baseline_method: str,
    appliance_savings: list[ApplianceSavings] | None = None,
) -> CashbackResult:
    """캐시백 산정."""
    savings_kwh = baseline_kwh - actual_kwh
    savings_rate = savings_kwh / baseline_kwh if baseline_kwh > 0 else 0.0

    capped_rate = min(max(savings_rate, 0.0), _MAX_SAVINGS_RATE)
    effective_savings_kwh = baseline_kwh * capped_rate
    cashback_rate = get_cashback_unit_rate(savings_rate)
    cashback_krw = int(effective_savings_kwh * cashback_rate)

    return CashbackResult(
        household_id=household_id,
        billing_month=billing_month,
        baseline_kwh=baseline_kwh,
        actual_kwh=actual_kwh,
        savings_kwh=savings_kwh,
        savings_rate=savings_rate,
        effective_savings_kwh=effective_savings_kwh,
        cashback_rate=cashback_rate,
        cashback_krw=cashback_krw,
        baseline_method=baseline_method,
        appliance_savings=appliance_savings or [],
    )
