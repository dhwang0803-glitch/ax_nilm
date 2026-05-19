"""Evaluator-Optimizer — 최종 InsightsLLMOutput 품질 평가 + 재생성 트리거.

report_node 직후 실행. LLM이 final_output을 평가해 점수·이슈 목록을 반환.
- score ≥ THRESHOLD 또는 재시도 횟수 초과 → 승인 후 END
- 그 외 → state["evaluator_feedback"]에 이슈를 담아 report_node 재실행 (최대 1회)

코드 측 정규식 후처리(_strip_title 등)는 안전망으로 유지. evaluator는 그 위 레이어.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ── 임계값 ────────────────────────────────────────────────────────────────────

_QUALITY_THRESHOLD = 0.7
_MAX_RETRIES = 1


# ── 평가 출력 스키마 ──────────────────────────────────────────────────────────

_IssueField = Literal["diagnosis", "recommendation", "consistency", "duplication", "format"]


class _EvalIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: _IssueField
    detail: str = Field(max_length=120)


class _EvalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    score: float = Field(ge=0.0, le=1.0)
    issues: list[_EvalIssue] = Field(default_factory=list)
    summary: str = Field(default="", max_length=160)


_SYSTEM = """\
한국 가정 전력 인사이트 리포트 품질 평가자.
final_output(InsightsLLMOutput)을 받아 0.0~1.0 점수와 이슈 목록을 반환한다.

## 평가 기준 (위반 시 issues에 기록)

1. **금액 일관성** (consistency):
   recommendations[].savings_krw 값과 description 안 "N원" 문구가 일치해야 한다.
   불일치 1건당 -0.15.

2. **권고 제목 구체성** (recommendation):
   title이 "사용 시간 단축", "사용량 조절", "효율적 사용" 같은 일반 명사형이면 안 된다.
   "에어컨 1°C 상승", "보온 1시간 단축" 같은 구체 행동이어야 한다.
   위반 1건당 -0.15.

3. **가전 중복** (duplication):
   동일 가전이 recommendations 여러 항목의 title에 중복 등장하면 안 된다.
   중복 1쌍당 -0.20.

4. **진단 합리성** (diagnosis):
   anomaly_diagnoses[].category가 "이상"인데 expected_savings_krw_per_month=0이거나
   비현실적 금액(>50,000원)이면 문제.
   위반 1건당 -0.10.

5. **형식** (format):
   recommendations 개수가 3~5 범위를 벗어나면 -0.20.
   description이 빈 문자열이면 -0.05.

## 점수 산정
- 1.0에서 시작해 위 감점 누적.
- 0.7 이상: 통과.
- 0.5~0.7: 경미한 문제. 1회 재생성 가치 있음.
- 0.5 미만: 중대 문제. 재생성 강력 권장.

summary는 한 문장(120자 이내)으로 전반 평가.
"""


# ── 노드 함수 ────────────────────────────────────────────────────────────────

def evaluator_node(state: dict[str, Any]) -> dict[str, Any]:
    """final_output 품질 평가 + 재시도 결정."""
    final = state.get("final_output") or {}
    retry_count = int(state.get("evaluator_retry_count") or 0)

    # 빈 결과는 평가 건너뛰고 통과 — report_node fallback이 처리한 케이스
    if not final.get("recommendations"):
        return {
            "evaluator":             {"approved": True, "score": 0.0, "issues": [], "skipped": True},
            "evaluator_retry_count": retry_count,
            "evaluator_feedback":    [],
        }

    if not os.getenv("OPENAI_API_KEY"):
        return {
            "evaluator":             {"approved": True, "score": 0.0, "issues": [], "skipped": True},
            "evaluator_retry_count": retry_count,
            "evaluator_feedback":    [],
        }

    try:
        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        result: _EvalResult = (
            llm
            .with_structured_output(_EvalResult)
            .invoke([
                SystemMessage(_SYSTEM),
                HumanMessage(content=json.dumps(final, ensure_ascii=False)),
            ])
        )
    except Exception as e:
        logger.warning("evaluator 호출 실패 — 자동 승인: %s", e)
        return {
            "evaluator":             {"approved": True, "score": 0.0, "issues": [], "error": str(e)},
            "evaluator_retry_count": retry_count,
            "evaluator_feedback":    [],
        }

    score = result.score
    has_issues = score < _QUALITY_THRESHOLD
    retry_exhausted = retry_count >= _MAX_RETRIES
    approved = (not has_issues) or retry_exhausted

    feedback: list[str] = []
    if not approved:
        feedback = [f"[{i.field}] {i.detail}" for i in result.issues][:5]

    logger.info(
        "evaluator: score=%.2f approved=%s retry=%d issues=%d",
        score, approved, retry_count, len(result.issues),
    )

    return {
        "evaluator": {
            "approved": approved,
            "score":    score,
            "issues":   [i.model_dump() for i in result.issues],
            "summary":  result.summary,
        },
        "evaluator_retry_count": retry_count if approved else retry_count + 1,
        "evaluator_feedback":    feedback,
    }


# ── 조건부 라우팅 함수 ────────────────────────────────────────────────────────

def evaluator_route(state: dict[str, Any]) -> Literal["report", "__end__"]:
    """평가 결과에 따라 END 또는 report 재실행."""
    evaluator = state.get("evaluator") or {}
    if evaluator.get("approved", True):
        return "__end__"
    return "report"
