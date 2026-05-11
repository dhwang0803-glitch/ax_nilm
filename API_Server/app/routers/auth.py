"""인증 엔드포인트.

데모 단계: 단일 데모 계정 (`settings.demo_user_email/password`) 만 통과.
JWT 는 httpOnly 쿠키로만 전달 — REQ-007 (localStorage 사용 금지).

OAuth: 시연용 stub. 실제 provider 콜백 핸드셰이크는 후속 마이그레이션.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import JSONResponse

from app.auth.jwt_utils import clear_session_cookie, encode_token, set_session_cookie
from app.config import Settings, get_settings
from app.deps import CurrentUser, get_current_user
from app.models.auth import AuthResponse, ErrorResponse, LoginRequest, SignupRequest, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


# 회원가입에서 거부할 데모용 "이미 가입된" 이메일 (Frontend MSW 호환)
_TAKEN_EMAIL = "taken@test.com"


def _issue_session(response: Response, settings: Settings, user: UserPublic) -> None:
    token = encode_token(
        settings,
        sub=user.id,
        claims={
            "email": user.email,
            "name": user.name,
            "household_id": settings.demo_household_id,
        },
    )
    set_session_cookie(response, settings, token)


@router.post(
    "/login",
    response_model=AuthResponse,
    responses={401: {"model": ErrorResponse}},
)
def login(
    body: LoginRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    if body.email != settings.demo_user_email or body.password != settings.demo_user_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 일치하지 않습니다"},
        )
    user = UserPublic(id="u1", email=settings.demo_user_email, name=settings.demo_user_name)
    _issue_session(response, settings, user)
    return AuthResponse(user=user)


@router.post(
    "/signup",
    response_model=AuthResponse,
    responses={422: {"model": ErrorResponse}},
)
def signup(
    body: SignupRequest,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    if body.email == _TAKEN_EMAIL:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "EMAIL_TAKEN", "message": "이미 가입된 이메일입니다"},
        )
    user = UserPublic(id="u-new", email=body.email, name=body.name)
    _issue_session(response, settings, user)
    return AuthResponse(user=user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(settings: Settings = Depends(get_settings)) -> Response:
    # 새 Response 를 반환하므로 cookie 도 그 위에 직접 설정 (DI 된 response 와 분리)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response, settings)
    return response


@router.post(
    "/oauth/{provider}",
    response_model=AuthResponse,
    responses={400: {"model": ErrorResponse}},
)
def oauth_login(
    provider: str,
    response: Response,
    settings: Settings = Depends(get_settings),
) -> AuthResponse:
    if provider not in {"kakao", "naver", "google"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "UNKNOWN_PROVIDER", "message": "지원하지 않는 OAuth provider"},
        )
    user = UserPublic(
        id=f"u-{provider}",
        email=f"{provider}@example.com",
        name=f"{provider} 사용자",
    )
    _issue_session(response, settings, user)
    return AuthResponse(user=user)


@router.get("/me", response_model=AuthResponse)
def me(current: CurrentUser = Depends(get_current_user)) -> AuthResponse:
    return AuthResponse(user=UserPublic(id=current.id, email=current.email, name=current.name))


__all__ = ["router"]
