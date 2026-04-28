"""단위 테스트 — data_tools.py 8개 도구 schema 검증.

각 도구 호출이 {"summary": str, "raw": ...} 또는 {"error": str, "code": str}을 반환하는지 확인.
mock 데이터 범위 안의 정상 케이스와 unknown household_id 오류 케이스 모두 검증.
"""
import pytest

from src.agent.data_tools import (
    get_consumption_breakdown,
    get_consumption_hourly,
    get_consumption_summary,
    get_dr_events,
    get_forecast,
    get_household_profile,
    get_tariff_info,
    get_weather,
)

# ─── 공통 헬퍼 ─────────────────────────────────────────────────────────────────

def _assert_success(result: dict) -> None:
    assert "summary" in result, f"'summary' 키 없음: {result}"
    assert "raw" in result,     f"'raw' 키 없음: {result}"
    assert isinstance(result["summary"], str), "summary가 str이 아님"
    assert result["summary"], "summary가 빈 문자열"


def _assert_error(result: dict) -> None:
    assert "error" in result, f"'error' 키 없음: {result}"
    assert "code"  in result, f"'code' 키 없음: {result}"
    assert isinstance(result["error"], str)
    assert isinstance(result["code"],  str)


# ─── get_household_profile ──────────────────────────────────────────────────────

class TestGetHouseholdProfile:
    @pytest.mark.parametrize("hid", ["HH001", "HH002", "HH003"])
    def test_success(self, hid: str) -> None:
        result = get_household_profile(hid)
        _assert_success(result)
        raw = result["raw"]
        assert "house_type" in raw
        assert "area_m2"    in raw
        assert "members"    in raw
        assert "appliances" in raw
        assert isinstance(raw["appliances"], list)
        assert len(raw["appliances"]) > 0

    def test_unknown_household(self) -> None:
        result = get_household_profile("HH999")
        _assert_error(result)
        assert result["code"] == "E_NOT_FOUND"


# ─── get_weather ────────────────────────────────────────────────────────────────

class TestGetWeather:
    def test_success(self) -> None:
        result = get_weather(["2026-04-21", "2026-04-27"], "서울")
        _assert_success(result)
        assert isinstance(result["raw"], list)
        assert len(result["raw"]) == 7
        for row in result["raw"]:
            assert "date" in row
            assert "tavg" in row
            assert "rain_mm" in row

    def test_no_data_outside_range(self) -> None:
        result = get_weather(["2025-01-01", "2025-01-07"], "서울")
        _assert_error(result)
        assert result["code"] == "E_NO_DATA"

    def test_unknown_location_falls_back_to_seoul(self) -> None:
        result = get_weather(["2026-04-21", "2026-04-27"], "부산")
        _assert_success(result)


# ─── get_forecast ───────────────────────────────────────────────────────────────

class TestGetForecast:
    def test_default_7days(self) -> None:
        result = get_forecast()
        _assert_success(result)
        assert isinstance(result["raw"], list)
        assert len(result["raw"]) == 7

    def test_3days(self) -> None:
        result = get_forecast(days_ahead=3)
        _assert_success(result)
        assert len(result["raw"]) == 3

    def test_unknown_location_falls_back(self) -> None:
        result = get_forecast(location="광주")
        _assert_success(result)


# ─── get_consumption_summary ────────────────────────────────────────────────────

class TestGetConsumptionSummary:
    @pytest.mark.parametrize("hid", ["HH001", "HH002", "HH003"])
    def test_success(self, hid: str) -> None:
        result = get_consumption_summary(hid)
        _assert_success(result)
        raw = result["raw"]
        assert "total_kwh"     in raw
        assert "daily_avg_kwh" in raw
        assert "peak_hours"    in raw
        assert isinstance(raw["peak_hours"], list)

    def test_unknown_household(self) -> None:
        result = get_consumption_summary("HH999")
        _assert_error(result)
        assert result["code"] == "E_NOT_FOUND"


# ─── get_consumption_hourly ─────────────────────────────────────────────────────

class TestGetConsumptionHourly:
    @pytest.mark.parametrize("hid", ["HH001", "HH002", "HH003"])
    def test_success(self, hid: str) -> None:
        result = get_consumption_hourly(hid, "2026-04-27")
        _assert_success(result)
        raw = result["raw"]
        assert isinstance(raw, list)
        assert len(raw) == 24
        for row in raw:
            assert "hour" in row
            assert "kwh"  in row
            assert 0 <= row["hour"] <= 23
            assert row["kwh"] >= 0

    def test_unknown_household(self) -> None:
        result = get_consumption_hourly("HHXXX")
        _assert_error(result)
        assert result["code"] == "E_NOT_FOUND"


# ─── get_consumption_breakdown ──────────────────────────────────────────────────

class TestGetConsumptionBreakdown:
    @pytest.mark.parametrize("hid", ["HH001", "HH002", "HH003"])
    def test_success(self, hid: str) -> None:
        result = get_consumption_breakdown(hid, "2026-04-27")
        _assert_success(result)
        raw = result["raw"]
        assert isinstance(raw, list)
        for item in raw:
            assert "appliance"        in item
            assert "kwh"              in item
            assert "share_pct"        in item
            assert "active_intervals" in item
            assert isinstance(item["active_intervals"], list)

    def test_share_pct_sums_to_100(self) -> None:
        result = get_consumption_breakdown("HH001")
        total  = sum(item["share_pct"] for item in result["raw"])
        assert abs(total - 100.0) < 0.5, f"share_pct 합계 {total:.1f}%"

    def test_unknown_household(self) -> None:
        result = get_consumption_breakdown("HH999")
        _assert_error(result)


# ─── get_dr_events ──────────────────────────────────────────────────────────────

class TestGetDrEvents:
    def test_events_in_range(self) -> None:
        result = get_dr_events(["2026-04-20", "2026-04-30"], "서울")
        _assert_success(result)
        assert isinstance(result["raw"], list)
        assert len(result["raw"]) > 0
        for evt in result["raw"]:
            assert "event_id"   in evt
            assert "date"       in evt
            assert "start_time" in evt
            assert "status"     in evt

    def test_no_events(self) -> None:
        result = get_dr_events(["2025-01-01", "2025-01-31"], "서울")
        _assert_success(result)
        assert result["raw"] == []

    def test_unknown_region_falls_back(self) -> None:
        result = get_dr_events(["2026-04-20", "2026-04-30"], "제주")
        _assert_success(result)

    def test_future_event_status(self) -> None:
        result  = get_dr_events(["2026-04-28", "2026-04-30"], "서울")
        statuses = [e["status"] for e in result["raw"]]
        assert "예정" in statuses


# ─── get_tariff_info ────────────────────────────────────────────────────────────

class TestGetTariffInfo:
    @pytest.mark.parametrize("hid,expected_tier", [
        ("HH001", 3),
        ("HH002", 1),
        ("HH003", 2),
    ])
    def test_success(self, hid: str, expected_tier: int) -> None:
        result = get_tariff_info(hid)
        _assert_success(result)
        raw = result["raw"]
        assert "plan"                       in raw
        assert "current_tier"               in raw
        assert "current_month_kwh"          in raw
        assert "kwh_to_next_tier"           in raw
        assert "estimated_monthly_bill_krw" in raw
        assert raw["current_tier"] == expected_tier

    def test_unknown_household(self) -> None:
        result = get_tariff_info("HH999")
        _assert_error(result)
        assert result["code"] == "E_NOT_FOUND"
