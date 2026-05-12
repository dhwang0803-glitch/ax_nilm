"""공유 Pydantic 출력 스키마 — 멀티에이전트 + 인사이트 LLM."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AnomalyDiagnosis(BaseModel):
    event_id: str
    diagnosis: str = Field(max_length=100)
    action: str = Field(max_length=15)


class SavingsRec(BaseModel):
    title: str = Field(max_length=30)
    savings_kwh: float = Field(ge=0.1, le=10.0)
    savings_krw: int = Field(default=0, ge=0)


class InsightsLLMOutput(BaseModel):
    anomaly_diagnoses: list[AnomalyDiagnosis]
    recommendations: list[SavingsRec] = Field(min_length=3, max_length=5)
