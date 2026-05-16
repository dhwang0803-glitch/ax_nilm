import datetime
import logging
import os
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

from src.agent.data_tools import get_anomaly_events, get_anomaly_log
from src.agent.schemas import InsightsLLMOutput
from src.agent.multi_agent import run_multi_agent
from src.agent.multi_agent.supervisor import get_pending_review, resume_multi_agent

router = APIRouter()

_SEVERITY_MAP = {
    "critical": "high",
    "error":    "high",
    "warning":  "medium",
    "warn":     "medium",
    "info":     "low",
    "low":      "low",
    "medium":   "medium",
    "high":     "high",
}

# ── 인메모리 캐시 (TTL 1시간) ─────────────────────────────────────

_cache: dict[str, tuple[float, InsightsLLMOutput]] = {}
_CACHE_TTL = 3600


def _get_cached(hh: str) -> InsightsLLMOutput | None:
    entry = _cache.get(hh)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _set_cache(hh: str, result: InsightsLLMOutput) -> None:
    _cache[hh] = (time.time(), result)



def get_or_run_insights(hh: str) -> InsightsLLMOutput | None:
    """캐시에서 읽거나 없으면 멀티에이전트 호출 후 저장.

    고위험 이상 이벤트로 HITL 중단 시 None 반환 (pending 상태).
    savings_krw는 supervisor 내부에서 이미 처리됨.
    """
    cached = _get_cached(hh)
    if cached is None:
        cached = run_multi_agent(hh)
        if cached is not None:
            _set_cache(hh, cached)
    return cached


# ── 주간 추이 빌드 ────────────────────────────────────────────────

_DAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _weekly_trend(log_records: list[dict]) -> list[dict]:
    counts: dict[str, int] = defaultdict(int)
    for r in log_records:
        day = r.get("detected_at", "")[:10]
        if day:
            counts[day] += 1

    today = datetime.date(2026, 4, 30)
    trend = []
    for i in range(6, -1, -1):
        d = today - datetime.timedelta(days=i)
        trend.append({
            "date": str(d),
            "day": _DAYS[d.weekday()],
            "count": counts.get(str(d), 0),
        })
    return trend


# ── 엔드포인트 ────────────────────────────────────────────────────

@router.get("/insights/summary")
def insights_summary():
    hh = os.getenv("DEFAULT_HH", "HH001")

    events_data = get_anomaly_events(hh, status="active")
    log_data    = get_anomaly_log(hh)

    raw_events = events_data.get("raw", [])
    raw_log    = log_data.get("raw", [])

    confidence = max((e.get("confidence", 0) for e in raw_events), default=0)

    result = get_or_run_insights(hh)
    if result is None:
        pending = get_pending_review(hh) or {}
        raise HTTPException(
            status_code=202,
            detail={
                "status":  "pending_review",
                "message": pending.get("interrupt_data", {}).get("message", "인간 검토 대기 중"),
                "anomaly_events": pending.get("interrupt_data", {}).get("anomaly_events", []),
            },
        )
    diag_map = {d.event_id: d for d in result.anomaly_diagnoses}

    anomaly_highlights = [
        {
            "id":             e.get("event_id", f"evt-{i}"),
            "appliance":      e.get("appliance", e.get("appliance_name", "알 수 없음")),
            "severity":       _SEVERITY_MAP.get(e.get("severity", "info"), "low"),
            "headline":       diag_map[e["event_id"]].diagnosis if e.get("event_id") in diag_map else e.get("description", ""),
            "recommendation": diag_map[e["event_id"]].action    if e.get("event_id") in diag_map else "점검 필요",
            "detectedAt":     e.get("detected_at", ""),
        }
        for i, e in enumerate(raw_events)
    ]

    recs_out = [
        {
            "id":                 f"rec-{i}",
            "appliance":          "",
            "action":             r.title,
            "estimatedSavingKrw": r.savings_krw,
            "confidence":         round(confidence, 2),
        }
        for i, r in enumerate(result.recommendations)
    ]

    weekly_raw   = _weekly_trend(raw_log)
    weekly_trend = [
        {
            "weekLabel":          w["day"],
            "diagnosisCount":     w["count"],
            "estimatedSavingKrw": 0,
        }
        for w in weekly_raw
    ]

    monthly_saving_krw = sum(r.savings_krw for r in result.recommendations)
    weekly_count       = sum(w["count"] for w in weekly_raw)

    return {
        "generatedAt":      datetime.datetime.now().isoformat(),
        "modelVersion":     "v2.4",
        "sampleHouseholds": 79,
        "kpi": {
            "weeklyDiagnosisCount":      weekly_count,
            "weeklyDiagnosisDelta":      0,
            "monthlyEstimatedSavingKrw": monthly_saving_krw,
            "monthlySavingDelta":        0,
            "modelConfidence":           round(confidence, 2),
        },
        "anomalyHighlights": anomaly_highlights,
        "recommendations":   recs_out,
        "weeklyTrend":       weekly_trend,
    }


# ── HITL 검토 승인/거부 ──────────────────────────────────────────────

class ReviewDecision(BaseModel):
    approved: bool
    note: str = ""


@router.delete("/insights/cache")
def clear_insights_cache():
    """개발용: 인메모리 인사이트 캐시를 즉시 비움."""
    if os.getenv("ENV", "production") not in ("development", "dev", "local"):
        raise HTTPException(status_code=403, detail="개발 환경에서만 사용 가능합니다.")
    _cache.clear()
    return {"cleared": True}


@router.post("/insights/review")
def insights_review(body: ReviewDecision):
    """보류 중인 이상 이벤트 검토 결과를 제출해 그래프를 재개한다.

    approved=true  → report 생성 계속 진행
    approved=false → 관리자 에스컬레이션 기록 후 report 생략
    """
    hh = os.getenv("DEFAULT_HH", "HH001")

    if not get_pending_review(hh):
        raise HTTPException(status_code=404, detail=f"보류 중인 검토 없음: {hh}")

    decision = {"approved": body.approved, "auto": False, "note": body.note}
    result = resume_multi_agent(hh, decision)
    _set_cache(hh, result)

    return {"status": "resumed", "approved": body.approved}
