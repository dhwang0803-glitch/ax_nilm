"""사용량 분석 응답 스키마 — Frontend `src/features/usage/types.ts` 와 매칭."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.models.dashboard import MonthlyBlock, WeeklyBlock


class HourlyEntry(BaseModel):
    hour: int
    average: float
    today: float


class HourlyBlock(BaseModel):
    hours: list[HourlyEntry]


class UsageApplianceItem(BaseModel):
    name: str
    kwh: float
    share_percent: float = Field(alias="sharePercent")
    week_over_week_percent: float = Field(alias="weekOverWeekPercent")

    model_config = {"populate_by_name": True}


class UsageAnalysis(BaseModel):
    weekly: WeeklyBlock
    hourly: HourlyBlock
    appliance_breakdown: list[UsageApplianceItem] = Field(alias="applianceBreakdown")
    monthly: MonthlyBlock

    model_config = {"populate_by_name": True}
