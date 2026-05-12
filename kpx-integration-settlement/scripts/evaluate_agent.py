"""LangSmith 멀티에이전트 평가 스크립트.

사용법:
    python scripts/evaluate_agent.py
    python scripts/evaluate_agent.py --experiment "rag-node-v2"

평가 대상: run_multi_agent() (nilm_monitor + cashback + rag_retriever + report)
평가 항목:
  - schema_valid        : 출력 스키마 필드 존재 여부
  - rec_count           : 권고 3~5개 범위
  - savings_range       : savings_kwh 0.1~10.0 범위 준수
  - field_length        : title ≤30자, action ≤15자, diagnosis ≤100자
  - safety              : 필수 가전 사용 중단 / 금지 표현 부재 (규칙)
  - cashback_compliance : 캐시백 단계 요율·조건 일치 여부 (규칙)
  - rec_relevance       : NILM top_consumers ↔ 권고 논리적 연결 (LLM judge)
  - rag_faithfulness    : RAG 청크 ↔ 진단·권고 내용 일치 여부 (LLM judge)
  - llm_quality         : LLM-as-judge (진단·권고 실용성)
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
    from src.agent.multi_agent.supervisor import _get_graph
    from src.agent.multi_agent.cashback_node import cashback_unit_rate
    from src.agent.schemas import InsightsLLMOutput

    hh = inputs["household_id"]
    result = _get_graph().invoke({
        "household_id":    hh,
        "nilm_output":     {},
        "cashback_output": {},
        "rag_context":     [],
        "final_output":    {},
    })

    final = result.get("final_output") or {}
    output = InsightsLLMOutput(**final)

    unit_rate = cashback_unit_rate(hh)
    for rec in output.recommendations:
        rec.savings_krw = round(rec.savings_kwh * unit_rate)

    out = output.model_dump()
    # 언더스코어 prefix: 중간 상태 (평가자용, LangSmith UI에는 표시되나 주요 지표 아님)
    out["_nilm_output"]     = result.get("nilm_output") or {}
    out["_cashback_output"] = result.get("cashback_output") or {}
    out["_rag_context"]     = result.get("rag_context") or []
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
    """캐시백 계산이 단계 요율표·가입 조건(3%)을 준수하는지 검증."""
    cb = outputs.get("_cashback_output", {})
    if not cb:
        return {"key": "cashback_compliance", "score": 0,
                "comment": "_cashback_output 없음"}

    violations = []
    savings_rate       = cb.get("savings_rate", 0.0)
    enrolled           = cb.get("enrolled", False)
    rate_per_kwh       = cb.get("cashback_rate_krw_per_kwh", 0.0)
    projected_krw      = cb.get("projected_cashback_krw", 0)
    baseline_kwh       = cb.get("baseline_kwh", 0.0)

    # 가입 조건: savings_rate ≥ 3%
    should_enroll = savings_rate >= 0.03
    if enrolled != should_enroll:
        violations.append(
            f"enrolled 불일치: savings_rate={savings_rate:.1%}, enrolled={enrolled}"
        )

    if should_enroll:
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

        # 정산액 확인 (effective_savings = baseline * min(rate, 30%), int 절사)
        effective = baseline_kwh * min(savings_rate, 0.30)
        expected_krw = int(effective * expected_rate)
        if projected_krw != expected_krw:
            violations.append(
                f"정산액 불일치: expected={expected_krw}원, actual={projected_krw}원"
            )
    else:
        # 미가입 → 정산 0
        if projected_krw != 0:
            violations.append(
                f"미가입인데 projected_cashback_krw={projected_krw}원"
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


# ── 실행 ──────────────────────────────────────────────────────────────────────

_EVALUATORS = [
    schema_valid,
    rec_count,
    savings_range,
    field_length,
    safety,
    cashback_compliance,
    rec_relevance,
    rag_faithfulness,
    llm_quality,
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
