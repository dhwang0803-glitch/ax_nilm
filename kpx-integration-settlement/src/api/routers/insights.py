import datetime
import json
import logging
import os
import re
import time
from collections import defaultdict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


_mode_refs_cache: dict[str, tuple[float, dict]] = {}  # hh → (ts, mode_refs)
_MODE_REFS_TTL = 3600


def _get_mode_refs(hh: str) -> dict:
    entry = _mode_refs_cache.get(hh)
    if entry and time.time() - entry[0] < _MODE_REFS_TTL:
        return entry[1]
    from src.agent.data_tools import get_nilm_mode_references
    try:
        raw = (get_nilm_mode_references(hh).get("raw") or {}) if hh else {}
    except Exception as e:
        logger.warning("get_nilm_mode_references 실패 (hh=%s): %s", hh, e)
        raw = {}
    _mode_refs_cache[hh] = (time.time(), raw)
    return raw


def _quantify_headline(appliance: str, event: dict, mode_refs: dict) -> str | None:
    """anomaly_event 발생 시 일관된 정성 헤드라인 사용.

    "N배 이상" 같은 충격적 숫자는 사용자에게 불안만 유발 + 클램핑 부작용 노출.
    이상으로 분류된 항목엔 모두 "전력 사용이 평소보다 높게 감지됐어요" 통일.
    """
    if not appliance or not event:
        return None
    return f"{appliance} 전력 사용이 평소보다 높게 감지됐어요"


# NILM 기술 용어만 친화어로 — 일상어(보온·냉방·냉각·송풍 등)는 그대로 두어야 문장 자연스러움 유지.
# "{용어} 모드" / "{용어}" 양쪽 패턴 모두 매칭, 친화어로 치환할 때 "모드" 단어도 함께 제거.
_FRIENDLY_MODE_MAP: dict[str, str] = {
    "컴프레서 가동":   "자주 작동",
    "단속냉각":       "냉각 작동",
    "연속냉각":       "냉각 작동",
    "모터 동작":      "세탁·탈수",
    "히터 동작":      "건조·가열",
    "드럼회전":       "건조",
    "열풍건조":       "건조",
    "중온건조":       "건조",
    "고온건조":       "건조",
    "예비헹굼":       "헹굼",
    "중전력":         "중간 세기",
    "고전력":         "강하게",
    "저전력":         "약하게",
}
_FRIENDLY_MODE_PATTERN = re.compile(
    "(" + "|".join(re.escape(k) for k in sorted(_FRIENDLY_MODE_MAP.keys(), key=len, reverse=True)) + r")(\s*모드)?"
)


def _friendly_modes(text: str) -> str:
    """raw NILM 모드명을 친화어로 치환. '{용어} 모드' 패턴의 '모드' 단어도 함께 제거."""
    if not text:
        return text

    def _repl(m: re.Match) -> str:
        raw = m.group(1)
        return _FRIENDLY_MODE_MAP.get(raw, raw)

    return _FRIENDLY_MODE_PATTERN.sub(_repl, text)


def _humanize_kst(iso_str: str) -> str:
    """ISO 8601 (UTC) → KST 자연어. 예: '오늘 오후 9시', '어제', '3일 전'."""
    if not iso_str:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except ValueError:
        return iso_str
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    kst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
    delta_days = (now.date() - kst.date()).days
    if delta_days == 0:
        ampm = "오전" if kst.hour < 12 else "오후"
        hour12 = kst.hour if kst.hour <= 12 else kst.hour - 12
        if hour12 == 0:
            hour12 = 12
        return f"오늘 {ampm} {hour12}시"
    if delta_days == 1:
        return "어제"
    if 2 <= delta_days <= 6:
        return f"{delta_days}일 전"
    return f"{kst.month}월 {kst.day}일"

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
_anomaly_cache: dict[str, tuple[float, dict, dict]] = {}  # hh → (ts, events_data, log_data)
_CACHE_TTL = 3600

# ── 디스크 캐시 (영구화) ─────────────────────────────────────────
# 메모리 캐시는 백엔드 재시작 시 소실 → 매번 빈약한 LLM 호출 결과 노출 위험.
# 좋은 결과(highlight ≥ 2건)는 cache/insights_{hh}.json에 영구 저장 → 일관성 확보.
# 사용자가 ?refresh=true로 요청 시에만 새 호출 + 갱신.

_CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "cache")
_QUALITY_MIN_DIAGNOSES = 2  # 진단 N건 이상이어야 디스크에 저장


def _disk_cache_path(hh: str) -> str:
    return os.path.abspath(os.path.join(_CACHE_DIR, f"insights_{hh}.json"))


def _is_quality_result(result: InsightsLLMOutput) -> bool:
    """디스크 캐시 저장 자격 — 진단이 일정 수 이상 나와야 의미 있는 결과로 본다."""
    return result is not None and len(result.anomaly_diagnoses) >= _QUALITY_MIN_DIAGNOSES


def _load_disk_cache(hh: str) -> InsightsLLMOutput | None:
    path = _disk_cache_path(hh)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return InsightsLLMOutput.model_validate(data)
    except Exception as e:
        logger.warning("디스크 캐시 로드 실패 (%s): %s", path, e)
        return None


