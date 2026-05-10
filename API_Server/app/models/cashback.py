"""캐시백 응답 스키마 — Frontend `src/features/cashback/types.ts` 와 매칭."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.models.dashboard import MonthlyBlock, WeeklyBlock


class CashbackGoal(BaseModel):
    month: int
    target_savings_percent: float = Field(alias="targetSavingsPercent")
    target_cashback_krw: int = Field(alias="targetCashbackKrw")
    days_remaining: int = Field(alias="daysRemaining")
    current_savings_percent: float = Field(alias="currentSavingsPercent")
    expected_savings_percent: float = Field(alias="expectedSavingsPercent")
    progress_percent: float = Field(alias="progressPercent")
    expected_progress_percent: float = Field(alias="expectedProgressPercent")

    model_config = {"populate_by_name": True}


class CashbackMission(BaseModel):
    id: str
    title: str
    expected_savings_kwh: float = Field(alias="expectedSavingsKwh")
    status: Literal["pending", "done"]

    model_config = {"populate_by_name": True}


class CashbackTracker(BaseModel):
    goal: CashbackGoal
    weekly: WeeklyBlock
    monthly: MonthlyBlock
    missions: list[CashbackMission]
