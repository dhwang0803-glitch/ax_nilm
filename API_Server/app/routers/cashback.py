"""캐시백 엔드포인트 — `GET /api/cashback/tracker`."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, get_current_user
from app.models.cashback import CashbackTracker
from app.services.mock_data import build_cashback_tracker

router = APIRouter(prefix="/api/cashback", tags=["cashback"])


@router.get("/tracker", response_model=CashbackTracker, response_model_by_alias=True)
def get_tracker(_: CurrentUser = Depends(get_current_user)) -> CashbackTracker:
    return build_cashback_tracker()
