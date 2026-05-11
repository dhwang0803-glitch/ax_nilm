from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_VALID_EMAIL = "test@example.com"
_VALID_PASSWORD = "nilm-mock-2026!"
_TAKEN_EMAIL = "taken@test.com"


class LoginPayload(BaseModel):
    email: str
    password: str


class SignupPayload(BaseModel):
    email: str
    password: str
    name: str
    agreeTerms: bool
    kepcoCustomerNumber: str | None = None


class UserOut(BaseModel):
    id: str
    email: str
    name: str


class AuthResponse(BaseModel):
    user: UserOut


@router.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginPayload):
    if payload.email == _VALID_EMAIL and payload.password == _VALID_PASSWORD:
        return {"user": {"id": "u1", "email": _VALID_EMAIL, "name": "테스터"}}
    raise HTTPException(
        status_code=401,
        detail={"code": "INVALID_CREDENTIALS", "message": "이메일 또는 비밀번호가 일치하지 않습니다"},
    )


@router.post("/auth/signup", response_model=AuthResponse)
def signup(payload: SignupPayload):
    if payload.email == _TAKEN_EMAIL:
        raise HTTPException(
            status_code=422,
            detail={"code": "EMAIL_TAKEN", "message": "이미 가입된 이메일입니다"},
        )
    return {"user": {"id": "u-new", "email": payload.email, "name": payload.name}}


@router.post("/auth/logout", status_code=204)
def logout():
    return None


@router.post("/auth/oauth/{provider}", response_model=AuthResponse)
def oauth_login(provider: str):
    if provider not in ("kakao", "naver", "google"):
        raise HTTPException(status_code=400, detail={"code": "UNKNOWN_PROVIDER"})
    return {
        "user": {
            "id": f"u-{provider}",
            "email": f"{provider}@example.com",
            "name": f"{provider} 사용자",
        }
    }
