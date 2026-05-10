"""AI 진단 엔드포인트 — `GET /api/insights/summary`."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, get_current_user
from app.models.insights import InsightsResponse
from app.services.mock_data import build_insights

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/summary", response_model=InsightsResponse, response_model_by_alias=True)
def get_summary(_: CurrentUser = Depends(get_current_user)) -> InsightsResponse:
    return build_insights()
