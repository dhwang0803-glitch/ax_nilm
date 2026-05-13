"""LangSmith 멀티에이전트 평가 스크립트.

사용법:
    python scripts/evaluate_agent.py
    python scripts/evaluate_agent.py --experiment "rag-node-v2"

평가 대상: run_multi_agent() (nilm_monitor + cashback + rag_retriever + report)
평가 항목 (규칙 기반):
  - schema_valid        : 출력 스키마 필드 존재 여부
  - rec_count           : 권고 3~5개 범위
  - savings_range       : savings_kwh 0.1~10.0 범위 준수
  - field_length        : title ≤30자, action ≤15자, diagnosis ≤100자
  - safety              : 필수 가전 사용 중단 / 금지 표현 부재
  - cashback_compliance : 캐시백 단계 요율·조건 일치 여부
  - rec_uniqueness      : 동일 기기명 중복 권고 탐지
  - seasonal_alignment  : 기온 기준 냉·난방 가전 권고 방향 일치
  - anomaly_coverage    : 이상 이벤트 대비 진단 커버리지 비율
평가 항목 (LLM judge):
  - rec_relevance       : NILM top_consumers ↔ 권고 논리적 연결
  - rag_faithfulness    : RAG 청크 ↔ 진단·권고 내용 일치 여부
  - llm_quality         : 진단·권고 실용성 종합
평가 항목 (메트릭):
  - latency             : 그래프 실행 지연 시간 (SLA 30s)
  - cost_estimate       : 가구당 LLM 비용 추정 (원)
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parents[1] / "config" / ".env")


# ── 데이터셋 ──────────────────────────────────────────────────────────────────

DATASET_NAME = "ax_nilm-multi-agent-eval"

TEST_CASES = [{"household_id": f"HH{n:03d}"} for n in range(1, 51)]


# ── 평가 대상 함수 ─────────────────────────────────────────────────────────────

def target(inputs: dict) -> dict:
    """그래프를 직접 invoke해 중간 상태(_nilm_output 등)도 함께 반환한다."""
    import time
    from datetime import date, timedelta
    from src.agent.multi_agent.supervisor import _get_graph
    from src.agent.multi_agent.cashback_node import cashback_unit_rate
    from src.agent.schemas import InsightsLLMOutput
    from src.agent.data_tools import get_weather

    hh = inputs["household_id"]

    # 토큰 추적 (langchain_community 없으면 무시)
    try:
        from langchain_community.callbacks import get_openai_callback
        _has_cb = True
    except ImportError:
        _has_cb = False

    t0 = time.time()
    if _has_cb:
        with get_openai_callback() as _cb:
            result = _get_graph().invoke({
                "household_id":    hh,
                "nilm_output":     {},
                "cashback_output": {},
                "rag_context":     [],
                "final_output":    {},
            })
        token_count = _cb.total_tokens
        cost_usd    = _cb.total_cost
    else:
        result = _get_graph().invoke({
            "household_id":    hh,
            "nilm_output":     {},
            "cashback_output": {},
            "rag_context":     [],
            "final_output":    {},
        })
        token_count = None
        cost_usd    = None
    latency_ms = int((time.time() - t0) * 1000)

    final = result.get("final_output") or {}
    output = InsightsLLMOutput(**final)

    unit_rate = cashback_unit_rate(hh)
    for rec in output.recommendations:
        rec.savings_krw = round(rec.savings_kwh * unit_rate)

    today = date.today()
    date_range = [(today - timedelta(days=7)).isoformat(), today.isoformat()]
    weather_raw = get_weather(date_range).get("raw", [])

    out = output.model_dump()
    # 언더스코어 prefix: 중간 상태 (평가자용, LangSmith UI에는 표시되나 주요 지표 아님)
    out["_nilm_output"]     = result.get("nilm_output") or {}
    out["_cashback_output"] = result.get("cashback_output") or {}
    out["_rag_context"]     = result.get("rag_context") or []
    out["_weather"]         = weather_raw
    out["_latency_ms"]      = latency_ms
    out["_token_count"]     = token_count
    out["_cost_usd"]        = cost_usd
    return out


# ── 규칙 기반 평가자 ──────────────────────────────────────────────────────────

def schema_valid(outputs: dict, **kwargs) -> dict:
    ok = (
        "anomaly_diagnoses" in outputs
        and "recommendations" in outputs
        and isinstance(outputs["recommendations"], list)
    )
    return {"key": "schema_valid", "score": int(ok)}


def rec_count(outputs: dict, **kwargs) -> dict:
    recs = outputs.get("recommendations", [])
    ok = 3 <= len(recs) <= 5
    return {"key": "rec_count", "score": int(ok), "comment": f"{len(recs)}개"}


def savings_range(outputs: dict, **kwargs) -> dict:
    recs = outputs.get("recommendations", [])
    violations = [r for r in recs if not (0.1 <= r.get("savings_kwh", 0) <= 10.0)]
    ok = len(violations) == 0
    return {"key": "savings_range", "score": int(ok),
            "comment": f"위반 {len(violations)}건" if violations else "전체 통과"}


def field_length(outputs: dict, **kwargs) -> dict:
    recs  = outputs.get("recommendations", [])
    diags = outputs.get("anomaly_diagnoses", [])
    violations = []
    for r in recs:
        if len(r.get("title", "")) > 30:
            violations.append(f"title 초과: {r['title'][:20]}…")
        if len(r.get("action", "")) > 15:
            violations.append(f"action 초과: {r['action']}")
    for d in diags:
        if len(d.get("diagnosis", "")) > 100:
            violations.append(f"diagnosis 초과: {d['diagnosis'][:30]}…")
    ok = len(violations) == 0
    return {"key": "field_length", "score": int(ok),
            "comment": "; ".join(violations) if violations else "전체 통과"}


# 사용 중단·금지 표현 (action·title 공통)
_STOP_PHRASES = [
    "사용 중단", "사용하지 마", "끄세요", "꺼두세요", "미사용 권고",
    "사용 금지", "작동 중지", "전원 끄기",
]
# 상시 가동 필수 가전 — 어떤 중단 표현도 허용하지 않음
_ESSENTIAL_APPLIANCES = ["냉장고", "김치냉장고", "의료기기", "산소발생기"]
_ESSENTIAL_STOP = ["중단", "차단", "꺼", "끄", "미사용"]


def safety(outputs: dict, **kwargs) -> dict:
    """필수 가전 사용 중단 / 금지 표현 부재 확인."""
    recs = outputs.get("recommendations", [])
    violations = []

    for r in recs:
        title  = r.get("title", "")
        action = r.get("action", "")
        text   = title + " " + action

        # 전역 금지 표현
        for phrase in _STOP_PHRASES:
            if phrase in text:
                violations.append(f"금지 표현 '{phrase}': {action or title}")
                break

        # 필수 가전 + 중단 표현 조합
        for appliance in _ESSENTIAL_APPLIANCES:
            if appliance in text:
                for stop in _ESSENTIAL_STOP:
                    if stop in action:
                        violations.append(f"필수 가전 중단 권고: {appliance} / {action}")
                        break

    ok = len(violations) == 0
    return {"key": "safety", "score": int(ok),
            "comment": "; ".join(violations) if violations else "전체 통과"}


# 캐시백 요율 단계 (cashback_node.py 와 동기화 필요)
_CASHBACK_TIERS: list[tuple[float, float]] = [
    (0.20, 100.0),
    (0.10,  80.0),
    (0.05,  60.0),
    (0.03,  30.0),
]


def cashback_compliance(outputs: dict, **kwargs) -> dict:
    """캐시백 계산이 단계 요율표를 준수하는지 검증.

    enrolled는 프로그램 가입 여부(DB 값)이며 savings_rate와 독립적.
    검증 대상: cashback_rate_krw_per_kwh 요율 일치 + projected_cashback_krw 정산액 정합성.
    """
    cb = outputs.get("_cashback_output", {})
    if not cb:
        return {"key": "cashback_compliance", "score": 0,
                "comment": "_cashback_output 없음"}

    violations = []
    savings_rate  = cb.get("savings_rate", 0.0)
    rate_per_kwh  = cb.get("cashback_rate_krw_per_kwh", 0.0)
    projected_krw = cb.get("projected_cashback_krw", 0)
    baseline_kwh  = cb.get("baseline_kwh", 0.0)

    # 단계 요율 확인
    expected_rate = 0.0
    for threshold, rate in _CASHBACK_TIERS:
        if savings_rate >= threshold:
            expected_rate = rate
            break

    if abs(rate_per_kwh - expected_rate) > 0.01:
        violations.append(
            f"요율 불일치: savings_rate={savings_rate:.1%}, "
            f"expected={expected_rate}원/kWh, actual={rate_per_kwh}원/kWh"
        )

    # 정산액 확인 (effective_savings = baseline * min(savings_rate, 30%), int 절사)
    effective    = baseline_kwh * min(savings_rate, 0.30)
    expected_krw = int(effective * expected_rate)
    if projected_krw != expected_krw:
        violations.append(
            f"정산액 불일치: expected={expected_krw}원, actual={projected_krw}원"
        )

    ok = len(violations) == 0
    return {"key": "cashback_compliance", "score": int(ok),
            "comment": "; ".join(violations) if violations else "전체 통과"}


# ── LLM-as-judge 평가자 ───────────────────────────────────────────────────────

_JUDGE_PROMPT = """\
당신은 한국 가정 에너지 절감 전문가입니다.
아래 멀티에이전트 출력을 평가하고 1~5점으로 점수를 매기세요.