def _save_disk_cache(hh: str, result: InsightsLLMOutput) -> None:
    if not _is_quality_result(result):
        logger.info("품질 미달 — 디스크 캐시 저장 안 함 (hh=%s, diag=%d)",
                    hh, len(result.anomaly_diagnoses) if result else 0)
        return
    os.makedirs(_CACHE_DIR, exist_ok=True)
    path = _disk_cache_path(hh)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info("디스크 캐시 저장 완료: %s (diag=%d, recs=%d)",
                    path, len(result.anomaly_diagnoses), len(result.recommendations))
    except Exception as e:
        logger.warning("디스크 캐시 저장 실패 (%s): %s", path, e)


def _get_cached(hh: str) -> InsightsLLMOutput | None:
    entry = _cache.get(hh)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None


def _set_cache(hh: str, result: InsightsLLMOutput) -> None:
    _cache[hh] = (time.time(), result)


def _get_anomaly_cached(hh: str) -> tuple[dict, dict] | None:
    entry = _anomaly_cache.get(hh)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1], entry[2]
    return None


def _set_anomaly_cache(hh: str, events_data: dict, log_data: dict) -> None:
    _anomaly_cache[hh] = (time.time(), events_data, log_data)



def get_or_run_insights(hh: str, refresh: bool = False) -> InsightsLLMOutput | None:
    """캐시 우선순위: refresh=False면 메모리 → 디스크 → LLM. refresh=True면 LLM 강제 호출.

    좋은 결과(highlight≥2)는 디스크에 저장해 백엔드 재시작·시간 무관 일관 노출.
    """
    if not refresh:
        cached = _get_cached(hh)
        if cached is not None:
            return cached
        disk_cached = _load_disk_cache(hh)
        if disk_cached is not None:
            _set_cache(hh, disk_cached)  # 메모리에도 hydration
            return disk_cached

    new_result = run_multi_agent(hh)
    if new_result is not None:
        _set_cache(hh, new_result)
        # 새 호출 결과가 품질 기준 통과 + 기존 디스크 결과보다 풍부할 때만 디스크 갱신
        existing = _load_disk_cache(hh)
        if _is_quality_result(new_result):
            if existing is None or len(new_result.anomaly_diagnoses) >= len(existing.anomaly_diagnoses):
                _save_disk_cache(hh, new_result)
        elif refresh and existing is not None:
            # refresh 요청인데 새 결과가 빈약하면 기존 디스크 결과 반환 (사용자 화면 보호)
            logger.info("refresh 새 결과 빈약 — 기존 디스크 결과 유지 (hh=%s)", hh)
            _set_cache(hh, existing)
            return existing
    return new_result


# ── 주간 추이 빌드 ────────────────────────────────────────────────

_DAYS = ["월", "화", "수", "목", "금", "토", "일"]


