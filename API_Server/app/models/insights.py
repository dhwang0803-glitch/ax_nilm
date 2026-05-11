"""AI 진단 응답 스키마 — Frontend `src/features/insights/types.ts` 와 매칭."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["high", "medium", "low"]


class InsightsKpi(BaseModel):
    weekly_diagnosis_count: int = Field(alias="weeklyDiagnosisCount")
    weekly_diagnosis_delta: int = Field(alias="weeklyDiagnosisDelta")
    monthly_estimated_saving_krw: int = Field(alias="monthlyEstimatedSavingKrw")
    monthly_saving_delta: int = Field(alias="monthlySavingDelta")
    model_confidence: float = Field(alias="modelConfidence")

    # `model_` 은 pydantic 예약 prefix — 본 도메인은 ML 모델 신뢰도라 의도된 이름
    model_config = {"populate_by_name": True, "protected_namespaces": ()}


class AnomalyHighlight(BaseModel):
    id: str
    appliance: str
    severity: Severity
    headline: str
    recommendation: str
    detected_at: str = Field(alias="detectedAt")

    model_config = {"populate_by_name": True}


class Recommendation(BaseModel):
    id: str
    appliance: str
    action: str
    estimated_saving_krw: int = Field(alias="estimatedSavingKrw")
    confidence: float


class WeeklyTrendEntry(BaseModel):
    week_label: str = Field(alias="weekLabel")
    diagnosis_count: int = Field(alias="diagnosisCount")
    estimated_saving_krw: int = Field(alias="estimatedSavingKrw")

    model_config = {"populate_by_name": True}


class InsightsResponse(BaseModel):
    generated_at: str = Field(alias="generatedAt")
    model_version: str = Field(alias="modelVersion")
    sample_households: int = Field(alias="sampleHouseholds")
    kpi: InsightsKpi
    anomaly_highlights: list[AnomalyHighlight] = Field(alias="anomalyHighlights")
    recommendations: list[Recommendation]
    weekly_trend: list[WeeklyTrendEntry] = Field(alias="weeklyTrend")

    model_config = {"populate_by_name": True, "protected_namespaces": ()}
