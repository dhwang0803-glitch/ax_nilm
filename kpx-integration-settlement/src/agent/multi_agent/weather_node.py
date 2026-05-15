"""Module 6 — 날씨 조회 노드 (비LLM).

START에서 nilm_monitor·cashback과 동시에 fan-out 실행.
최근 7일 기상 데이터를 DB(household_daily_env)에서 읽어 state에 주입.
report 노드가 날씨 데이터를 직접 호출하지 않고 state에서 읽도록 분리.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from ..data_tools import get_weather


def weather_node(state: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    date_range = [(today - timedelta(days=7)).isoformat(), today.isoformat()]
    weather_data = get_weather(date_range)
    return {"weather_output": weather_data.get("raw", {})}
