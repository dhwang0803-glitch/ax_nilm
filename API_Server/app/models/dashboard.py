"""대시보드 응답 스키마 — Frontend `src/features/dashboard/types.ts` 와 매칭."""
from __future__ import annotations

from pydantic import BaseModel, Field


class DashboardKpis(BaseModel):
    monthly_usage_kwh: float = Field(alias="monthlyUsageKwh")
    monthly_delta_percent: float = Field(alias="monthlyDeltaPercent")
    estimated_cashback_krw: int = Field(alias="estimatedCashbackKrw")
    cashback_rate_krw_per_kwh: int = Field(alias="cashbackRateKrwPerKwh")
    estimated_bill_krw: int = Field(alias="estimatedBillKrw")

    model_config = {"populate_by_name": True}


class WeeklyDay(BaseModel):
    day: str
    prev_week: float = Field(alias="prevWeek")
    this_week: float = Field(alias="thisWeek")

    model_config = {"populate_by_name": True}


class WeeklyBlock(BaseModel):
    days: list[WeeklyDay]
    this_week_total: float = Field(alias="thisWeekTotal")
    prev_week_total: float = Field(alias="prevWeekTotal")
    avg_per_day: float | None = Field(default=None, alias="avgPerDay")

    model_config = {"populate_by_name": True}


class MonthEntry(BaseModel):
    month: int
    kwh: float


class MonthlyBlock(BaseModel):
    year: int
    months: list[MonthEntry]
    current_month: int = Field(alias="currentMonth")

    model_config = {"populate_by_name": True}


class ApplianceShare(BaseModel):
    name: str
    share_percent: float = Field(alias="sharePercent")

    model_config = {"populate_by_name": True}


class DashboardSummary(BaseModel):
    kpis: DashboardKpis
    weekly: WeeklyBlock
    monthly: MonthlyBlock
    appliance_breakdown: list[ApplianceShare] = Field(alias="applianceBreakdown")

    model_config = {"populate_by_name": True}
