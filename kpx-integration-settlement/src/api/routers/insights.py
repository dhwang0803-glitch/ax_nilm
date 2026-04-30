import datetime
import os
import time
from collections import defaultdict

from fastapi import APIRouter

from src.agent.data_tools import get_anomaly_events, get_anomaly_log
from src.agent.graph import AnomalyDiagnosis, InsightsLLMOutput, SavingsRec, run_insights

router = APIRouter()

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


# ── 폴백 (LLM 미사용 시) ─────────────────────────────────────────

def _fallback_diagnoses(events: list[dict]) -> list[dict]:
    return [
        {
            "event_id": e.get("event_id", ""),
            "diagnosis": e.get("description", ""),
            "action": "점검 필요",
        }
        for e in events
    ]


_FALLBACK_RECS = [
    {"title": "저녁 19–21시 대기전력 차단", "savings_kwh": 2.1, "savings_krw": 63},
    {"title": "대기전력 멀티탭 OFF",         "savings_kwh": 0.7, "savings_krw": 21},
    {"title": "에어컨 26 → 27°C",            "savings_kwh": 1.4, "savings_krw": 42},
]

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
    hh      = os.getenv("DEFAULT_HH", "HH001")
    use_llm = os.getenv("INSIGHTS_LLM", "false").lower() == "true"

    events_data = get_anomaly_events(hh, status="active")
    log_data    = get_anomaly_log(hh)

    raw_events = events_data.get("raw", [])
    raw_log    = log_data.get("raw", [])

    total_kwh  = round(sum(e.get("excess_kwh", 0) for e in raw_events), 1)
    confidence = max((e.get("confidence", 0) for e in raw_events), default=0)

    if use_llm and os.getenv("OPENAI_API_KEY"):
        cached = _get_cached(hh)
        if cached is None:
            cached = run_insights(hh)
            _set_cache(hh, cached)
        diagnoses       = [d.model_dump() for d in cached.anomaly_diagnoses]
        recommendations = [r.model_dump() for r in cached.recommendations]
    else:
        diagnoses       = _fallback_diagnoses(raw_events)
        recommendations = _FALLBACK_RECS

    diag_map  = {d["event_id"]: d for d in diagnoses}
    anomalies = [
        {
            **e,
            "diagnosis": diag_map.get(e["event_id"], {}).get("diagnosis", e.get("description", "")),
            "action":    diag_map.get(e["event_id"], {}).get("action", "점검 필요"),
        }
        for e in raw_events
    ]

    return {
        "summary": {
            "totalAnomalies":  len(raw_events),
            "anomalyKwh":      total_kwh,
            "modelConfidence": round(confidence * 100),
        },
        "anomalies":       anomalies,
        "recommendations": recommendations,
        "weeklyTrend":     _weekly_trend(raw_log),
    }
