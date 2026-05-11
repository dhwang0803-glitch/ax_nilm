"""사용량 분석 엔드포인트 — `GET /api/usage/analysis`."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, get_current_user
from app.models.usage import UsageAnalysis
from app.services.mock_data import build_usage_analysis

router = APIRouter(prefix="/api/usage", tags=["usage"])


@router.get("/analysis", response_model=UsageAnalysis, response_model_by_alias=True)
def get_analysis(_: CurrentUser = Depends(get_current_user)) -> UsageAnalysis:
    return build_usage_analysis()
