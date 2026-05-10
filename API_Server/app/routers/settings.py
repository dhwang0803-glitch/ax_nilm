"""설정 엔드포인트 — 5개 GET 라우트.

`/api/settings/account`, `/notifications`, `/security`,
`/anomaly-events`, `/email`.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.deps import CurrentUser, get_current_user
from app.models.settings import (
    AccountResponse,
    AnomalyEventsResponse,
    EmailResponse,
    NotificationsResponse,
    SecurityResponse,
)
from app.services.mock_data import (
    build_account,
    build_anomaly_events,
    build_email,
    build_notifications,
    build_security,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/account", response_model=AccountResponse, response_model_by_alias=True)
def get_account(current: CurrentUser = Depends(get_current_user)) -> AccountResponse:
    return build_account(email=current.email, name=current.name)


@router.get("/notifications", response_model=NotificationsResponse, response_model_by_alias=True)
def get_notifications(_: CurrentUser = Depends(get_current_user)) -> NotificationsResponse:
    return build_notifications()


@router.get("/security", response_model=SecurityResponse, response_model_by_alias=True)
def get_security(_: CurrentUser = Depends(get_current_user)) -> SecurityResponse:
    return build_security()


@router.get("/anomaly-events", response_model=AnomalyEventsResponse, response_model_by_alias=True)
def get_anomaly_events(_: CurrentUser = Depends(get_current_user)) -> AnomalyEventsResponse:
    return build_anomaly_events()


@router.get("/email", response_model=EmailResponse, response_model_by_alias=True)
def get_email(current: CurrentUser = Depends(get_current_user)) -> EmailResponse:
    return build_email(primary_email=current.email)
