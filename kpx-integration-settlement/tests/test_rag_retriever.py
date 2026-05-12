"""RAG 검색 모듈 단위 테스트.

외부 의존성(OpenAI API, PostgreSQL) 전부 mock — DB/API키 없이 실행 가능.
"""
from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


# ─── 1. 폴백 동작 (환경변수 미설정) ─────────────────────────────────────────


def test_retrieve_returns_empty_without_api_key(monkeypatch):
    """OPENAI_API_KEY 미설정 시 retrieve()는 [] 반환해야 한다."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.agent.rag_retriever import retrieve
    assert retrieve("에너지캐시백 신청") == []


def test_retrieve_with_scores_returns_empty_without_api_key(monkeypatch):
    """OPENAI_API_KEY 미설정 시 retrieve_with_scores()는 [] 반환해야 한다."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from src.agent.rag_retriever import retrieve_with_scores
    assert retrieve_with_scores("기준 사용량") == []


def test_retrieve_returns_empty_when_db_unavailable(monkeypatch):
    """DB 연결 불가 시 retrieve()는 [] 반환해야 한다 (예외 노출 금지)."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("src.agent.rag_retriever._get_db_conn", return_value=None):
        from src.agent import rag_retriever
        result = rag_retriever.retrieve("절감 팁")
    assert result == []


def test_retrieve_with_scores_returns_empty_when_db_unavailable(monkeypatch):
    """DB 연결 불가 시 retrieve_with_scores()는 [] 반환해야 한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    with patch("src.agent.rag_retriever._get_db_conn", return_value=None):
        from src.agent import rag_retriever
        result = rag_retriever.retrieve_with_scores("절감 팁")
    assert result == []


# ─── 2. 시그니처 및 기본값 ───────────────────────────────────────────────────


def test_retrieve_signature_defaults():
    """retrieve()의 k=5, category=None 기본값을 확인한다."""
    import inspect
    from src.agent.rag_retriever import retrieve
    sig = inspect.signature(retrieve)
    assert sig.parameters["k"].default == 5
    assert sig.parameters["category"].default is None


def test_retrieve_with_scores_signature_defaults():
    """retrieve_with_scores()의 k=5, category=None 기본값을 확인한다."""
    import inspect
    from src.agent.rag_retriever import retrieve_with_scores
    sig = inspect.signature(retrieve_with_scores)
    assert sig.parameters["k"].default == 5
    assert sig.parameters["category"].default is None


# ─── 3. mock DB 연결 — 정상 경로 ────────────────────────────────────────────


def _make_mock_conn(rows):
    """psycopg2 커넥션 mock 헬퍼."""
    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = rows
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    return mock_conn


def test_retrieve_returns_content_list(monkeypatch):
    """DB에서 행을 받으면 content 문자열 리스트를 반환해야 한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_rows = [("에너지캐시백이란 절전 시 지급하는 보조금입니다.",),
                 ("3% 이상 절감 시 30~100원/kWh를 받을 수 있습니다.",)]

    with patch("src.agent.rag_retriever._get_db_conn", return_value=_make_mock_conn(fake_rows)), \
         patch("src.agent.rag_retriever._embed", return_value=[0.1] * 1536):
        from src.agent import rag_retriever
        result = rag_retriever.retrieve("캐시백 금액", k=2)

    assert len(result) == 2
    assert all(isinstance(s, str) for s in result)
    assert "에너지캐시백" in result[0]


def test_retrieve_with_scores_returns_dict_list(monkeypatch):
    """retrieve_with_scores()는 doc_id·chunk_index·score 키를 포함한 dict 리스트를 반환해야 한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_rows = [
        ("policy_cashback_tiers", 0, "30~100원/kWh 단계별 지급", "정책 참조", 0.12),
    ]

    with patch("src.agent.rag_retriever._get_db_conn", return_value=_make_mock_conn(fake_rows)), \
         patch("src.agent.rag_retriever._embed", return_value=[0.1] * 1536):
        from src.agent import rag_retriever
        result = rag_retriever.retrieve_with_scores("캐시백 단가", k=1)

    assert len(result) == 1
    item = result[0]
    assert set(item.keys()) == {"doc_id", "chunk_index", "content", "category", "score"}
    assert item["doc_id"] == "policy_cashback_tiers"
    assert isinstance(item["score"], float)


def test_retrieve_respects_k_limit(monkeypatch):
    """k 파라미터가 SQL LIMIT에 정확히 반영되어야 한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    fake_rows = [("chunk1",), ("chunk2",), ("chunk3",)]

    with patch("src.agent.rag_retriever._get_db_conn", return_value=_make_mock_conn(fake_rows)), \
         patch("src.agent.rag_retriever._embed", return_value=[0.0] * 1536):
        from src.agent import rag_retriever
        result = rag_retriever.retrieve("query", k=3)

    assert len(result) == 3


# ─── 4. category 필터 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("category", ["가입 가이드", "절감 팁", "정책 참조"])
def test_retrieve_with_category_filter(monkeypatch, category):
    """category 파라미터가 있으면 WHERE category = %s 절을 포함한 쿼리가 실행되어야 한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    executed_sqls = []

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.execute.side_effect = lambda sql, params: executed_sqls.append((sql, params))

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("src.agent.rag_retriever._get_db_conn", return_value=mock_conn), \
         patch("src.agent.rag_retriever._embed", return_value=[0.0] * 1536):
        from src.agent import rag_retriever
        rag_retriever.retrieve("query", k=3, category=category)

    assert len(executed_sqls) == 1
    sql_used, params_used = executed_sqls[0]
    assert "WHERE category" in sql_used
    assert category in params_used


def test_retrieve_no_category_filter_omits_where(monkeypatch):
    """category=None이면 WHERE category 절이 없는 쿼리가 실행되어야 한다."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    executed_sqls = []

    mock_cursor = MagicMock()
    mock_cursor.fetchall.return_value = []
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.execute.side_effect = lambda sql, params: executed_sqls.append((sql, params))

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("src.agent.rag_retriever._get_db_conn", return_value=mock_conn), \
         patch("src.agent.rag_retriever._embed", return_value=[0.0] * 1536):
        from src.agent import rag_retriever
        rag_retriever.retrieve("query", k=3, category=None)

    assert len(executed_sqls) == 1
    sql_used, _ = executed_sqls[0]
    assert "WHERE category" not in sql_used


# ─── 5. DB 예외 — 폴백 보장 ─────────────────────────────────────────────────


def test_retrieve_returns_empty_on_db_exception(monkeypatch):
    """DB 쿼리 중 예외 발생 시 [] 반환해야 한다 (예외 전파 금지)."""
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    mock_cursor = MagicMock()
    mock_cursor.__enter__ = lambda s: s
    mock_cursor.__exit__ = MagicMock(return_value=False)
    mock_cursor.execute.side_effect = Exception("DB connection lost")

    mock_conn = MagicMock()
    mock_conn.cursor.return_value = mock_cursor

    with patch("src.agent.rag_retriever._get_db_conn", return_value=mock_conn), \
         patch("src.agent.rag_retriever._embed", return_value=[0.0] * 1536):
        from src.agent import rag_retriever
        result = rag_retriever.retrieve("query")

    assert result == []
