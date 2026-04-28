"""SQLAlchemy 2.0 declarative Base.

모든 ORM 모델은 본 ``Base`` 를 상속한다. metadata 분리는 하지 않는다 —
스키마 단일 소스 (PostgreSQL + TimescaleDB 인스턴스 1개) 가정.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 모델의 공통 부모. 추가 mixin 필요 시 본 클래스에 합친다."""

    pass
