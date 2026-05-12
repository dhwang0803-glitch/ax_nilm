"""pgvector 기반 RAG 검색.

질의 → text-embedding-3-small → cosine 유사도 → top-k 청크 반환.
DB 미연결 시 빈 리스트 반환 (에이전트 폴백 호환).

사용 예:
    from src.agent.rag_retriever import retrieve

    chunks = retrieve("에너지캐시백 신청 방법", k=3)
    # → ["...", "...", "..."]

    chunks = retrieve("에어컨 절감 팁", k=5, category="절감 팁")
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

EMBEDDING_MODEL = "text-embedding-3-small"


@lru_cache(maxsize=256)
def _embed(text: str) -> list[float]:
    """텍스트 임베딩 (LRU 캐시 — 반복 질의 토큰 절약)."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.embeddings.create(model=EMBEDDING_MODEL, input=[text])
    return resp.data[0].embedding


def _get_db_conn():
    pw = os.getenv("DB_PASSWORD")
    if not pw:
        return None
    try:
        import psycopg2
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5436")),
            dbname=os.getenv("DB_NAME", "ax_nilm"),
            user=os.getenv("DB_USER", "ax_nilm_team"),
            password=pw,
            connect_timeout=5,
        )
    except Exception:
        return None


def retrieve(
    query: str,
    k: int = 5,
    category: Optional[str] = None,
) -> list[str]:
    """유사 청크 상위 k개의 content 반환.

    Args:
        query:    검색 질의 (자연어)
        k:        반환할 청크 수 (기본 5)
        category: "가입 가이드" | "절감 팁" | "정책 참조" 중 하나로 필터링 (None = 전체)

    Returns:
        청크 본문 문자열 리스트. DB 미연결 또는 결과 없으면 [].
    """
    if "OPENAI_API_KEY" not in os.environ:
        return []

    conn = _get_db_conn()
    if conn is None:
        return []

    try:
        embedding = _embed(query)
        vec_str = str(embedding)  # '[x, y, ...]' 형식으로 pgvector에 전달

        if category:
            sql = """
                SELECT content
                FROM rag_chunks
                WHERE category = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params = (category, vec_str, k)
        else:
            sql = """
                SELECT content
                FROM rag_chunks
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params = (vec_str, k)

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [row[0] for row in rows]
    except Exception:
        return []
    finally:
        conn.close()


def retrieve_with_scores(
    query: str,
    k: int = 5,
    category: Optional[str] = None,
) -> list[dict]:
    """유사 청크를 score·메타데이터 포함해 반환.

    Returns:
        list of {"doc_id", "chunk_index", "content", "category", "score"}
        score 낮을수록 유사도 높음 (cosine distance).
    """
    if "OPENAI_API_KEY" not in os.environ:
        return []

    conn = _get_db_conn()
    if conn is None:
        return []

    try:
        embedding = _embed(query)
        vec_str = str(embedding)

        if category:
            sql = """
                SELECT doc_id, chunk_index, content, category,
                       embedding <=> %s::vector AS score
                FROM rag_chunks
                WHERE category = %s
                ORDER BY score
                LIMIT %s
            """
            params = (vec_str, category, k)
        else:
            sql = """
                SELECT doc_id, chunk_index, content, category,
                       embedding <=> %s::vector AS score
                FROM rag_chunks
                ORDER BY score
                LIMIT %s
            """
            params = (vec_str, k)

        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

        return [
            {
                "doc_id": row[0],
                "chunk_index": row[1],
                "content": row[2],
                "category": row[3],
                "score": float(row[4]),
            }
            for row in rows
        ]
    except Exception:
        return []
    finally:
        conn.close()
