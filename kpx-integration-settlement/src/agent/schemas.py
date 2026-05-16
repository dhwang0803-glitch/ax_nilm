"""공유 Pydantic 출력 스키마 — 멀티에이전트 + 인사이트 LLM."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# category 의미
#   "이상"     : 기기 결함·성능 저하 의심 — 점검·교체 권고
#   "사용변화" : 사용 빈도/시간대 급변 — 정상 행동 가능성 높음, 정보성 안내
#   "정상"     : baseline 범위 내 — 기록만, 사용자 노출 최소
DiagnosisCategory = Literal["이상", "사용변화", "정상"]


class AnomalyDiagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    category: DiagnosisCategory = "이상"
    diagnosis: str = Field(max_length=140)
    cause: str = Field(default="", max_length=160)
    action: str = Field(default="", max_length=50)
    expected_savings_krw_per_month: int = Field(default=0, ge=0)


class SavingsRec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(max_length=30)
    savings_kwh: float = Field(ge=0.01, le=200.0)
    savings_krw: int = Field(default=0, ge=0)
    description: str = Field(default="", max_length=300)


class InsightsLLMOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anomaly_diagnoses: list[AnomalyDiagnosis]
    recommendations: list[SavingsRec] = Field(min_length=3, max_length=5)
