"""환경변수 기반 설정 — 루트 CLAUDE.md 보안 규칙 준수.

자격증명/시크릿은 코드 기본값에 절대 두지 않는다 (`os.getenv()` 만 사용,
실제 값이 없으면 dev 데모용으로만 사용 가능한 명시적 placeholder).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "config/.env", "API_Server/config/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 앱
    app_env: Literal["dev", "staging", "prod"] = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_log_level: str = "info"

    # CORS
    cors_allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # 인증
    jwt_secret: str = Field(default="dev-only-change-me-32-byte-secret-string")
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    cookie_name: str = "ax_nilm_session"
    cookie_secure: bool = False
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # 데모 계정 (Frontend MSW 와 동일 자격증명 — 공모전 시연용)
    demo_user_email: str = "test@example.com"
    demo_user_password: str = "nilm-mock-2026!"
    demo_user_name: str = "테스터"
    demo_household_id: str = "H001"

    # 데이터 소스
    use_db: bool = False
    database_url: str | None = None
    credential_master_key: str | None = None

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
