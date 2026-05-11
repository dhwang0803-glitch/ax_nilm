"""시계열 전력 ORM (TimescaleDB hypertable + continuous aggregate).

- ``PowerMinute``           — power_1min hypertable (hot, 7일 retention)
- ``PowerHour``             — power_1hour cagg (1시간 다운샘플, read-only)
- ``PowerEfficiency30Min``  — DR 정산용 30분 사전집계 (migration 04)

ORM 은 INSERT/SELECT 만 다룬다. hypertable 생성, retention, cagg 정책은
``schemas/`` 와 ``migrations/`` SQL 이 책임진다.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    PrimaryKeyConstraint,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class PowerMinute(Base):
    """1분 집계 hypertable. PK 는 (household_id, channel_num, bucket_ts).

    스키마 자체에는 PK 가 없고 unique index 로 강제되지만, ORM 측은 PK 가
    필요하므로 동일 컬럼 조합을 PK 로 선언한다 (실제 DB 는 unique index).
    """

    __tablename__ = "power_1min"

    bucket_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    household_id: Mapped[str] = mapped_column(Text)
    channel_num: Mapped[int] = mapped_column(SmallInteger)

    active_power_avg: Mapped[float | None]
    active_power_min: Mapped[float | None]
    active_power_max: Mapped[float | None]
    energy_wh: Mapped[float | None]

    voltage_avg: Mapped[float | None]
    current_avg: Mapped[float | None]
    frequency_avg: Mapped[float | None]
    apparent_power_avg: Mapped[float | None]
    reactive_power_avg: Mapped[float | None]
    power_factor_avg: Mapped[float | None]
    phase_difference_avg: Mapped[float | None]

    sample_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        PrimaryKeyConstraint(
            "household_id",
            "channel_num",
            "bucket_ts",
            name="pk_power_1min",
        ),
        CheckConstraint("channel_num BETWEEN 1 AND 23"),
        CheckConstraint(
            "power_factor_avg IS NULL OR power_factor_avg BETWEEN 0 AND 1"
        ),
        CheckConstraint(
            "sample_count IS NULL OR sample_count BETWEEN 0 AND 1800"
        ),
    )


class PowerHour(Base):
    """power_1hour continuous aggregate — 읽기 전용.

    ORM 으로 매핑하나 INSERT/UPDATE/DELETE 금지 (cagg 가 자동 갱신). PK 는
    cagg group-by 키와 동일.
    """

    __tablename__ = "power_1hour"

    hour_bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    household_id: Mapped[str] = mapped_column(Text)
    channel_num: Mapped[int] = mapped_column(SmallInteger)

    active_power_avg: Mapped[float | None]
    active_power_min: Mapped[float | None]
    active_power_max: Mapped[float | None]
    energy_wh: Mapped[float | None]
    voltage_avg: Mapped[float | None]
    current_avg: Mapped[float | None]
    frequency_avg: Mapped[float | None]
    apparent_power_avg: Mapped[float | None]
    reactive_power_avg: Mapped[float | None]
    power_factor_avg: Mapped[float | None]
    phase_difference_avg: Mapped[float | None]
    sample_count: Mapped[int | None] = mapped_column(Integer)
    minute_bucket_count: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        PrimaryKeyConstraint(
            "household_id",
            "channel_num",
            "hour_bucket",
            name="pk_power_1hour",
        ),
    )


class PowerEfficiency30Min(Base):
    """30분 사전집계 hypertable — KPX UC-2 calc_savings 의 단일 조회 소스.

    is_dr_window=FALSE → 일반 효율 패널, TRUE → DR 정산. CHECK 로 두
    의미가 (event_id NULL/NOT NULL) 와 정합되도록 강제됨.
    """

    __tablename__ = "power_efficiency_30min"

    bucket_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    household_id: Mapped[str] = mapped_column(Text)
    channel_num: Mapped[int] = mapped_column(SmallInteger)

    energy_wh: Mapped[float] = mapped_column(nullable=False)
    cbl_wh: Mapped[float | None]
    savings_wh: Mapped[float] = mapped_column(
        nullable=False, server_default="0"
    )

    is_dr_window: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    event_id: Mapped[str | None] = mapped_column(
        ForeignKey("dr_events.event_id", ondelete="SET NULL")
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        PrimaryKeyConstraint(
            "household_id",
            "channel_num",
            "bucket_ts",
            name="pk_power_efficiency_30min",
        ),
        ForeignKeyConstraint(
            ["household_id", "channel_num"],
            ["household_channels.household_id", "household_channels.channel_num"],
            ondelete="CASCADE",
        ),
        CheckConstraint("channel_num BETWEEN 1 AND 23"),
        CheckConstraint("energy_wh >= 0"),
        CheckConstraint("cbl_wh IS NULL OR cbl_wh >= 0"),
        CheckConstraint(
            "(is_dr_window AND event_id IS NOT NULL) "
            "OR (NOT is_dr_window AND event_id IS NULL)"
        ),
    )
