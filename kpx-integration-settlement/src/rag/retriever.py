"""pgvector 기반 유사 날 검색.

오늘 전력 패턴과 가장 유사한 과거 날을 household_embeddings 테이블에서 검색.
LLM 프롬프트 맥락 주입 및 신규 가구 Proxy CBL에 활용.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import numpy as np


@dataclass
class SimilarDay:
    ref_date: date
    similarity: float
    savings_kwh: float | None   # 해당 날 DR 이벤트 절감량 (있으면)
    top_appliances: list[str]   # 주요 사용 가전
    temperature: float | None


class EmbeddingRepository(Protocol):
    async def search_similar(
        self,
        household_id: str,
        query_vector: np.ndarray,
        top_k: int = 5,
        exclude_date: date | None = None,
    ) -> list[SimilarDay]: ...


class SimilarDayRetriever:
    def __init__(self, repo: EmbeddingRepository) -> None:
        self._repo = repo

    async def retrieve(
        self,
        household_id: str,
        query_vector: np.ndarray,
        top_k: int = 3,
        exclude_today: date | None = None,
    ) -> list[SimilarDay]:
        """유사 날 top_k개 반환."""
        return await self._repo.search_similar(
            household_id, query_vector, top_k, exclude_today
        )

    def to_context_text(self, similar_days: list[SimilarDay]) -> str:
        """LLM 프롬프트에 주입할 맥락 텍스트 생성."""
        if not similar_days:
            return "유사 패턴 데이터 없음."
        lines = []
        for d in similar_days:
            parts = [f"{d.ref_date}(유사도:{d.similarity:.2f})"]
            if d.temperature is not None:
                parts.append(f"기온:{d.temperature:.1f}도")
            if d.top_appliances:
                parts.append(f"주요가전:{','.join(d.top_appliances)}")
            if d.savings_kwh is not None:
                parts.append(f"절감:{d.savings_kwh:.2f}kWh")
            lines.append(" ".join(parts))
        return "\n".join(lines)