def _anomaly_fallback_rec(e: dict) -> str:
    before = e.get("before_kw") or 0
    after = e.get("after_kw") or 0
    if before > 0 and after > before:
        pct = round((after / before - 1) * 100)
        return f"전주 대비 {pct}% 증가 — 점검 권장"
    sev = e.get("severity", "")
    if sev in ("critical", "error"):
        return "즉시 점검 필요"
    return "사용 이력 확인 권장"


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
def insights_summary(refresh: bool = False):
    """진단 요약 — 캐시 우선(메모리→디스크), refresh=true로 강제 새 분석."""
    hh = os.getenv("DEFAULT_HH", "HH001")

    anomaly_hit = _get_anomaly_cached(hh)
    if anomaly_hit:
        events_data, log_data = anomaly_hit
    else:
        events_data = get_anomaly_events(hh, status="active")
        log_data    = get_anomaly_log(hh)
        _set_anomaly_cache(hh, events_data, log_data)

    raw_events = events_data.get("raw", [])
    # 메인분전반·명시적 before_kw=0(평소 미사용 → 신규 사용)만 노출 제외.
    # before_kw 필드 자체가 없는 케이스(현재 _db_anomaly_events 출력엔 부재)는 통과.
    raw_events = [
        e for e in raw_events
        if "분전반" not in (e.get("appliance") or e.get("appliance_name") or "")
        and not ("before_kw" in e and (e.get("before_kw") or 0) == 0)
    ]
    raw_log    = log_data.get("raw", [])

    confidence = max((e.get("confidence", 0) for e in raw_events), default=0)

    result = get_or_run_insights(hh, refresh=refresh)
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
    raw_events_map = {e.get("event_id"): e for e in raw_events if e.get("event_id")}
    # LLM이 진단을 반환한 경우 — "정상"으로 판정해 diag_map에 없는 이벤트는 노출 제외.
    # LLM이 빈 배열을 반환한 경우 (fallback 등) — 분류 정보 없이 raw_events 전부 노출.
    use_llm_filter = bool(result.anomaly_diagnoses)

    mode_refs = _get_mode_refs(hh)

    def _diag_to_highlight(i: int, diag) -> dict | None:
        """진단 기준 → highlight. raw_event 있으면 정량 headline·detectedAt 보강, 없으면(WoW 합성) diag 자체에서 생성."""
        if diag.category == "정상":
            return None
        evt = raw_events_map.get(diag.event_id) or {}
        appliance = evt.get("appliance") or evt.get("appliance_name") or diag.diagnosis.split()[0]
        if "분전반" in appliance:
            return None
        quantified = _quantify_headline(appliance, evt, mode_refs) if evt else None
        headline = quantified or diag.diagnosis
        return {
            "id":         diag.event_id or f"diag-{i}",
            "appliance":  appliance,
            "severity":   _SEVERITY_MAP.get(evt.get("severity", "info"), "low") if evt else "low",
            "category":   diag.category,
            "headline":   headline,
            "cause":      "",  # 자세한 원인·확인 행동은 추천 조치 description에 노출 (중복 제거)
            "detectedAt": _humanize_kst(evt.get("detected_at", "")) if evt else "최근 7일",
        }

    if use_llm_filter:
        anomaly_highlights = [h for i, d in enumerate(result.anomaly_diagnoses) if (h := _diag_to_highlight(i, d)) is not None]
    else:
        # LLM이 빈 배열 → raw_events 전부 노출 (legacy 동작)
        def _evt_only_highlight(i: int, e: dict) -> dict | None:
            if "분전반" in e.get("appliance", e.get("appliance_name", "")):
                return None
            appliance = e.get("appliance", e.get("appliance_name", "알 수 없음"))
            quantified = _quantify_headline(appliance, e, mode_refs)
            headline = quantified or e.get("description") or f"{appliance} 전력 사용이 평소보다 늘어났어요"
            return {
                "id":         e.get("event_id", f"evt-{i}"),
                "appliance":  appliance,
                "severity":   _SEVERITY_MAP.get(e.get("severity", "info"), "low"),
                "category":   "이상",
                "headline":   headline,
                "cause":      "",
                "detectedAt": _humanize_kst(e.get("detected_at", "")),
            }
        anomaly_highlights = [h for i, e in enumerate(raw_events) if (h := _evt_only_highlight(i, e)) is not None]

    _SAVING_SUFFIX = re.compile(r"\s*월\s*기준\s*약\s*[\d,]+\s*원\s*절약(이\s*예상됩니다|할\s*수\s*있어요)\.?\s*$")

    def _to_saving_description(cause: str, action: str, savings_krw: int) -> str:
        """cause(원인 설명·확인 행동) + 절감 효과 1문장 결합 + 모드명 친화어 치환."""
        suffix = f"월 기준 약 {savings_krw:,}원 절약이 예상됩니다."
        if cause:
            base = _SAVING_SUFFIX.sub("", cause).strip().rstrip(".")
            return _friendly_modes(f"{base}. {suffix}")
        if not action:
            return suffix
        base = re.sub(r"\s*(권장|권고|권유|필요|좋을\s*것\s*같아요|있어요|보세요|해보세요)\s*$", "", action).strip()
        last = base[-1] if base else "고"
        josa = "을" if "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 else "를"
        return _friendly_modes(f"{base}{josa} 하시면 {suffix}")

    # 진단 기반 권고 — 진단 action + cause + expected_savings를 추천 조치 표로 통합 노출.
    appliance_in_recs: set[str] = set()
    diag_recs = []
    for i, h in enumerate(anomaly_highlights):
        diag = diag_map.get(h["id"])
        if diag is None or not diag.action:
            continue
        savings = diag.expected_savings_krw_per_month or 0
        if savings < 100:
            continue  # 100원 미만 권고는 사용자 체감 가치 낮음 — 제외
        app = h["appliance"]
        diag_recs.append({
            "id":                 f"diag-{i}",
            "appliance":          app,
            "action":             diag.action,
            "description":        _to_saving_description(diag.cause or "", diag.action, savings),
            "estimatedSavingKrw": savings,
            "confidence":         0.85,
        })
        appliance_in_recs.add(app)

    def _appliance_overlaps_title(app: str, title: str) -> bool:
        """가전명과 title의 토큰 단위 부분 일치 검사.

        예) "일반 냉장고" ↔ "냉장고 필터 점검" → True
            "전기장판/담요" ↔ "전기장판 사용 시간 단축" → True
        """
        if not app or not title:
            return False
        if app in title or title in app:
            return True
        # 토큰 분리 (공백·슬래시·콤마)
        tokens = [t for t in app.replace("/", " ").replace(",", " ").split() if len(t) >= 2]
        return any(tok in title for tok in tokens)

    general_recs = [
        {
            "id":                 f"rec-{i}",
            "appliance":          "",
            "action":             _friendly_modes(r.title),
            "description":        _friendly_modes(r.description),
            "estimatedSavingKrw": r.savings_krw,
            "confidence":         0.80,
        }
        for i, r in enumerate(result.recommendations)
        if not any(_appliance_overlaps_title(app, r.title) for app in appliance_in_recs)
    ]
    recs_out = diag_recs + general_recs

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
    _anomaly_cache.clear()
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
