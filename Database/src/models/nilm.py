"""NILM 라벨 / 추론 결과 / ETL 이력 ORM.

- ``ActivityInterval``           — AI Hub ground truth 라벨
- ``ApplianceStatusInterval``    — CNN+TDA NILM 모델 출력 (구간 기반)
- ``IngestionLog``               — ETL 파일별 적재 이력
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ActivityInterval(Base):
    __tablename__ = "activity_intervals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    household_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="aihub_71685"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("start_ts < end_ts"),
        ForeignKeyConstraint(
            ["household_id", "channel_num"],
            ["household_channels.household_id", "household_channels.channel_num"],
            ondelete="CASCADE",
        ),
        # EXCLUDE USING gist 제약은 SQLAlchemy 표준 미지원 — schemas/002 에서
        # SQL 로 생성됨. ORM 측은 구간 겹침 INSERT 시 IntegrityError 로 받음.
    )


class ApplianceStatusInterval(Base):
    """CNN+TDA NILM 출력. ``end_ts IS NULL`` = 진행 중 구간."""

    __tablename__ = "appliance_status_intervals"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    household_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    start_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status_code: Mapped[int] = mapped_column(
        ForeignKey("appliance_status_codes.status_code"), nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("end_ts IS NULL OR start_ts < end_ts"),
        CheckConstraint("confidence IS NULL OR confidence BETWEEN 0.0 AND 1.0"),
        CheckConstraint("channel_num BETWEEN 1 AND 23"),
        ForeignKeyConstraint(
            ["household_id", "channel_num"],
            ["household_channels.household_id", "household_channels.channel_num"],
            ondelete="CASCADE",
        ),
    )


class IngestionLog(Base):
    __tablename__ = "ingestion_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    household_id: Mapped[str] = mapped_column(Text, nullable=False)
    channel_num: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    file_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_row_count: Mapped[int | None] = mapped_column(BigInteger)
    agg_row_count: Mapped[int | None] = mapped_column(BigInteger)
    intervals_count: Mapped[int | None] = mapped_column(Integer)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="ok")
    notes: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'partial', 'failed', 'skipped')"),
    )
