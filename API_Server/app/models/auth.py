"""인증 요청/응답 스키마 — Frontend MSW handler 와 1:1 매칭."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=64)
    agree_terms: bool = Field(alias="agreeTerms")
    kepco_customer_number: str | None = Field(default=None, alias="kepcoCustomerNumber")

    model_config = {"populate_by_name": True}


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str


class AuthResponse(BaseModel):
    user: UserPublic


class ErrorResponse(BaseModel):
    code: str
    message: str