## 평가 기준
- 권고가 구체적이고 실행 가능한가 (시간대·기기명·수치 포함)
- 이상 진단이 원인을 명확히 설명하는가
- 가전 교체·구매 같은 금지 권고가 없는가
- 중복 없이 다양한 시간대·기기를 다루는가

## 출력
{output}

점수(1~5)와 한 줄 근거만 답하세요. 형식: "점수: N | 근거: ..."
"""

_RELEVANCE_PROMPT = """\
당신은 한국 가정 에너지 분석 전문가입니다.
NILM 분석 결과(top_consumers)와 절감 권고(recommendations)의 논리적 연결을 평가하세요.

## NILM top_consumers (일일 소비량 상위 기기)
{top_consumers}

## 권고 목록
{recommendations}

## 평가 기준
- 권고 기기가 top_consumers에서 도출되었는가
- daily_kwh가 높은 기기를 우선 다루는가
- 소비량이 낮은(0.1 kWh 미만) 기기를 제외했는가

점수(1~5)와 한 줄 근거만 답하세요. 형식: "점수: N | 근거: ..."
"""

_FAITHFULNESS_PROMPT = """\
당신은 RAG 기반 리포트 품질 검증 전문가입니다.
검색된 RAG 청크와 최종 리포트(진단·권고)의 내용 일치를 평가하세요.

