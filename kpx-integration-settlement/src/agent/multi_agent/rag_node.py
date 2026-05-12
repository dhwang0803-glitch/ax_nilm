"""Module 4 — RAG 검색 노드.

cashback_output.savings_rate를 기반으로 쿼리를 구성하고
pgvector에서 관련 청크를 검색해 state에 주입한다.
"""
from __future__ import annotations

from typing import Any

from ..rag_retriever import retrieve


def rag_node(state: dict[str, Any]) -> dict[str, Any]:
    cashback_output = state.get("cashback_output") or {}
    savings_rate = cashback_output.get("savings_rate", 0)
    query = f"에너지캐시백 절감률 {savings_rate:.0%} 절감 권고"
    return {"rag_context": retrieve(query, k=3)}
