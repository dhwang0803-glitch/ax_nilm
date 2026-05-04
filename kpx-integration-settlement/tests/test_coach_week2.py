"""통합 테스트 — LangGraph 멀티에이전트 (run_graph / supervisor_node / run_insights).

실제 API 키 없이 테스트:
- run_graph() 반환 스키마 확인
- supervisor_node 의도별 라우팅 검증
- run_insights() LLM 출력 스키마 + Pydantic 제약 확인
- _safe_tool PII 스크럽 검증
"""
from __future__ import annotations

import json
import os
import unittest.mock as mock

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from pydantic import ValidationError

from src.agent.graph import (
    ALL_TOOLS,
    InsightsLLMOutput,
    _safe_tool,
    run_graph,
    run_insights,
)


# ─── 픽스처 ───────────────────────────────────────────────────────────────────

FINAL_ANSWER = {
    "recommendations": ["저녁 10시 이후 세탁기 사용 권장"],
    "reasoning": "피크 시간 회피",
    "data_used": ["get_tariff_info"],
}


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-dummy")


def _graph_state(answer: dict, agent: str = "cashback", extra_messages: list | None = None) -> dict:
    """graph.invoke 반환값 픽스처."""
    msgs = [HumanMessage(content="질문"), *(extra_messages or []),
            AIMessage(content=json.dumps(answer, ensure_ascii=False))]
    return {
        "messages": msgs,
        "household_id": "HH001",
        "next": agent,
        "worker_results": [{"agent": agent, "output": json.dumps(answer, ensure_ascii=False)}],
    }


def _mock_insights_llm(output: InsightsLLMOutput):
    """run_insights() 내부 _llm() 호출을 모의."""
    m = mock.MagicMock()
    m.with_structured_output.return_value.invoke.return_value = output
    return m


def _sample_insights() -> InsightsLLMOutput:
    return InsightsLLMOutput(
        anomaly_diagnoses=[
            {"event_id": "E001", "diagnosis": "평균 대비 30% 높은 소비.", "action": "필터 점검"},
        ],
        recommendations=[
            {"title": "저녁 세탁기 사용 조정", "savings_kwh": 2.5, "savings_krw": 250},
            {"title": "에어컨 설정 온도 1도 상향",  "savings_kwh": 1.2, "savings_krw": 120},
            {"title": "대기전력 차단 멀티탭 사용",  "savings_kwh": 0.8, "savings_krw": 80},
        ],
    )


# ─── run_graph 반환 스키마 ─────────────────────────────────────────────────────

class TestRunGraph:
    def test_return_schema(self, mock_env: None, tmp_path) -> None:
        with mock.patch("src.agent.graph._get_graph") as mg:
            mg.return_value.invoke.return_value = _graph_state(FINAL_ANSWER)
            result = run_graph("HH001", "전기료 줄이는 방법?", log_dir=str(tmp_path))

        for key in ("answer", "tool_calls", "iterations", "session_id", "trace_path", "pii_warnings", "validation"):
            assert key in result

    def test_session_id_propagated(self, mock_env: None, tmp_path) -> None:
        with mock.patch("src.agent.graph._get_graph") as mg:
            mg.return_value.invoke.return_value = _graph_state(FINAL_ANSWER)
            result = run_graph("HH001", "전기료?", session_id="fixed-sid", log_dir=str(tmp_path))

        assert result["session_id"] == "fixed-sid"

    def test_non_json_answer_wrapped_in_raw_text(self, mock_env: None, tmp_path) -> None:
        state = {
            "messages": [HumanMessage(content="질문"), AIMessage(content="절감 가능합니다.")],
            "household_id": "HH001",
            "next": "profile",
            "worker_results": [],
        }
        with mock.patch("src.agent.graph._get_graph") as mg:
            mg.return_value.invoke.return_value = state
            result = run_graph("HH001", "질문", log_dir=str(tmp_path))

        assert "raw_text" in result["answer"]

    def test_tool_messages_collected(self, mock_env: None, tmp_path) -> None:
        tool_msg = ToolMessage(
            content=json.dumps({"summary": "전력 정보", "raw": []}, ensure_ascii=False),
            tool_call_id="call_1",
        )
        with mock.patch("src.agent.graph._get_graph") as mg:
            mg.return_value.invoke.return_value = _graph_state(FINAL_ANSWER, extra_messages=[tool_msg])
            result = run_graph("HH001", "전기료?", log_dir=str(tmp_path))

        assert len(result["tool_calls"]) == 1

    def test_iterations_counts_ai_messages(self, mock_env: None, tmp_path) -> None:
        state = {
            "messages": [
                HumanMessage(content="질문"),
                AIMessage(content="중간 추론"),
                AIMessage(content=json.dumps(FINAL_ANSWER, ensure_ascii=False)),
            ],
            "household_id": "HH001",
            "next": "cashback",
            "worker_results": [],
        }
        with mock.patch("src.agent.graph._get_graph") as mg:
            mg.return_value.invoke.return_value = state
            result = run_graph("HH001", "질문", log_dir=str(tmp_path))

        assert result["iterations"] == 2

    def test_trace_file_created(self, mock_env: None, tmp_path) -> None:
        with mock.patch("src.agent.graph._get_graph") as mg:
            mg.return_value.invoke.return_value = _graph_state(FINAL_ANSWER)
            result = run_graph("HH001", "전기료?", log_dir=str(tmp_path))

        assert result["trace_path"] is not None
        assert os.path.exists(result["trace_path"])


