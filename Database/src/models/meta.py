"""정적 마스터 테이블 ORM.

- ``ApplianceType``        — 22 가전 + MAIN 카테고리 (schemas/001 + migration 06)
- ``Aggregator``           — 수요관리사업자 (migration 01)
- ``ApplianceStatusCode``  — NILM 상태 코드 마스터 (schemas/004 + migration 07)
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ApplianceType(Base):
    __tablename__ = "appliance_types"

    appliance_code: Mapped[str] = mapped_column(Text, primary_key=True)
    name_ko: Mapped[str] = mapped_column(Text, nullable=False)
    name_en: Mapped[str | None] = mapped_column(Text)
    default_channel: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, unique=True
    )
    nilm_type: Mapped[int | None] = mapped_column(SmallInteger)
    # migration 06 — nilm-engine 모델 출력 인덱스(0~21). MAIN 은 NULL.
    nilm_label_index: Mapped[int | None] = mapped_column(
        SmallInteger, unique=True
    )

    __table_args__ = (
        CheckConstraint("default_channel BETWEEN 1 AND 23"),
        CheckConstraint("nilm_type IS NULL OR nilm_type BETWEEN 1 AND 4"),
        CheckConstraint(
            "nilm_label_index IS NULL OR nilm_label_index BETWEEN 0 AND 21",
            name="chk_appliance_types_nilm_label_index_range",
        ),
    )


class Aggregator(Base):
    __tablename__ = "aggregators"

    aggregator_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # 원/kWh — KPX 정산 단가. settlement_rate > 0 CHECK.
    settlement_rate: Mapped[float] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    __table_args__ = (CheckConstraint("settlement_rate > 0"),)


class ApplianceStatusCode(Base):
    __tablename__ = "appliance_status_codes"

    status_code: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    label_en: Mapped[str] = mapped_column(Text, nullable=False)
    label_ko: Mapped[str | None] = mapped_column(Text)
    appliance_code: Mapped[str | None] = mapped_column(
        ForeignKey("appliance_types.appliance_code")
    )
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
