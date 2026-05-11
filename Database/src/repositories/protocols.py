"""Repository 인터페이스 — 다운스트림(API_Server / KPX / Execution_Engine) 가
구현체 대신 본 Protocol 에만 의존한다. 테스트는 InMemory 구현체로 대체.

KPX 호환:
    ``UsageRepository`` / ``AggregatorRepository`` 는
    ``kpx-integration-settlement/src/settlement/{cbl,calculator}.py`` 의 Protocol
    시그니처와 일치 (메서드명·인자·반환형). 두 모듈을 별도 import 하지
    않고도 KPX 모듈이 본 Protocol 만 보고 구현체를 받을 수 있도록 한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol, Sequence


# ─── 공용 DTO ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class DailyUsage:
    """KPX cbl.DailyUsage 와 구조 동일. 두 dataclass 중 어느 쪽을 사용하든
    duck-typed compatible 이지만, KPX 측 import 체인을 끊기 위해 본 모듈에서
    별도 정의."""

    day: date
    energy_kwh: float


@dataclass(frozen=True)
class DecryptedPII:
    """PII 복호화 결과 — 관리자 전용 API 에서만 반환. 로그 직렬화 금지."""

    household_id: str
    address: str | None
    members: str | None
    income_dual: bool | None
    utility_facilities: list[str] | None
    extra_appliances: list[str] | None


# ─── 시계열 / KPX UsageRepository ─────────────────────────────────────


class PowerRepository(Protocol):
    """power_1min / power_1hour / power_efficiency_30min 조회 인터페이스.

    KPX UsageRepository (cbl.py) 호환을 위해 ``get_weekday_usage`` /
    ``get_cluster_avg_ratio`` 도 본 Protocol 에 포함.
    """

    async def get_recent_minutes(
        self,
        household_id: str,
        channel_num: int,
        hours: int = 1,
    ) -> Sequence[tuple[datetime, float | None]]:
        """최근 N 시간 1분 평균전력 시계열."""
        ...

    async def get_hour_range(
        self,
        household_id: str,
        channel_num: int,
        start: datetime,
        end: datetime,
    ) -> Sequence[tuple[datetime, float | None, float | None]]:
        """1시간 다운샘플 (hour_bucket, energy_wh, active_power_avg)."""
        ...

    # ─── KPX 호환 ────────────────────────────────────────────────────
    async def get_weekday_usage(
        self,
        household_id: str,
        channel_num: int,
        event_start_date: date,
        limit: int = 10,
    ) -> list[DailyUsage]:
        """직전 N 평일 일별 소비량 (CBL 산정용)."""
        ...

    async def get_cluster_avg_ratio(
        self,
        cluster_label: int,
        channel_num: int,
    ) -> float:
        """동일 cluster 가구의 (channel_num 사용량 / ch01 사용량) 평균 비율.

        신규 가구 fallback CBL: ch01_proxy_cbl × ratio.
        """
        ...

    async def upsert_efficiency_30min(
        self,
        household_id: str,
        channel_num: int,
        bucket_ts: datetime,
        energy_wh: float,
        cbl_wh: float | None,
        is_dr_window: bool,
        event_id: str | None,
    ) -> None:
        """power_efficiency_30min UPSERT (Celery 배치 + DR 트리거 양쪽)."""
        ...


# ─── 가구 / PII / 채널 ────────────────────────────────────────────────


class HouseholdRepository(Protocol):
    async def get(self, household_id: str) -> object | None: ...
    async def list_by_aggregator(self, aggregator_id: str) -> Sequence[object]: ...
    async def list_by_cluster(self, cluster_label: int) -> Sequence[object]: ...
    async def set_cluster_label(
        self, household_id: str, cluster_label: int | None
    ) -> None: ...
    async def set_dr_enrollment(
        self, household_id: str, enrolled: bool, aggregator_id: str | None = None
    ) -> None: ...
    async def get_channels(self, household_id: str) -> Sequence[object]: ...


class PIIRepository(Protocol):
    """🔒 권한 분리 — 본 인터페이스를 분석 역할에 노출 금지."""

    async def upsert_encrypted(
        self,
        household_id: str,
        address: str | None,
        members: str | None,
        income_dual: bool | None,
        utility_facilities: list[str] | None,
        extra_appliances: list[str] | None,
    ) -> None: ...

    async def get_decrypted(self, household_id: str) -> DecryptedPII | None: ...


# ─── 라벨 / NILM 출력 ─────────────────────────────────────────────────


class ActivityRepository(Protocol):
    async def insert_intervals(
        self,
        household_id: str,
        channel_num: int,
        intervals: Sequence[tuple[datetime, datetime]],
        source: str = "aihub_71685",
    ) -> int: ...

    async def get_intervals(
        self,
        household_id: str,
        channel_num: int,
        start: datetime,
        end: datetime,
    ) -> Sequence[tuple[datetime, datetime, str]]: ...


class NILMInferenceRepository(Protocol):
    async def record_transition(
        self,
        household_id: str,
        channel_num: int,
        transition_ts: datetime,
        new_status: int,
        confidence: float | None,
        model_version: str,
    ) -> int:
        """단일 트랜잭션:
        (1) 기존 열린 구간(end_ts NULL) UPDATE 로 종료
        (2) 새 구간 INSERT (end_ts NULL).
        반환: 새 구간의 id.
        """
        ...

    async def get_current_status(
        self, household_id: str, channel_num: int, model_version: str
    ) -> tuple[int, datetime, float | None] | None:
        """진행 중 구간 (status_code, start_ts, confidence). 없으면 None."""
        ...

    async def get_history(
        self,
        household_id: str,
        channel_num: int,
        model_version: str,
        start: datetime,
        end: datetime,
        min_confidence: float | None = 0.6,
    ) -> Sequence[tuple[datetime, datetime | None, int, float | None]]: ...


class IngestionLogRepository(Protocol):
    async def record(
        self,
        source_file: str,
        household_id: str,
        channel_num: int,
        file_date: date,
        raw_row_count: int,
        agg_row_count: int,
        intervals_count: int | None,
        status: str = "ok",
        notes: str | None = None,
    ) -> int: ...

    async def is_already_ingested(self, source_file: str) -> bool: ...


# ─── KPX DR / Aggregator ──────────────────────────────────────────────


class AggregatorRepository(Protocol):
    """KPX calculator.AggregatorRepository 호환."""

    async def get_settlement_rate(self, aggregator_id: str) -> float: ...

    async def upsert(
        self, aggregator_id: str, name: str, settlement_rate: float
    ) -> None: ...


class DRRepository(Protocol):
    async def create_event(
        self,
        event_id: str,
        start_ts: datetime,
        end_ts: datetime,
        target_kw: float,
        status: str = "pending",
    ) -> None: ...

    async def update_event_status(self, event_id: str, status: str) -> None: ...

    async def get_event(self, event_id: str) -> object | None: ...

    async def upsert_result(
        self,
        event_id: str,
        household_id: str,
        cbl_kwh: float,
        actual_kwh: float,
        settlement_rate: float,
        cbl_method: str,
    ) -> None:
        """savings_kwh / refund_krw 는 cbl_kwh - actual_kwh / × settlement_rate
        로 본 메서드 내에서 산출 (호출자 단순화). 호출자는 DRSavingsResult
        dataclass 를 그대로 풀어 넘기지 않고 필드만 전달."""
        ...

    async def insert_appliance_savings(
        self,
        event_id: str,
        household_id: str,
        rows: Sequence[tuple[int, str, float, float]],
    ) -> int:
        """rows = [(channel_num, appliance_code, channel_cbl_kwh, channel_actual_kwh), ...]
        savings = cbl - actual 로 자동 산출. 반환: 적재 행 수."""
        ...

    async def get_results(self, event_id: str) -> Sequence[object]: ...
