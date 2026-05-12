"""LangSmith 멀티에이전트 평가 스크립트.

사용법:
    python scripts/evaluate_agent.py
    python scripts/evaluate_agent.py --experiment "rag-node-v2"

평가 대상: run_multi_agent() (nilm_monitor + cashback + rag_retriever + report)
평가 항목:
  - schema_valid   : 출력 스키마 필드 존재 여부
  - rec_count      : 권고 3~5개 범위
  - savings_range  : savings_kwh 0.1~10.0 범위 준수
  - field_length   : title ≤30자, action ≤15자, diagnosis ≤100자
  - llm_quality    : LLM-as-judge (진단·권고 실용성)
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
    from src.agent.multi_agent import run_multi_agent
    result = run_multi_agent(inputs["household_id"])
    return result.model_dump()


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

def llm_quality(outputs: dict, **kwargs) -> dict:
    import re
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    prompt = _JUDGE_PROMPT.format(output=str(outputs))
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=100,
    )
    text = resp.choices[0].message.content or ""
    match = re.search(r"점수\s*:\s*([1-5])", text)
    score = int(match.group(1)) / 5.0 if match else 0.5
    return {"key": "llm_quality", "score": score, "comment": text.strip()}


# ── 실행 ──────────────────────────────────────────────────────────────────────

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
        evaluators=[schema_valid, rec_count, savings_range, field_length, llm_quality],
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
