"""인증 엔드포인트 — 골든 패스 + 핵심 실패 케이스."""
from __future__ import annotations


def test_login_success_sets_cookie(client):
    resp = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "nilm-mock-2026!"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"user": {"id": "u1", "email": "test@example.com", "name": "테스터"}}
    assert "ax_nilm_session" in resp.cookies


def test_login_invalid_credentials(client):
    resp = client.post(
        "/auth/login",
        json={"email": "test@example.com", "password": "wrong"},
    )
    assert resp.status_code == 401
    body = resp.json()["detail"]
    assert body["code"] == "INVALID_CREDENTIALS"


def test_signup_taken_email(client):
    resp = client.post(
        "/auth/signup",
        json={
            "email": "taken@test.com",
            "password": "any-password-8+",
            "name": "Taken",
            "agreeTerms": True,
            "kepcoCustomerNumber": None,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["detail"]["code"] == "EMAIL_TAKEN"


def test_signup_success(client):
    resp = client.post(
        "/auth/signup",
        json={
            "email": "new@example.com",
            "password": "newuser-pass-2026",
            "name": "신규",
            "agreeTerms": True,
            "kepcoCustomerNumber": "12-3456-7890-12",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "new@example.com"


def test_oauth_kakao(client):
    resp = client.post("/auth/oauth/kakao")
    assert resp.status_code == 200
    assert resp.json()["user"]["id"] == "u-kakao"


def test_oauth_unknown_provider(client):
    resp = client.post("/auth/oauth/twitter")
    assert resp.status_code == 400


def test_me_unauthenticated(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_me_authenticated(authed_client):
    resp = authed_client.get("/auth/me")
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "test@example.com"


def test_logout_clears_cookie(authed_client):
    resp = authed_client.post("/auth/logout")
    assert resp.status_code == 204
    # 후속 요청은 401 — 쿠키가 만료됨
    follow = authed_client.get("/auth/me")
    assert follow.status_code == 401
