"""단위 테스트 — anonymizer.py (scrub_tool_output + validate_no_pii)."""
import pytest

from src.agent.anonymizer import scrub_tool_output, validate_no_pii


# ─── scrub_tool_output ──────────────────────────────────────────────────────────

class TestScrubToolOutput:
    def test_no_pii_passthrough(self) -> None:
        data = {"summary": "4인 가구", "raw": {"area_m2": 85, "members": 4}}
        result = scrub_tool_output(data)
        assert result == data

    def test_top_level_pii_redacted(self) -> None:
        data = {"real_name": "홍길동", "summary": "가구 정보"}
        result = scrub_tool_output(data)
        assert result["real_name"] == "[REDACTED]"
        assert result["summary"] == "가구 정보"

    def test_nested_pii_redacted(self) -> None:
        data = {"raw": {"owner_name": "이순신", "area_m2": 85}}
        result = scrub_tool_output(data)
        assert result["raw"]["owner_name"] == "[REDACTED]"
        assert result["raw"]["area_m2"] == 85

    def test_pii_in_list_redacted(self) -> None:
        data = {"members": [{"email": "test@test.com", "role": "head"}]}
        result = scrub_tool_output(data)
        assert result["members"][0]["email"] == "[REDACTED]"
        assert result["members"][0]["role"] == "head"

    def test_multiple_pii_fields(self) -> None:
        data = {
            "real_name": "홍길동",
            "phone": "010-1234-5678",
            "address": "서울시 강남구",
            "area_m2": 85,
        }
        result = scrub_tool_output(data)
        assert result["real_name"] == "[REDACTED]"
        assert result["phone"]     == "[REDACTED]"
        assert result["address"]   == "[REDACTED]"
        assert result["area_m2"]   == 85

    def test_does_not_mutate_original(self) -> None:
        data = {"real_name": "홍길동", "summary": "test"}
        original_name = data["real_name"]
        scrub_tool_output(data)
        assert data["real_name"] == original_name  # 원본 불변

    def test_appliance_name_not_redacted(self) -> None:
        """'name' 필드는 PII가 아님 — 가전 이름 등에 사용."""
        data = {"raw": [{"name": "에어컨", "kwh": 12.3}]}
        result = scrub_tool_output(data)
        assert result["raw"][0]["name"] == "에어컨"

    def test_all_known_pii_fields(self) -> None:
        pii_fields = [
            "real_name", "owner_name", "address", "real_address",
            "phone", "phone_number", "mobile", "email",
            "resident_id", "resident_number", "ssn",
            "birth_date", "birthday", "passport_no",
        ]
        data = {f: f"value_{f}" for f in pii_fields}
        result = scrub_tool_output(data)
        for f in pii_fields:
            assert result[f] == "[REDACTED]", f"{f} 필드가 스크럽되지 않음"

    def test_empty_dict(self) -> None:
        assert scrub_tool_output({}) == {}

    def test_nested_empty(self) -> None:
        assert scrub_tool_output({"raw": {}}) == {"raw": {}}


# ─── validate_no_pii ────────────────────────────────────────────────────────────

class TestValidateNoPii:
    def test_clean_data_returns_empty(self) -> None:
        data = {"summary": "가구 정보", "raw": {"area_m2": 85}}
        assert validate_no_pii(data) == []

    def test_detects_top_level_pii(self) -> None:
        data = {"real_name": "홍길동", "summary": "test"}
        found = validate_no_pii(data)
        assert "real_name" in found

    def test_detects_nested_pii(self) -> None:
        data = {"raw": {"email": "x@x.com"}}
        found = validate_no_pii(data)
        assert "email" in found

    def test_detects_pii_in_list(self) -> None:
        data = {"items": [{"phone": "010-0000-0000"}]}
        found = validate_no_pii(data)
        assert "phone" in found

    def test_multiple_pii_all_reported(self) -> None:
        data = {"real_name": "A", "phone": "B", "area_m2": 85}
        found = validate_no_pii(data)
        assert "real_name" in found
        assert "phone"     in found

    def test_appliance_name_not_flagged(self) -> None:
        data = {"raw": [{"name": "에어컨"}]}
        assert validate_no_pii(data) == []

    def test_empty_dict_clean(self) -> None:
        assert validate_no_pii({}) == []
