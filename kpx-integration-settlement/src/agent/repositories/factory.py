"""레포지토리 팩토리 — 환경에 따라 구현체를 선택한다.

DB_PASSWORD 설정 시 DbRepository(실 DB 연결),
미설정 시 MockRepository(인메모리 mock 데이터) 반환.

현재는 두 구현 모두 data_tools.py의 함수를 위임 호출한다.
향후 mock/db 로직이 분리되면 각 클래스 내부만 교체하면 된다.
"""
from __future__ import annotations

import os
from typing import Any

from .base import IHouseholdRepository


# ── 구현체 ────────────────────────────────────────────────────────────────────

class _DataToolsRepository(IHouseholdRepository):
    """data_tools.py 공개 함수를 위임 호출하는 어댑터.

    data_tools.py 가 이미 DB_PASSWORD 유무에 따라 DB/mock을 분기하므로
    현재 단계에서는 단일 클래스로 두 경우를 모두 처리한다.
    """

    def get_household_profile(self, household_id: str) -> dict[str, Any]:
        from ..data_tools import get_household_profile
        return get_household_profile(household_id)

    def get_consumption_summary(
        self, household_id: str, period: str = "week"
    ) -> dict[str, Any]:
        from ..data_tools import get_consumption_summary
        return get_consumption_summary(household_id, period)

    def get_cashback_history(
        self, household_id: str, date_range: list[str] | None = None
    ) -> dict[str, Any]:
        from ..data_tools import get_cashback_history
        return get_cashback_history(household_id, date_range)

    def get_tariff_info(self, household_id: str) -> dict[str, Any]:
        from ..data_tools import get_tariff_info
        return get_tariff_info(household_id)

    def get_anomaly_events(
        self, household_id: str, status: str = "active"
    ) -> dict[str, Any]:
        from ..data_tools import get_anomaly_events
        return get_anomaly_events(household_id, status)

    def get_anomaly_log(
        self,
        household_id: str,
        date_range: list[str] | None = None,
        severity: str = "all",
        appliance: str | None = None,
    ) -> dict[str, Any]:
        from ..data_tools import get_anomaly_log
        return get_anomaly_log(household_id, date_range, severity, appliance)

    def get_hourly_appliance_breakdown(
        self, household_id: str, date: str = "2026-04-27"
    ) -> dict[str, Any]:
        from ..data_tools import get_hourly_appliance_breakdown
        return get_hourly_appliance_breakdown(household_id, date)

    def get_consumption_hourly(
        self, household_id: str, date: str = "2026-04-27"
    ) -> dict[str, Any]:
        from ..data_tools import get_consumption_hourly
        return get_consumption_hourly(household_id, date)

    def get_consumption_breakdown(
        self, household_id: str, date: str = "2026-04-27"
    ) -> dict[str, Any]:
        from ..data_tools import get_consumption_breakdown
        return get_consumption_breakdown(household_id, date)

    def get_dashboard_summary(
        self, household_id: str, month: str = "2026-04"
    ) -> dict[str, Any]:
        from ..data_tools import get_dashboard_summary
        return get_dashboard_summary(household_id, month)

    def get_weather(
        self, date_range: list[str], location: str = "서울"
    ) -> dict[str, Any]:
        from ..data_tools import get_weather
        return get_weather(date_range, location)

    def get_forecast(
        self, days_ahead: int = 7, location: str = "서울"
    ) -> dict[str, Any]:
        from ..data_tools import get_forecast
        return get_forecast(days_ahead, location)


# ── 팩토리 ────────────────────────────────────────────────────────────────────

_repo: IHouseholdRepository | None = None


def get_repository() -> IHouseholdRepository:
    """프로세스 내 싱글턴 레포지토리 반환.

    DB_PASSWORD 환경변수 존재 여부로 DB/mock 구현체를 결정한다.
    현재는 두 경우 모두 _DataToolsRepository를 반환하며,
    mock.py / db.py 클래스가 완성되면 이 함수만 교체한다.
    """
    global _repo
    if _repo is None:
        _repo = _DataToolsRepository()
    return _repo
