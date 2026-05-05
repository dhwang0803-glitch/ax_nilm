"""컨텍스트 엔지니어링 전/후 토큰 사용량 비교.

Naive  : 모든 데이터를 한 번에 텍스트로 덤프 → LLM 단일 호출
Engineered : 현재 tool-use ReAct 에이전트

실행:
    cd kpx-integration-settlement
    python scripts/compare_tokens.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# .env 로드
for line in (Path(__file__).parent.parent / "config" / ".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from src.agent.data_tools import (
    get_anomaly_events,
    get_anomaly_log,
    get_cashback_history,
    get_consumption_summary,
    get_forecast,
    get_hourly_appliance_breakdown,
    get_tariff_info,
    get_weather,
)
from src.agent.graph import run_graph

HOUSEHOLD_ID = "HH001"
QUESTION = "이번 주 전기료 어떻게 줄여?"


def _extract_tokens(response) -> dict[str, int]:
    usage = {}
    for src in (
        getattr(response, "usage_metadata", None) or {},
        (getattr(response, "response_metadata", None) or {}).get("token_usage", {}),
    ):
        for k, v in src.items():
            if isinstance(v, int):
                usage[k] = usage.get(k, 0) + v
    return usage


def run_naive() -> dict[str, int]:
    """모든 데이터를 텍스트로 덤프 후 단일 LLM 호출."""
    data = {
        "consumption":  get_consumption_summary(HOUSEHOLD_ID),
        "hourly":       get_hourly_appliance_breakdown(HOUSEHOLD_ID),
        "weather":      get_weather(HOUSEHOLD_ID),
        "forecast":     get_forecast(),
        "cashback":     get_cashback_history(HOUSEHOLD_ID),
        "tariff":       get_tariff_info(HOUSEHOLD_ID),
        "anomaly_now":  get_anomaly_events(HOUSEHOLD_ID),
        "anomaly_log":  get_anomaly_log(HOUSEHOLD_ID),
    }
    data_text = json.dumps(data, ensure_ascii=False, indent=2)

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    response = llm.invoke([
        SystemMessage("당신은 가정 전력 절감 전문 코치입니다. 아래 데이터를 보고 절약 방법을 추천하세요."),
        HumanMessage(f"가구 데이터:\n{data_text}\n\n질문: {QUESTION}"),
    ])
    return _extract_tokens(response)


def run_engineered() -> dict[str, int]:
    """tool-use ReAct 에이전트 (현재 시스템)."""
    result = run_graph(HOUSEHOLD_ID, QUESTION)
    trace = json.loads(Path(result["trace_path"]).read_text(encoding="utf-8"))
    return trace["token_usage"]


def main() -> None:
    print("=" * 50)
    print("  컨텍스트 엔지니어링 전/후 토큰 비교")
    print("=" * 50)

    print("\n[1/2] Naive (전체 데이터 덤프) 실행 중...")
    naive = run_naive()

    print("[2/2] Engineered (tool-use ReAct) 실행 중...")
    engineered = run_engineered()

    input_before  = naive.get("input_tokens") or naive.get("prompt_tokens", 0)
    output_before = naive.get("output_tokens") or naive.get("completion_tokens", 0)
    total_before  = naive.get("total_tokens", input_before + output_before)

    input_after   = engineered.get("input_tokens") or engineered.get("prompt_tokens", 0)
    output_after  = engineered.get("output_tokens") or engineered.get("completion_tokens", 0)
    total_after   = engineered.get("total_tokens", input_after + output_after)

    saved = total_before - total_after
    rate  = saved / total_before * 100 if total_before else 0

    print()
    print(f"{'':30} {'Naive':>10} {'Engineered':>12} {'절감':>8}")
    print("-" * 62)
    print(f"{'입력 토큰 (input)':30} {input_before:>10,} {input_after:>12,} {input_before - input_after:>+8,}")
    print(f"{'출력 토큰 (output)':30} {output_before:>10,} {output_after:>12,} {output_before - output_after:>+8,}")
    print(f"{'합계 (total)':30} {total_before:>10,} {total_after:>12,} {saved:>+8,}")
    print("-" * 62)
    print(f"{'절감률':30} {'':>10} {'':>12} {rate:>7.1f}%")
    print()


if __name__ == "__main__":
    main()
