"""설정 화면 응답 스키마 — Frontend `src/features/settings/types.ts` 와 매칭."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ─── 계정 ────────────────────────────────────────────


class AccountProfile(BaseModel):
    name: str
    email: str
    phone: str
    member_count: int = Field(alias="memberCount")

    model_config = {"populate_by_name": True}


class KepcoLink(BaseModel):
    customer_no: str = Field(alias="customerNo")
    address_masked: str = Field(alias="addressMasked")
    contract_type: str = Field(alias="contractType")
    linked_at: str = Field(alias="linkedAt")

    model_config = {"populate_by_name": True}


class AccountResponse(BaseModel):
    profile: AccountProfile
    kepco: KepcoLink


# ─── 알림 ────────────────────────────────────────────


NotificationKind = Literal["anomaly", "cashback", "weeklyReport", "system"]


class NotificationRow(BaseModel):
    kind: NotificationKind
    email: bool
    sms: bool
    push: bool


class DoNotDisturb(BaseModel):
    enabled: bool
    start_minutes: int = Field(alias="startMinutes")
    end_minutes: int = Field(alias="endMinutes")

    model_config = {"populate_by_name": True}


class NotificationsResponse(BaseModel):
    matrix: list[NotificationRow]
    do_not_disturb: DoNotDisturb = Field(alias="doNotDisturb")

    model_config = {"populate_by_name": True}


# ─── 보안 ────────────────────────────────────────────


class SessionEntry(BaseModel):
    id: str
    device: str
    location: str
    last_active_at: str = Field(alias="lastActiveAt")
    current: bool

    model_config = {"populate_by_name": True}


class SecurityResponse(BaseModel):
    two_factor_enabled: bool = Field(alias="twoFactorEnabled")
    sessions: list[SessionEntry]

    model_config = {"populate_by_name": True}


# ─── 이상 탐지 이력 ──────────────────────────────────


class AnomalyKpi(BaseModel):
    month_count: int = Field(alias="monthCount")
    avg_response_minutes: int = Field(alias="avgResponseMinutes")
    unresolved_count: int = Field(alias="unresolvedCount")

    model_config = {"populate_by_name": True}


class AnomalyEvent(BaseModel):
    id: str
    occurred_at: str = Field(alias="occurredAt")
    appliance: str
    severity: Literal["high", "medium", "low"]
    description: str
    status: Literal["open", "resolved"]

    model_config = {"populate_by_name": True}


class AnomalyEventsResponse(BaseModel):
    kpi: AnomalyKpi
    events: list[AnomalyEvent]


# ─── 이메일 ──────────────────────────────────────────


class EmailToggles(BaseModel):
    anomaly: bool
    cashback: bool
    weekly_report: bool = Field(alias="weeklyReport")
    policy: bool

    model_config = {"populate_by_name": True}


class EmailResponse(BaseModel):
    primary_email: str = Field(alias="primaryEmail")
    alternate_email: str | None = Field(default=None, alias="alternateEmail")
    toggles: EmailToggles
    last_test_at: str | None = Field(default=None, alias="lastTestAt")

    model_config = {"populate_by_name": True}
