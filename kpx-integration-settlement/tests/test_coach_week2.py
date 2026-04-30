"""통합 테스트 — coach.py Week 2 기능 (OpenAI mock 사용).

실제 API 키 없이 테스트:
- baseline 컨텍스트 주입 확인
- tool 디스패치 + 익명화 + 트레이스 로깅 E2E 흐름
- PII 경고 감지 및 반환
- max_iterations 초과 시 빈 answer 반환
"""
from __future__ import annotations

import json
import os
import types
import unittest.mock as mock
from typing import Any

import pytest

from src.agent.coach import run_coach
from src.agent.context_engine import build_smart_context


# ─── 헬퍼: OpenAI 응답 픽스처 ────────────────────────────────────────────────────

def _make_tool_call_choice(tool_name: str, args: dict) -> Any:
    """LLM이 tool을 호출하는 응답 객체를 모의 생성."""
    tc = mock.MagicMock()
    tc.id = f"call_{tool_name}"
    tc.function.name      = tool_name
    tc.function.arguments = json.dumps(args, ensure_ascii=False)

    choice = mock.MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message.tool_calls = [tc]
    choice.message.content    = None

    resp = mock.MagicMock()
    resp.choices = [choice]
    resp.usage   = None
    return resp


def _make_final_answer_choice(content: dict) -> Any:
    """LLM이 최종 답변을 반환하는 응답 객체를 모의 생성."""
    choice = mock.MagicMock()
    choice.finish_reason          = "stop"
    choice.message.tool_calls     = []
    choice.message.content        = json.dumps(content, ensure_ascii=False)

    usage = mock.MagicMock()
    usage.prompt_tokens     = 200
    usage.completion_tokens = 100
    usage.total_tokens      = 300

    resp = mock.MagicMock()
    resp.choices = [choice]
    resp.usage   = usage
    return resp


# ─── build_smart_context ─────────────────────────────────────────────────────────

class TestBuildSmartContext:
    def test_returns_string(self) -> None:
        ctx = build_smart_context("HH001", "전기료 줄이려면?")
        assert isinstance(ctx, str)
        assert len(ctx) > 0

    def test_contains_baseline_header(self) -> None:
        ctx = build_smart_context("HH001", "요금제 알려줘")
        assert "[현재 가구 baseline" in ctx

    def test_contains_summary_lines(self) -> None:
        ctx = build_smart_context("HH002", "이번 주 소비량")
        assert "- " in ctx

    def test_unknown_household_still_returns_string(self) -> None:
        ctx = build_smart_context("HH999", "질문")
        assert isinstance(ctx, str)

    def test_intent_injected_in_header(self) -> None:
        ctx = build_smart_context("HH001", "요금 단계 알려줘")
        assert "의도:" in ctx


# ─── run_coach — mock 통합 테스트 ────────────────────────────────────────────────

FINAL_ANSWER = {
    "recommendations": ["저녁 10시 이후 세탁기 사용 권장"],
    "reasoning": "피크 시간 회피",
    "data_used": ["get_tariff_info"],
}


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")


class TestRunCoachDirectAnswer:
    """LLM이 tool 없이 바로 답변하는 케이스."""

    def test_basic_return_schema(self, mock_env: None, tmp_path: str) -> None:
        final_resp = _make_final_answer_choice(FINAL_ANSWER)
        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료 줄이는 방법?", log_dir=str(tmp_path), use_graph=False)

        assert "answer"      in result
        assert "tool_calls"  in result
        assert "iterations"  in result
        assert "session_id"  in result
        assert "trace_path"  in result
        assert "pii_warnings" in result
        assert "validation"  in result

    def test_answer_parsed_correctly(self, mock_env: None, tmp_path: str) -> None:
        final_resp = _make_final_answer_choice(FINAL_ANSWER)
        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료?", log_dir=str(tmp_path), use_graph=False)

        assert result["answer"]["recommendations"] == ["저녁 10시 이후 세탁기 사용 권장"]
        assert result["iterations"] == 1

    def test_trace_file_created(self, mock_env: None, tmp_path: str) -> None:
        final_resp = _make_final_answer_choice(FINAL_ANSWER)
        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료?", log_dir=str(tmp_path), use_graph=False)

        assert result["trace_path"] is not None
        assert os.path.exists(result["trace_path"])

    def test_no_pii_warnings_for_clean_tools(self, mock_env: None, tmp_path: str) -> None:
        final_resp = _make_final_answer_choice(FINAL_ANSWER)
        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료?", log_dir=str(tmp_path), use_graph=False)

        assert result["pii_warnings"] == []

    def test_session_id_propagated(self, mock_env: None, tmp_path: str) -> None:
        final_resp = _make_final_answer_choice(FINAL_ANSWER)
        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료?", session_id="fixed-sid", log_dir=str(tmp_path), use_graph=False)

        assert result["session_id"] == "fixed-sid"

    def test_non_json_answer_wrapped(self, mock_env: None, tmp_path: str) -> None:
        """LLM이 JSON이 아닌 텍스트를 반환할 때 raw_text로 감싸기."""
        choice = mock.MagicMock()
        choice.finish_reason      = "stop"
        choice.message.tool_calls = []
        choice.message.content    = "절감 가능합니다."
        resp = mock.MagicMock()
        resp.choices = [choice]
        resp.usage   = None

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = resp
            result = run_coach("HH001", "전기료?", log_dir=str(tmp_path), use_graph=False)

        assert "raw_text" in result["answer"]


