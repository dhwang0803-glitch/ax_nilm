"""DR(수요반응) ORM — migration 03.

- ``DREvent``             — KPX 발행 이벤트 헤더
- ``DRResult``            — 가구별 정산 결과 (KPX UC-2 calc_savings 출력)
- ``DRApplianceSavings``  — 채널별 분해 (UI 전용, KPX 정산은 ch01 기준)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
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


class DREvent(Base):
    __tablename__ = "dr_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    start_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    target_kw: Mapped[float] = mapped_column(nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="pending"
    )

    __table_args__ = (
        CheckConstraint("start_ts < end_ts"),
        CheckConstraint("target_kw > 0"),
        CheckConstraint("status IN ('pending', 'active', 'completed', 'cancelled')"),
    )


class DRResult(Base):
    """KPX UC-2 calc_savings 출력. settlement_rate 는 이벤트 시점 스냅샷 (불변)."""

    __tablename__ = "dr_results"

    event_id: Mapped[str] = mapped_column(
        ForeignKey("dr_events.event_id", ondelete="CASCADE"), primary_key=True
    )
    household_id: Mapped[str] = mapped_column(
        ForeignKey("households.household_id", ondelete="CASCADE"),
        primary_key=True,
    )
    cbl_kwh: Mapped[float] = mapped_column(nullable=False)
    actual_kwh: Mapped[float] = mapped_column(nullable=False)
    savings_kwh: Mapped[float] = mapped_column(nullable=False)
    refund_krw: Mapped[int] = mapped_column(Integer, nullable=False)
    settlement_rate: Mapped[float] = mapped_column(nullable=False)
    cbl_method: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("cbl_kwh >= 0"),
        CheckConstraint("actual_kwh >= 0"),
        CheckConstraint("settlement_rate > 0"),
        CheckConstraint("cbl_method IN ('mid_6_10', 'proxy_cluster')"),
    )


class DRApplianceSavings(Base):
    __tablename__ = "dr_appliance_savings"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    household_id: Mapped[str] = mapped_column(Text, primary_key=True)
    channel_num: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    appliance_code: Mapped[str] = mapped_column(
        ForeignKey("appliance_types.appliance_code"), nullable=False
    )
    channel_cbl_kwh: Mapped[float] = mapped_column(nullable=False)
    channel_actual_kwh: Mapped[float] = mapped_column(nullable=False)
    channel_savings_kwh: Mapped[float] = mapped_column(nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "household_id"],
            ["dr_results.event_id", "dr_results.household_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["household_id", "channel_num"],
            ["household_channels.household_id", "household_channels.channel_num"],
            ondelete="CASCADE",
        ),
        CheckConstraint("channel_num BETWEEN 1 AND 23"),
        CheckConstraint("channel_cbl_kwh >= 0"),
        CheckConstraint("channel_actual_kwh >= 0"),
    )
