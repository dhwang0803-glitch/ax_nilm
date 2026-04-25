"""KPX Open API 게이트웨이.

DR 이벤트 수신 및 감축 실적 전송.
실제 KPX API 스펙 확보 후 구현 예정 — 현재 인터페이스 정의 및 Mock 제공.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass
class DREventPayload:
    event_id: str
    start_ts: datetime
    end_ts: datetime
    target_kw: float
    issued_at: datetime


@dataclass
class PerformanceReport:
    event_id: str
    household_id: str
    savings_kwh: float
    reported_at: datetime


class KPXGateway(Protocol):
    async def fetch_dr_events(self) -> list[DREventPayload]: ...
    async def submit_performance(self, report: PerformanceReport) -> bool: ...


class MockKPXGateway:
    """KPX API 스펙 확보 전 사용하는 Mock 구현체."""

    async def fetch_dr_events(self) -> list[DREventPayload]:
        return [
            DREventPayload(
                event_id  = "EVT_MOCK_001",
                start_ts  = datetime(2024, 7, 15, 18, 0),
                end_ts    = datetime(2024, 7, 15, 19, 0),
                target_kw = 500.0,
                issued_at = datetime(2024, 7, 15, 17, 30),
            )
        ]

    async def submit_performance(self, report: PerformanceReport) -> bool:
        return True


class HttpKPXGateway:
    """실제 KPX Open API 연동 — API 스펙 확보 후 구현."""

    def __init__(self) -> None:
        self._base_url  = os.getenv("KPX_API_BASE_URL", "")
        self._api_key   = os.getenv("KPX_API_KEY", "")
        if not self._base_url or not self._api_key:
            raise EnvironmentError("KPX_API_BASE_URL, KPX_API_KEY 환경변수 필요")

    async def fetch_dr_events(self) -> list[DREventPayload]:
        raise NotImplementedError("KPX API 스펙 확보 후 구현")

    async def submit_performance(self, report: PerformanceReport) -> bool:
        raise NotImplementedError("KPX API 스펙 확보 후 구현")


def get_kpx_gateway() -> KPXGateway:
    """환경변수 설정 여부에 따라 실제/Mock 게이트웨이 반환."""
    if os.getenv("KPX_API_BASE_URL"):
        return HttpKPXGateway()
    return MockKPXGateway()
