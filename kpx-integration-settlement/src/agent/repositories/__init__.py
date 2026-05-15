"""레포지토리 패키지 — 데이터 접근 추상화 레이어."""
from .base import IHouseholdRepository
from .factory import get_repository

__all__ = ["IHouseholdRepository", "get_repository"]
