"""IHouseholdRepository — 데이터 접근 추상 인터페이스.

도메인 레이어는 이 인터페이스에만 의존한다.
실제 구현(mock / DB)은 factory.py에서 선택.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IHouseholdRepository(ABC):

    @abstractmethod
    def get_household_profile(self, household_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_consumption_summary(
        self,
        household_id: str,
        period: str = "week",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_cashback_history(
        self,
        household_id: str,
        date_range: list[str] | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_tariff_info(self, household_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def get_anomaly_events(
        self,
        household_id: str,
        status: str = "active",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_anomaly_log(
        self,
        household_id: str,
        date_range: list[str] | None = None,
        severity: str = "all",
        appliance: str | None = None,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_hourly_appliance_breakdown(
        self,
        household_id: str,
        date: str = "2026-04-27",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_consumption_hourly(
        self,
        household_id: str,
        date: str = "2026-04-27",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_consumption_breakdown(
        self,
        household_id: str,
        date: str = "2026-04-27",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_dashboard_summary(
        self,
        household_id: str,
        month: str = "2026-04",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_weather(
        self,
        date_range: list[str],
        location: str = "서울",
    ) -> dict[str, Any]: ...

    @abstractmethod
    def get_forecast(
        self,
        days_ahead: int = 7,
        location: str = "서울",
    ) -> dict[str, Any]: ...
