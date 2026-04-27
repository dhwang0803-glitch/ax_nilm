"""가구 관련 ORM.

- ``Household``           — 평문 분류값 (schemas/001 + migration 02)
- ``HouseholdPII``        — AES-256 암호화 BYTEA 분리 테이블
- ``HouseholdChannel``    — 가구 × ch## 가전 매핑
- ``HouseholdDailyEnv``   — 가구 × 일자 날씨/기온/풍속/습도
- ``HouseholdEmbedding``  — pgvector (migration 05, 차원 미지정)
"""
from __future__ import annotations

from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    Numeric,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Household(Base):
    __tablename__ = "households"

    household_id: Mapped[str] = mapped_column(Text, primary_key=True)
    house_type: Mapped[str | None] = mapped_column(Text)
    residential_type: Mapped[str | None] = mapped_column(Text)
    residential_area: Mapped[str | None] = mapped_column(Text)
    co_lighting: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    # migration 02 추가 컬럼
    cluster_label: Mapped[int | None] = mapped_column(SmallInteger)
    dr_enrolled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    aggregator_id: Mapped[str | None] = mapped_column(
        ForeignKey("aggregators.aggregator_id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint(r"household_id ~ '^H[0-9]{3}$'"),
        CheckConstraint(
            "cluster_label IS NULL OR cluster_label BETWEEN 0 AND 8",
            name="chk_households_cluster_label",
        ),
    )


class HouseholdPII(Base):
    """🔒 PII — 직접 SELECT 권한 분리. 평문 노출 금지."""

    __tablename__ = "household_pii"

    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.household_id", ondelete="CASCADE"),
        primary_key=True,
    )
    address_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    members_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    income_dual: Mapped[bool | None] = mapped_column(Boolean)
    utility_facilities: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    extra_appliances: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )


class HouseholdChannel(Base):
    __tablename__ = "household_channels"

    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.household_id", ondelete="CASCADE"),
        primary_key=True,
    )
    channel_num: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    appliance_code: Mapped[str] = mapped_column(
        ForeignKey("appliance_types.appliance_code"), nullable=False
    )
    device_name: Mapped[str | None] = mapped_column(Text)
    brand: Mapped[str | None] = mapped_column(Text)
    power_category: Mapped[str | None] = mapped_column(Text)
    power_consumption: Mapped[float | None] = mapped_column(Numeric(8, 2))
    energy_efficiency: Mapped[int | None] = mapped_column(SmallInteger)

    __table_args__ = (
        CheckConstraint("channel_num BETWEEN 1 AND 23"),
        CheckConstraint(
            "power_category IS NULL OR power_category IN ('high','middle','low')"
        ),
        CheckConstraint(
            "energy_efficiency IS NULL OR energy_efficiency BETWEEN 1 AND 5"
        ),
    )


class HouseholdDailyEnv(Base):
    __tablename__ = "household_daily_env"

    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.household_id", ondelete="CASCADE"),
        primary_key=True,
    )
    observed_date: Mapped[date] = mapped_column(Date, primary_key=True)
    weather_raw: Mapped[str | None] = mapped_column(Text)
    temperature_c: Mapped[float | None] = mapped_column(Numeric(5, 2))
    wind_speed_ms: Mapped[float | None] = mapped_column(Numeric(5, 2))
    humidity_pct: Mapped[float | None] = mapped_column(Numeric(5, 2))


class HouseholdEmbedding(Base):
    """차원 미지정 pgvector — migration 05. KPX ADR 후 차원 확정 예정."""

    __tablename__ = "household_embeddings"

    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.household_id", ondelete="CASCADE"),
        primary_key=True,
    )
    ref_date: Mapped[date] = mapped_column(Date, primary_key=True)
    embed_model: Mapped[str] = mapped_column(Text, primary_key=True)
    # 차원 미지정 vector — 후속 마이그레이션에서 vector(384|768) 로 고정.
    embedding: Mapped[list[float]] = mapped_column(Vector(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