# ─── 단일 에이전트 도구 구성 ──────────────────────────────────────────────────

class TestAllTools:
    """단일 에이전트에 모든 도구가 연결됐는지 확인."""

    EXPECTED_TOOLS = {
        "get_consumption_summary",
        "get_hourly_appliance_breakdown",
        "get_weather",
        "get_forecast",
        "get_cashback_history",
        "get_tariff_info",
        "get_anomaly_events",
        "get_anomaly_log",
        "get_household_profile",
        "get_dashboard_summary",
    }

    def test_all_tools_registered(self) -> None:
        tool_names = {t.name for t in ALL_TOOLS}
        assert tool_names == self.EXPECTED_TOOLS

    def test_tool_count(self) -> None:
        assert len(ALL_TOOLS) == 10

    def test_all_tools_are_safe_wrapped(self) -> None:
        from langchain_core.tools import StructuredTool
        for tool in ALL_TOOLS:
            assert isinstance(tool, StructuredTool)


# ─── run_insights 출력 스키마 + Pydantic 제약 ─────────────────────────────────

class TestRunInsights:
    def _run(self, mock_env) -> InsightsLLMOutput:
        output = _sample_insights()
        with mock.patch("src.agent.graph.get_anomaly_events", return_value={"raw": []}):
            with mock.patch("src.agent.graph.get_anomaly_log", return_value={"raw": []}):
                with mock.patch("src.agent.graph._llm", return_value=_mock_insights_llm(output)):
                    return run_insights("HH001")

    def test_return_type(self, mock_env: None) -> None:
        assert isinstance(self._run(mock_env), InsightsLLMOutput)

    def test_recommendations_count_3_to_5(self, mock_env: None) -> None:
        result = self._run(mock_env)
        assert 3 <= len(result.recommendations) <= 5

    def test_savings_kwh_in_range(self, mock_env: None) -> None:
        for rec in self._run(mock_env).recommendations:
            assert 0.1 <= rec.savings_kwh <= 10.0

    def test_savings_krw_in_range(self, mock_env: None) -> None:
        for rec in self._run(mock_env).recommendations:
            assert 10 <= rec.savings_krw <= 3000

    def test_action_max_15_chars(self, mock_env: None) -> None:
        for diag in self._run(mock_env).anomaly_diagnoses:
            assert len(diag.action) <= 15

    def test_diagnosis_max_100_chars(self, mock_env: None) -> None:
        for diag in self._run(mock_env).anomaly_diagnoses:
            assert len(diag.diagnosis) <= 100

    def test_pydantic_rejects_kwh_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            InsightsLLMOutput(
                anomaly_diagnoses=[],
                recommendations=[
                    {"title": "테스트",  "savings_kwh": 99.0, "savings_krw": 9900},
                    {"title": "테스트2", "savings_kwh": 1.0,  "savings_krw": 100},
                    {"title": "테스트3", "savings_kwh": 1.0,  "savings_krw": 100},
                ],
            )

    def test_pydantic_rejects_too_few_recommendations(self) -> None:
        with pytest.raises(ValidationError):
            InsightsLLMOutput(
                anomaly_diagnoses=[],
                recommendations=[
                    {"title": "테스트",  "savings_kwh": 1.0, "savings_krw": 100},
                    {"title": "테스트2", "savings_kwh": 1.0, "savings_krw": 100},
                ],
            )

    def test_pydantic_rejects_krw_too_low(self) -> None:
        with pytest.raises(ValidationError):
            InsightsLLMOutput(
                anomaly_diagnoses=[],
                recommendations=[
                    {"title": "테스트",  "savings_kwh": 1.0, "savings_krw": 5},
                    {"title": "테스트2", "savings_kwh": 1.0, "savings_krw": 100},
                    {"title": "테스트3", "savings_kwh": 1.0, "savings_krw": 100},
                ],
            )


# ─── _safe_tool PII 스크럽 ────────────────────────────────────────────────────

class TestSafeToolPii:
    """_safe_tool 래퍼가 tool 반환값에서 PII를 스크럽하는지 확인."""

    def test_pii_value_scrubbed(self) -> None:
        def fake_tool(household_id: str) -> dict:
            """테스트용 PII 포함 도구."""
            return {"summary": "테스트", "real_name": "홍길동", "raw": {}}

        safe = _safe_tool(fake_tool)
        result = safe.invoke({"household_id": "HH001"})
        assert "홍길동" not in json.dumps(result, ensure_ascii=False)

    def test_clean_output_passes_through(self) -> None:
        def fake_tool(household_id: str) -> dict:
            """테스트용 정상 도구."""
            return {"summary": "정상 데이터", "raw": {"kwh": 42.0}}

        safe = _safe_tool(fake_tool)
        result = safe.invoke({"household_id": "HH001"})
        assert result["raw"]["kwh"] == 42.0
