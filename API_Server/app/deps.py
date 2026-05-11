"""FastAPI 의존성 주입 — 인증 / 세션 / 설정.

데모 단계: 데모 계정 1개 (`settings.demo_user_email`) 만 인증 통과.
실 서비스 전환 시: User 테이블 + bcrypt password 검증으로 교체.
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Cookie, Depends, HTTPException, status

from app.auth.jwt_utils import decode_token
from app.config import Settings, get_settings


@dataclass(frozen=True)
class CurrentUser:
    id: str
    email: str
    name: str
    household_id: str


def get_current_user(
    settings: Settings = Depends(get_settings),
    session_cookie: str | None = Cookie(default=None, alias="ax_nilm_session"),
) -> CurrentUser:
    """쿠키 검증. 미인증/만료 시 401."""
    if not session_cookie:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_token(settings, session_cookie)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session")

    return CurrentUser(
        id=payload["sub"],
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        household_id=payload.get("household_id", settings.demo_household_id),
    )


def get_optional_user(
    settings: Settings = Depends(get_settings),
    session_cookie: str | None = Cookie(default=None, alias="ax_nilm_session"),
) -> CurrentUser | None:
    """비인증도 허용 (랜딩 등 public 라우트). 쿠키가 있으면 검증."""
    if not session_cookie:
        return None
    payload = decode_token(settings, session_cookie)
    if not payload or "sub" not in payload:
        return None
    return CurrentUser(
        id=payload["sub"],
        email=payload.get("email", ""),
        name=payload.get("name", ""),
        household_id=payload.get("household_id", settings.demo_household_id),
    )
