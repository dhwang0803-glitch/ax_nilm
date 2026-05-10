"""Pytest fixtures — TestClient + 인증 헬퍼."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="session")
def app():
    # 테스트 환경 격리 — 실 .env 영향 차단
    os.environ.setdefault("APP_ENV", "dev")
    os.environ.setdefault("USE_DB", "false")
    os.environ.setdefault("JWT_SECRET", "test-secret-32-bytes-for-pytest-only")
    os.environ.setdefault("DEMO_USER_EMAIL", "test@example.com")
    os.environ.setdefault("DEMO_USER_PASSWORD", "nilm-mock-2026!")

    from app.config import get_settings
    get_settings.cache_clear()  # 환경변수 변경 반영

    from app.main import create_app
    return create_app()


@pytest.fixture
def client(app) -> TestClient:
    return TestClient(app)


@pytest.fixture
def authed_client(client: TestClient) -> TestClient:
    """로그인 완료된 클라이언트 (쿠키 보유)."""
    resp = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "nilm-mock-2026!"},
    )
    assert resp.status_code == 200, resp.text
    return client
