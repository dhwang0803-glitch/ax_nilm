"""단위 테스트 — trace_logger.py (TraceLogger)."""
import json
import os
import tempfile

import pytest

from src.agent.trace_logger import TraceLogger


@pytest.fixture
def tmp_log_dir(tmp_path):
    return str(tmp_path / "traces")


@pytest.fixture
def logger(tmp_log_dir):
    return TraceLogger(
        session_id="test-session-001",
        household_token="HH-test001",
        log_dir=tmp_log_dir,
    )


# ─── log_tool_call ──────────────────────────────────────────────────────────────

class TestLogToolCall:
    def test_records_tool_call(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_tariff_info", {"household_id": "HH001"}, {"summary": "test"})
        assert logger.tool_call_count == 1
        assert logger.tools_used == ["get_tariff_info"]

    def test_household_id_replaced_with_token(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_tariff_info", {"household_id": "HH001"}, {"summary": "ok"})
        entry = logger._tool_calls[0]
        assert entry.inputs.get("household_id") == "HH-test001"
        assert "HH001" not in str(entry.inputs)

    def test_non_household_inputs_preserved(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_weather", {"date_range": ["2026-04-21", "2026-04-27"], "location": "서울"}, {})
        entry = logger._tool_calls[0]
        assert entry.inputs["location"] == "서울"
        assert entry.inputs["date_range"] == ["2026-04-21", "2026-04-27"]

    def test_multiple_calls_accumulated(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_household_profile", {"household_id": "HH001"}, {})
        logger.log_tool_call("get_weather", {"date_range": ["2026-04-27", "2026-04-27"]}, {})
        assert logger.tool_call_count == 2
        assert logger.tools_used == ["get_household_profile", "get_weather"]

    def test_result_stored_correctly(self, logger: TraceLogger) -> None:
        result = {"summary": "3단계", "raw": {"current_tier": 3}}
        logger.log_tool_call("get_tariff_info", {"household_id": "HH001"}, result)
        assert logger._tool_calls[0].result == result


# ─── save / load ────────────────────────────────────────────────────────────────

class TestSaveLoad:
    def test_save_creates_file(self, logger: TraceLogger, tmp_log_dir: str) -> None:
        logger.log_final_answer({"recommendations": []})
        path = logger.save()
        assert os.path.exists(path)
        assert path.endswith("test-session-001.json")

    def test_saved_json_structure(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_forecast", {"days_ahead": 3}, {"summary": "맑음"})
        logger.log_final_answer({"recommendations": ["에어컨 저녁 8시 이후 사용"]}, {"total_tokens": 512})
        path = logger.save()

        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        assert data["session_id"]      == "test-session-001"
        assert data["household_token"] == "HH-test001"
        assert "start_time"  in data
        assert "elapsed_sec" in data
        assert isinstance(data["elapsed_sec"], float)
        assert len(data["tool_calls"]) == 1
        assert data["tool_calls"][0]["tool"] == "get_forecast"
        assert data["final_answer"]["recommendations"] == ["에어컨 저녁 8시 이후 사용"]
        assert data["token_usage"]["total_tokens"] == 512

    def test_load_roundtrip(self, logger: TraceLogger) -> None:
        logger.log_final_answer({"raw_text": "절감 가능합니다."})
        path   = logger.save()
        loaded = TraceLogger.load(path)
        assert loaded["session_id"] == "test-session-001"
        assert loaded["final_answer"]["raw_text"] == "절감 가능합니다."

    def test_log_dir_created_if_missing(self, tmp_path: str) -> None:
        deep_dir = str(tmp_path / "a" / "b" / "c")
        logger = TraceLogger(session_id="x", household_token="T", log_dir=deep_dir)
        logger.log_final_answer({})
        path = logger.save()
        assert os.path.exists(path)

    def test_no_raw_household_id_in_file(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_tariff_info", {"household_id": "HH001"}, {"summary": "ok"})
        logger.log_final_answer({})
        path = logger.save()
        content = open(path, encoding="utf-8").read()
        assert "HH001" not in content

    def test_empty_trace_save(self, logger: TraceLogger) -> None:
        logger.log_final_answer({})
        path = logger.save()
        data = json.loads(open(path, encoding="utf-8").read())
        assert data["tool_calls"] == []
        assert data["final_answer"] == {}


# ─── properties ─────────────────────────────────────────────────────────────────

class TestProperties:
    def test_tool_call_count_empty(self, logger: TraceLogger) -> None:
        assert logger.tool_call_count == 0

    def test_tools_used_empty(self, logger: TraceLogger) -> None:
        assert logger.tools_used == []

    def test_tools_used_order(self, logger: TraceLogger) -> None:
        logger.log_tool_call("get_household_profile", {}, {})
        logger.log_tool_call("get_consumption_summary", {}, {})
        logger.log_tool_call("get_tariff_info", {}, {})
        assert logger.tools_used == [
            "get_household_profile", "get_consumption_summary", "get_tariff_info"
        ]
