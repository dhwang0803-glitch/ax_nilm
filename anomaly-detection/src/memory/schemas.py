"""모니터링 엔진 단기/장기 메모리 데이터 타입."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class StandbyEvent:
    """단기 메모리 — 대기전력 구간 측정값."""

    duration_min: float
    avg_w: float
    energy_wh: float


@dataclass
class ShortTermEvent:
    """단기 메모리 — 가전 1회 동작 이벤트.

    매시간 누적, 00시에 장기 메모리로 압축 후 리셋.
    """

    appliance: str
    mode: str
    started_at: datetime
    duration_min: float
    energy_wh: float
    avg_w: float
    peak_w: float
    standby: StandbyEvent | None = None


@dataclass
class ModeBaseline:
    """장기 메모리 — 가전 모드별 기준값."""

    avg_energy_wh: float
    avg_duration_min: float
    sample_count: int = 0


@dataclass
class ApplianceBaseline:
    """장기 메모리 — 가전 1종 전체."""

    appliance: str
    modes: dict[str, ModeBaseline] = field(default_factory=dict)
    standby_avg_w: float = 0.0
    standby_avg_duration_min: float = 0.0
