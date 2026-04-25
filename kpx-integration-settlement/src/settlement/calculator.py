"""DR 절감량·환급금 계산 — 공식식 / 내부식 / 정합성 보정식.

공식식:   가구 전체 절감량  = 가구 단위 CBL - 이벤트 구간 실제 총 사용량
내부식:   가전별 절감량(추정) = 가전별 기준 사용량 - 가전별 NILM 추정 사용량
보정식:   기타/미분류 절감량 = 가구 전체 절감량 - Σ(가전별 절감량)
           (음수이면 NILM 과대추정 → UI에 추정 오차 표시)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class AggregatorRepository(Protocol):
    async def get_settlement_rate(self, aggregator_id: str) -> float:
        """aggregators 테이블에서 사업자별 정산 단가(원/kWh) 조회."""
        ...


@dataclass
class ApplianceSavings:
    channel_num: int
    appliance_code: str
    channel_cbl_kwh: float
    channel_actual_kwh: float

    @property
    def savings_kwh(self) -> float:
        return self.channel_cbl_kwh - self.channel_actual_kwh


@dataclass
class DRSavingsResult:
    household_id: str
    event_id: str
    cbl_kwh: float           # 공식식 CBL
    actual_kwh: float        # 공식식 실측
    savings_kwh: float       # 공식식 절감량
    refund_krw: int          # 환급금
    settlement_rate: float   # 원/kWh
    cbl_method: str          # "mid_6_10" | "proxy_cluster"
    appliance_savings: list[ApplianceSavings] = field(default_factory=list)

    @property
    def appliance_total_kwh(self) -> float:
        """내부식 Σ(가전별 절감량)."""
        return sum(a.savings_kwh for a in self.appliance_savings)

    @property
    def untracked_savings_kwh(self) -> float:
        """보정식: 기타/미분류 절감량. 음수 = NILM 과대추정."""
        return self.savings_kwh - self.appliance_total_kwh

    @property
    def has_nilm_overestimate(self) -> bool:
        return self.untracked_savings_kwh < 0


def calc_savings(
    household_id: str,
    event_id: str,
    cbl_kwh: float,
    actual_kwh: float,
    settlement_rate: float,
    cbl_method: str,
    appliance_savings: list[ApplianceSavings] | None = None,
) -> DRSavingsResult:
    """공식식 기반 절감량 및 환급금 계산."""
    savings_kwh = cbl_kwh - actual_kwh
    refund_krw = int(max(0.0, savings_kwh) * settlement_rate)

    return DRSavingsResult(
        household_id=household_id,
        event_id=event_id,
        cbl_kwh=cbl_kwh,
        actual_kwh=actual_kwh,
        savings_kwh=savings_kwh,
        refund_krw=refund_krw,
        settlement_rate=settlement_rate,
        cbl_method=cbl_method,
        appliance_savings=appliance_savings or [],
    )