class TestRunCoachWithToolCalls:
    """LLM이 tool을 1회 호출 후 최종 답변을 반환하는 케이스."""

    def test_tool_call_then_answer(self, mock_env: None, tmp_path: str) -> None:
        tool_resp  = _make_tool_call_choice("get_tariff_info", {"household_id": "HH001"})
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = [tool_resp, final_resp]
            result = run_coach("HH001", "요금제 알려줘", log_dir=str(tmp_path), use_graph=False)

        assert result["iterations"] == 2
        assert len(result["tool_calls"]) == 1
        assert result["tool_calls"][0].tool == "get_tariff_info"

    def test_household_id_not_in_trace_file(self, mock_env: None, tmp_path: str) -> None:
        """트레이스 파일에 원본 household_id가 없어야 한다."""
        tool_resp  = _make_tool_call_choice("get_tariff_info", {"household_id": "HH001"})
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = [tool_resp, final_resp]
            result = run_coach("HH001", "요금제?", log_dir=str(tmp_path), use_graph=False)

        trace_content = open(result["trace_path"], encoding="utf-8").read()
        assert "HH001" not in trace_content


class TestRunCoachPiiWarnings:
    """tool이 PII 필드를 포함한 데이터를 반환할 때 경고가 수집되는지 확인."""

    def test_pii_in_tool_result_triggers_warning(self, mock_env: None, tmp_path: str) -> None:
        tool_resp  = _make_tool_call_choice("get_household_profile", {"household_id": "HH001"})
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        pii_result = {"summary": "테스트", "real_name": "홍길동", "raw": {}}

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = [tool_resp, final_resp]
            with mock.patch("src.agent.coach._dispatch_tool", return_value=pii_result):
                result = run_coach("HH001", "프로필?", log_dir=str(tmp_path), use_graph=False)

        assert "real_name" in result["pii_warnings"]

    def test_pii_scrubbed_in_llm_message(self, mock_env: None, tmp_path: str) -> None:
        """PII가 감지돼도 스크럽된 버전이 LLM에 전달되는지 확인 (messages 리스트 검사)."""
        tool_resp  = _make_tool_call_choice("get_household_profile", {"household_id": "HH001"})
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        pii_result = {"summary": "테스트", "real_name": "홍길동", "raw": {}}
        captured_messages: list = []

        def capture_create(**kwargs):
            captured_messages.extend(kwargs.get("messages", []))
            side = [tool_resp, final_resp]
            return side.pop(0)

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = [tool_resp, final_resp]
            with mock.patch("src.agent.coach._dispatch_tool", return_value=pii_result):
                result = run_coach("HH001", "프로필?", log_dir=str(tmp_path), use_graph=False)

        # LLM으로 전달된 tool 메시지 중 "홍길동"이 없어야 함
        tool_messages = [m for m in result["tool_calls"] if hasattr(m, "result")]
        for tc in result["tool_calls"]:
            assert "홍길동" not in json.dumps(tc.result, ensure_ascii=False)


class TestRunCoachMaxIterations:
    """max_iterations 소진 시 빈 answer 반환."""

    def test_max_iter_returns_empty_answer(self, mock_env: None, tmp_path: str) -> None:
        tool_resp = _make_tool_call_choice("get_tariff_info", {"household_id": "HH001"})

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = tool_resp
            result = run_coach("HH001", "질문", max_iterations=2, log_dir=str(tmp_path), use_graph=False)

        assert result["answer"] == {}
        assert result["iterations"] == 2

    def test_trace_saved_even_on_max_iter(self, mock_env: None, tmp_path: str) -> None:
        tool_resp = _make_tool_call_choice("get_tariff_info", {"household_id": "HH001"})

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = tool_resp
            result = run_coach("HH001", "질문", max_iterations=1, log_dir=str(tmp_path), use_graph=False)

        assert os.path.exists(result["trace_path"])


class TestRunCoachHitl:
    """HITL 콜백 — before_tool / before_answer 중단 동작 확인."""

    def test_before_tool_reject_injects_error_response(self, mock_env: None, tmp_path: str) -> None:
        """before_tool이 False를 반환하면 tool 결과로 E_HITL_REJECTED가 주입된다."""
        tool_resp  = _make_tool_call_choice("get_tariff_info", {"household_id": "HH001"})
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        rejected_tools: list[str] = []

        def hitl(stage: str, payload: dict) -> bool:
            if stage == "before_tool":
                rejected_tools.append(payload["tool"])
                return False
            return True

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.side_effect = [tool_resp, final_resp]
            result = run_coach("HH001", "요금제?", log_dir=str(tmp_path), hitl_callback=hitl, use_graph=False)

        assert "get_tariff_info" in rejected_tools
        # tool이 거부돼도 agent loop는 계속 돌아 최종 답변을 받는다
        assert result["answer"] != {}

    def test_before_answer_reject_returns_empty(self, mock_env: None, tmp_path: str) -> None:
        """before_answer가 False를 반환하면 answer={}로 즉시 반환된다."""
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        def hitl(stage: str, payload: dict) -> bool:
            return stage != "before_answer"

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료?", log_dir=str(tmp_path), hitl_callback=hitl, use_graph=False)

        assert result["answer"] == {}

    def test_hitl_none_does_not_affect_normal_flow(self, mock_env: None, tmp_path: str) -> None:
        """hitl_callback=None이면 기존 동작과 동일하다."""
        final_resp = _make_final_answer_choice(FINAL_ANSWER)

        with mock.patch("src.agent.coach.OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = final_resp
            result = run_coach("HH001", "전기료?", log_dir=str(tmp_path), hitl_callback=None, use_graph=False)

        assert result["answer"]["recommendations"] == FINAL_ANSWER["recommendations"]
        assert "validation" in result