## RAG 검색 청크
{rag_chunks}

## 최종 리포트 (진단 + 권고)
{report}

## 평가 기준
- 리포트가 RAG 청크의 사실(기준·수치·제도)을 왜곡하지 않는가
- RAG 청크에 없는 내용을 근거인 것처럼 주장하지 않는가

점수(1~5)와 한 줄 근거만 답하세요. 형식: "점수: N | 근거: ..."
"""


def _call_judge(prompt: str) -> tuple[float, str]:
    import re
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=100,
    )
    text = resp.choices[0].message.content or ""
    match = re.search(r"점수\s*:\s*([1-5])", text)
    score = int(match.group(1)) / 5.0 if match else 0.5
    return score, text.strip()


def llm_quality(outputs: dict, **kwargs) -> dict:
    # 중간 상태 키 제거 후 판단 (노이즈 방지)
    clean = {k: v for k, v in outputs.items() if not k.startswith("_")}
    score, text = _call_judge(_JUDGE_PROMPT.format(output=str(clean)))
    return {"key": "llm_quality", "score": score, "comment": text}


def rec_relevance(outputs: dict, **kwargs) -> dict:
    """NILM top_consumers ↔ 권고 논리적 연결 (LLM judge)."""
    nilm = outputs.get("_nilm_output", {})
    top_consumers = nilm.get("top_consumers", [])
    recs = outputs.get("recommendations", [])

    if not top_consumers:
        return {"key": "rec_relevance", "score": 0.5,
                "comment": "top_consumers 없음 — 중립"}

    prompt = _RELEVANCE_PROMPT.format(
        top_consumers=str(top_consumers),
        recommendations=str(recs),
    )
    score, text = _call_judge(prompt)
    return {"key": "rec_relevance", "score": score, "comment": text}


def rag_faithfulness(outputs: dict, **kwargs) -> dict:
    """RAG 청크 ↔ 진단·권고 내용 일치 여부 (LLM judge). 청크 없으면 중립."""
    rag_chunks = outputs.get("_rag_context", [])
    if not rag_chunks:
        return {"key": "rag_faithfulness", "score": 0.5,
                "comment": "RAG 청크 없음 — 중립"}

    report = {
        "anomaly_diagnoses": outputs.get("anomaly_diagnoses", []),
        "recommendations":   outputs.get("recommendations", []),
    }
    prompt = _FAITHFULNESS_PROMPT.format(
        rag_chunks="\n---\n".join(rag_chunks),
        report=str(report),
    )
    score, text = _call_judge(prompt)
    return {"key": "rag_faithfulness", "score": score, "comment": text}


# ── 추가 평가자 (품질·비용·안전) ──────────────────────────────────────────────

def rec_uniqueness(outputs: dict, **kwargs) -> dict:
    """동일 기기명 중복 권고 탐지 — top_consumers 기기명 기준."""
    recs = outputs.get("recommendations", [])
    nilm = outputs.get("_nilm_output", {})
    known = [tc["appliance"] for tc in nilm.get("top_consumers", [])]

    seen: dict[str, str] = {}
    violations: list[str] = []
    for r in recs:
        title = r.get("title", "")
        for app in known:
            if app in title:
                if app in seen:
                    violations.append(f"'{app}' 중복")
                else:
                    seen[app] = title

    ok = len(violations) == 0
    return {"key": "rec_uniqueness", "score": int(ok),
            "comment": "; ".join(dict.fromkeys(violations)) if violations else "전체 통과"}


# 기온 기준 냉·난방 방향 (report_agent 시스템 프롬프트와 동기화)
_COOLING_APPLIANCES = ["에어컨", "선풍기"]
_HEATING_APPLIANCES = ["전기장판", "온수매트", "전열기", "히터", "전기히터"]
_HOT_THRESHOLD  = 23.0   # °C 이상 → 여름
_COLD_THRESHOLD = 12.0   # °C 이하 → 겨울


def seasonal_alignment(outputs: dict, **kwargs) -> dict:
    """기온 기준 냉·난방 가전 권고 방향 일치 확인."""
    weather = outputs.get("_weather", [])
    recs    = outputs.get("recommendations", [])

    # _weather = list[{"date": ..., "tavg": float, ...}]
    temps = [d["tavg"] for d in weather if isinstance(d, dict) and "tavg" in d]
    if not temps:
        return {"key": "seasonal_alignment", "score": 0.5, "comment": "기온 데이터 없음 — 중립"}

    avg_t   = sum(temps) / len(temps)
    is_hot  = avg_t >= _HOT_THRESHOLD
    is_cold = avg_t <= _COLD_THRESHOLD

    violations: list[str] = []
    for r in recs:
        title = r.get("title", "")
        if is_cold:
            for app in _COOLING_APPLIANCES:
                if app in title:
                    violations.append(f"한랭({avg_t:.1f}°C)인데 냉방 기기 권고: {title}")
        if is_hot:
            for app in _HEATING_APPLIANCES:
                if app in title:
                    violations.append(f"온난({avg_t:.1f}°C)인데 난방 기기 권고: {title}")

    ok = len(violations) == 0
    return {"key": "seasonal_alignment", "score": int(ok),
            "comment": f"평균 {avg_t:.1f}°C; " + ("; ".join(violations) if violations else "전체 통과")}


def anomaly_coverage(outputs: dict, **kwargs) -> dict:
    """이상 이벤트 건수 대비 진단 커버리지 (0.0~1.0)."""
    nilm    = outputs.get("_nilm_output", {})
    events  = nilm.get("anomaly_events", [])
    diags   = outputs.get("anomaly_diagnoses", [])

    n_events = len(events)
    n_diags  = len(diags)

    if n_events == 0:
        return {"key": "anomaly_coverage", "score": 1.0, "comment": "이상 이벤트 없음"}

    score = round(min(n_diags, n_events) / n_events, 2)
    return {"key": "anomaly_coverage", "score": score,
            "comment": f"이벤트 {n_events}건 / 진단 {n_diags}건"}


_LATENCY_BUDGET_MS = 30_000   # 30초 SLA


def latency(outputs: dict, **kwargs) -> dict:
    """그래프 실행 지연 시간 (ms). 예산 30초 이하 = 1, 초과 = 0."""
    ms = outputs.get("_latency_ms")
    if ms is None:
        return {"key": "latency", "score": 0.5, "comment": "측정값 없음"}
    ok = ms <= _LATENCY_BUDGET_MS
    return {"key": "latency", "score": int(ok),
            "comment": f"{ms:,}ms ({'통과' if ok else f'예산 {_LATENCY_BUDGET_MS:,}ms 초과'})"}


_GPT4O_MINI_INPUT_USD_PER_TOK  = 0.15 / 1_000_000
_GPT4O_MINI_OUTPUT_USD_PER_TOK = 0.60 / 1_000_000
_USD_TO_KRW = 1_350


def cost_estimate(outputs: dict, **kwargs) -> dict:
    """가구당 LLM 실행 비용 추정 (원). token_count 있으면 실측, 없으면 자 기반 rough 추정."""
    token_count = outputs.get("_token_count")
    cost_usd    = outputs.get("_cost_usd")

    if cost_usd is not None:
        cost_krw = int(cost_usd * _USD_TO_KRW)
        return {"key": "cost_estimate", "score": cost_krw,
                "comment": f"실측 {token_count:,}tok → {cost_usd*100:.3f}¢ → {cost_krw}원"}

    # fallback: 출력 문자 수 × 2 ≈ 토큰 (한국어), 입력:출력 ≈ 3:1 가정
    clean = {k: v for k, v in outputs.items() if not k.startswith("_")}
    out_tok = len(str(clean)) * 2
    in_tok  = out_tok * 3
    cost_usd_est = in_tok * _GPT4O_MINI_INPUT_USD_PER_TOK + out_tok * _GPT4O_MINI_OUTPUT_USD_PER_TOK
    cost_krw = int(cost_usd_est * _USD_TO_KRW)
    return {"key": "cost_estimate", "score": cost_krw,
            "comment": f"추정 {in_tok + out_tok:,}tok → {cost_usd_est*100:.3f}¢ → {cost_krw}원"}


# ── 실행 ──────────────────────────────────────────────────────────────────────

_EVALUATORS = [
    schema_valid,
    rec_count,
    savings_range,
    field_length,
    safety,
    cashback_compliance,
    rec_uniqueness,
    seasonal_alignment,
    anomaly_coverage,
    rec_relevance,
    rag_faithfulness,
    llm_quality,
    latency,
    cost_estimate,
]


def main(experiment_prefix: str) -> None:
    from langsmith import Client
    from langsmith.evaluation import evaluate

    client = Client()

    # 데이터셋 생성 (없으면 신규, 있으면 누락 가구만 추가)
    if not client.has_dataset(dataset_name=DATASET_NAME):
        dataset = client.create_dataset(DATASET_NAME,
                                        description="멀티에이전트 평가 — HH001~HH050")
        client.create_examples(inputs=TEST_CASES, dataset_id=dataset.id)
        print(f"데이터셋 생성: {DATASET_NAME} ({len(TEST_CASES)}가구)")
    else:
        dataset = client.read_dataset(dataset_name=DATASET_NAME)
        existing = list(client.list_examples(dataset_id=dataset.id))
        existing_ids = {e.inputs["household_id"] for e in existing}
        missing = [tc for tc in TEST_CASES if tc["household_id"] not in existing_ids]
        if missing:
            client.create_examples(inputs=missing, dataset_id=dataset.id)
            print(f"기존 데이터셋에 {len(missing)}가구 추가: {DATASET_NAME}")
        else:
            print(f"기존 데이터셋 사용: {DATASET_NAME} ({len(existing)}가구)")

    results = evaluate(
        target,
        data=DATASET_NAME,
        evaluators=_EVALUATORS,
        experiment_prefix=experiment_prefix,
        max_concurrency=1,  # API rate limit 방지
    )

    print("\n=== 평가 결과 ===")
    for r in results:
        hh  = r["run"].inputs.get("household_id", "?")
        evs = {e.key: e.score for e in r["evaluation_results"]["results"]}
        print(f"{hh}: {evs}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", default="multi-agent",
                        help="LangSmith 실험 이름 prefix")
    args = parser.parse_args()
    main(args.experiment)
