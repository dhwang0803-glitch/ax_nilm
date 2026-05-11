"""대시보드 엔드포인트 — `GET /api/dashboard/summary`."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, get_current_user
from app.models.dashboard import DashboardSummary
from app.services.mock_data import build_dashboard_summary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary, response_model_by_alias=True)
def get_summary(_: CurrentUser = Depends(get_current_user)) -> DashboardSummary:
    return build_dashboard_summary()
