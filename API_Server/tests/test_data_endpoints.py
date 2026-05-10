"""Frontend 가 호출하는 모든 데이터 엔드포인트 — 인증 게이팅 + 응답 스키마 키 검증."""
from __future__ import annotations

import pytest


PROTECTED = [
    "/api/dashboard/summary",
    "/api/usage/analysis",
    "/api/cashback/tracker",
    "/api/insights/summary",
    "/api/settings/account",
    "/api/settings/notifications",
    "/api/settings/security",
    "/api/settings/anomaly-events",
    "/api/settings/email",
]


@pytest.mark.parametrize("path", PROTECTED)
def test_requires_auth(client, path):
    resp = client.get(path)
    assert resp.status_code == 401


def test_dashboard_shape(authed_client):
    body = authed_client.get("/api/dashboard/summary").json()
    assert set(body.keys()) >= {"kpis", "weekly", "monthly", "applianceBreakdown"}
    assert body["kpis"]["monthlyUsageKwh"] == 218
    assert len(body["weekly"]["days"]) == 7
    assert len(body["monthly"]["months"]) == 12


def test_usage_shape(authed_client):
    body = authed_client.get("/api/usage/analysis").json()
    assert len(body["hourly"]["hours"]) == 24
    assert {"weekly", "hourly", "applianceBreakdown", "monthly"} <= set(body.keys())


def test_cashback_shape(authed_client):
    body = authed_client.get("/api/cashback/tracker").json()
    assert body["goal"]["targetSavingsPercent"] == 10
    assert len(body["missions"]) == 3


def test_insights_shape(authed_client):
    body = authed_client.get("/api/insights/summary").json()
    assert body["modelVersion"] == "v2.4"
    assert len(body["recommendations"]) == 6


def test_settings_account_uses_session_email(authed_client):
    body = authed_client.get("/api/settings/account").json()
    assert body["profile"]["email"] == "test@example.com"


def test_settings_anomaly_events(authed_client):
    body = authed_client.get("/api/settings/anomaly-events").json()
    assert body["kpi"]["unresolvedCount"] == 2
    assert len(body["events"]) == 8


def test_settings_email_uses_session(authed_client):
    body = authed_client.get("/api/settings/email").json()
    assert body["primaryEmail"] == "test@example.com"
    assert body["toggles"]["weeklyReport"] is False


def test_healthz_no_auth(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
