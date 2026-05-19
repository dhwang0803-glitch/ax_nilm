"""Module 5 — AI 진단 리포트 에이전트.

Module 2(NILM 모니터링) + Module 3(캐시백 계산) 결과를 받아
이상 진단 + 절감 권고를 최종 생성한다. LLM은 structured_output만 사용.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from pydantic import BaseModel, ConfigDict, Field

from ..schemas import AnomalyDiagnosis, InsightsLLMOutput, SavingsRec
from .. import ontology


# ── 분할 호출 전용 스키마 ─────────────────────────────────────────────────────
# 한 호출에 진단+권고를 모두 담으면 OpenAI strict JSON schema의 한국어 escape로
# completion 토큰이 폭증한다. 둘로 분할 호출해 각 응답 부피를 절반으로 줄임.

class _DiagnosisOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    anomaly_diagnoses: list[AnomalyDiagnosis]


class _RecommendationsOnly(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recommendations: list[SavingsRec] = Field(min_length=3, max_length=5)


# ── 페이로드 슬림 ──────────────────────────────────────────────────────────────

_RECENT_EVENT_FIELDS = ("appliance", "mode", "energy_wh", "duration_min", "peak_w", "avg_w", "started_at")
_RECENT_EVENT_CAP = 12
_ANOMALY_EVENT_CAP = 6
_MODE_FIELDS_KEEP = ("avg_energy_wh", "avg_duration_min", "sample_count", "low_confidence", "duration_threshold_min")


def _slim_nilm_output(nilm: dict[str, Any]) -> dict[str, Any]:
    """LLM에 넘어가는 nilm payload를 의미 있는 부분만 남기고 축소.

    mode_references는 anomaly_flags / top_consumers에 등장하는 가전만 유지.
    recent_events·anomaly_events는 캡 + 핵심 필드만.
    """
    if not nilm:
        return {}

    top_consumers = nilm.get("top_consumers") or []
    peak_hours    = nilm.get("peak_hours") or []
    anomaly_flags = nilm.get("anomaly_flags") or []

    relevant_apps: set[str] = {f.get("appliance", "") for f in anomaly_flags}
    relevant_apps.update(tc.get("appliance", "") for tc in top_consumers)
    relevant_apps.discard("")

    mode_refs_full = nilm.get("mode_references") or {}
    mode_refs_slim: dict[str, Any] = {}
    if isinstance(mode_refs_full, dict):
        for app, ref in mode_refs_full.items():
            if app not in relevant_apps:
                continue
            modes_in = ref.get("modes", {}) or {}
            modes_out = {
                m: {k: v for k, v in data.items() if k in _MODE_FIELDS_KEEP}
                for m, data in modes_in.items()
            }
            mode_refs_slim[app] = {"type": ref.get("type"), "modes": modes_out}

    recent_in = nilm.get("recent_events") or []
    recent_slim = [
        {k: e.get(k) for k in _RECENT_EVENT_FIELDS if k in e}
        for e in recent_in if e.get("appliance") in relevant_apps
    ][:_RECENT_EVENT_CAP]

    anomaly_events = (nilm.get("anomaly_events") or [])[:_ANOMALY_EVENT_CAP]

    return {
        "top_consumers":   top_consumers,
        "peak_hours":      peak_hours,
        "anomaly_flags":   anomaly_flags,
        "anomaly_events":  anomaly_events,
        "mode_references": mode_refs_slim,
        "recent_events":   recent_slim,
        "appliance_wow":   nilm.get("appliance_wow") or [],
    }


# ── 폴백 출력 ──────────────────────────────────────────────────────────────────

def _build_fallback(nilm_output: dict[str, Any]) -> dict[str, Any]:
    """LLM 실패 시 top_consumers 기반으로 최소 유효 출력 생성 (schema min_length=3 충족)."""
    top = [tc for tc in (nilm_output.get("top_consumers") or []) if tc.get("daily_kwh", 0) >= 0.01][:3]
    while len(top) < 3:
        top.append({"appliance": "기타", "daily_kwh": 0.5})
    recs = []
    for tc in top[:3]:
        app = tc.get("appliance") or "기타"
        kwh = max(0.01, min(10.0, round(float(tc.get("daily_kwh") or 0.5) * 0.075 * 30, 2)))
        recs.append({
            "title": f"{app} 사용 점검",
            "savings_kwh": kwh,
            "savings_krw": 0,
            "description": "AI 진단 일시 오류 — 일반 권고만 표시됩니다. 잠시 후 다시 시도해주세요.",
        })
    return {"anomaly_diagnoses": [], "recommendations": recs}


# ── 진단 후처리 ────────────────────────────────────────────────────────────────

_USAGE_CHANGE_SINGLE_EVENT_THRESHOLD = 1  # 같은 가전·모드 recent_events가 이 이하면 단발 — 사용변화 우선


# 가전 매칭 실패 fallback 시 유형별로 cause·action 문구를 분기.
# 사용자에게 "평소와 다른 패턴이 있는지 확인하세요" 같은 자가진단 숙제를 떠넘기지 않고,
# 유형이 알려주는 가전별 구체 확인 행동을 제시한다.
_FALLBACK_BY_TYPE: dict[str, dict[str, str]] = {
    "A": {  # 상시 가동: 컴프레서·문 패킹 등 성능 신호
        "cause":  "{app} 전력 사용이 평소보다 늘었어요. 문이 잘 닫히는지, 뒤쪽에 먼지가 쌓여 있지 않은지 확인해 보세요.",
        "hint":   "문이 잘 닫히는지, 뒤쪽에 먼지가 쌓여 있지 않은지 확인해 보세요.",
        "action": "{app} 문 닫힘과 뒤쪽 먼지 확인",
    },
    "B": {  # 다단계 사이클: 한 사이클이 한 단위 — 양·횟수가 핵심
        "cause":  "{app} 사용이 평소보다 늘었어요. 한 번에 처리하는 양이 평소보다 적지는 않은지, 여러 번 나눠 돌리는 대신 모아서 한 번에 쓸 수 있는지 확인해 보세요.",
        "hint":   "한 번에 처리하는 양이 적지는 않은지, 여러 번 나눠 돌리는 대신 모아서 한 번에 쓸 수 있는지 확인해 보세요.",
        "action": "{app} 사이클 횟수 점검",
    },
    "C": {  # 단발 사용
        "cause":  "{app}을(를) 평소보다 자주 사용한 것으로 보여요. 짧은 시간 여러 번 쓰기보다 한 번에 모아서 쓰면 전기료를 줄일 수 있어요.",
        "hint":   "짧은 시간 여러 번 쓰기보다 한 번에 모아서 쓰면 전기료를 줄일 수 있어요.",
        "action": "{app} 사용 빈도 확인",
    },
    "D": {  # 장시간 세션: 시간은 사용자 선택 — 정보성 안내
        "cause":  "{app} 사용 시간이 평소보다 늘었어요. 의도하신 사용이라면 그대로 두셔도 되고, 가동 시간을 30분~1시간만 줄여도 전기료가 줄어요.",
        "hint":   "의도하신 사용이라면 그대로 두셔도 되고, 가동 시간을 30분~1시간만 줄여도 전기료가 줄어요.",
        "action": "{app} 사용 시간 점검",
    },
}


def _fallback_diagnosis_text(app: str, atype: str, mode: str = "") -> tuple[str, str, str]:
    """가전 매칭 실패 시 유형별 fallback (diagnosis, cause, action) 반환."""
    tpl = _FALLBACK_BY_TYPE.get(atype) or _FALLBACK_BY_TYPE["C"]
    diag = f"{app} 사용이 평소보다 늘어났어요"
    cause = tpl["cause"].format(app=app)
    action = tpl["action"].format(app=app)
    if mode and atype in ("C", "D"):
        diag = f"{app} {mode} 사용이 늘었어요"
    return diag, cause, action


# ── WoW 트랙 → 합성 diagnosis ───────────────────────────────────────────────
# 코드에서 직접 생성 (LLM 우회). 같은 가전이 LLM 진단(피크/에너지이상)에 이미 잡혔으면 스킵.

_WOW_SAVINGS_RATE = 0.30  # "사용변화" 절감 잠재 — 사용자가 30% 줄였을 때


def _build_wow_diagnoses(appliance_wow: list[dict], existing_apps: set[str], unit_krw: int) -> list[dict]:
    """appliance_wow 목록 → AnomalyDiagnosis dict 목록 (category='사용변화').

    cause는 "지난주 대비 N% 증가 사실 + 유형별 확인 행동(hint)" 2단 구성.
    Fallback 템플릿의 cause(전체 문장)는 LLM 우회 경로에 중복이라 hint만 사용.
    """
    out: list[dict] = []
    for item in appliance_wow or []:
        app = item.get("appliance") or ""
        if not app or app in existing_apps:
            continue
        atype = item.get("type") or ontology.appliance_type(app)
        cur_kwh = float(item.get("this_week_daily_kwh") or 0)
        wow_pct = float(item.get("wow_pct") or 0)

        tpl = _FALLBACK_BY_TYPE.get(atype) or _FALLBACK_BY_TYPE["C"]
        diag = f"{app} 사용이 평소보다 늘어났어요"
        cause = f"지난주 같은 요일보다 약 {int(round(wow_pct))}% 늘었어요. " + tpl["hint"]
        action = tpl["action"].format(app=app)

        savings = int(cur_kwh * _WOW_SAVINGS_RATE * 30 * unit_krw)
        out.append({
            "event_id": f"wow:{app}",
            "category": "사용변화",
            "diagnosis": diag,
            "cause": cause[:160],
            "action": action,
            "expected_savings_krw_per_month": max(0, savings),
        })
    return out

# baseline 자체가 작은 경우(GCS sample 부족 가구) 비율이 폭주 → 사용자에 보일 땐 클램핑.
_MULTIPLIER_CLAMP = 10.0       # 10배 이상은 "훨씬 더"로 표시
_PERCENT_CLAMP    = 200.0      # 200% 이상은 "평소의 2배 이상"으로 표시
_MULTIPLIER_PATTERN = re.compile(r"(?<!\d)(\d+(?:,\d{3})*(?:\.\d+)?)\s*배")
_PERCENT_PATTERN    = re.compile(r"(?<!\d)(\d+(?:,\d{3})*(?:\.\d+)?)\s*%")


def _clamp_friendly_numbers(text: str) -> str:
    """diagnosis/cause 안 비현실적 배수·퍼센트를 일상어로 치환.

    예) "4,595.76배 더" → "훨씬 더 (10배 이상)"
        "1240.77% 초과" → "평소의 2배 이상"
    """
    if not text:
        return text

    def _mult(m: re.Match) -> str:
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            return m.group(0)
        if n >= _MULTIPLIER_CLAMP:
            return "10배 이상"
        return m.group(0)

    def _pct(m: re.Match) -> str:
        try:
            n = float(m.group(1).replace(",", ""))
        except ValueError:
            return m.group(0)
        if n >= _PERCENT_CLAMP:
            return "평소의 2배 이상"
        return m.group(0)

    text = _MULTIPLIER_PATTERN.sub(_mult, text)
    text = _PERCENT_PATTERN.sub(_pct, text)
    return text


def _polish_diagnoses(diagnoses: list[dict], payload: dict[str, Any]) -> list[dict]:
    """진단 카테고리·금액 안전망.

    LLM이 energy_wh 비율(예: baseline의 100배)에 끌려 low_confidence 단발 사용을 "이상"으로
    오분류하는 경우가 잦음. 코드 측에서 mode_references·recent_events 패턴을 보고 강제로
    "사용변화"로 재분류한다. expected_savings_krw_per_month가 0이면 daily_kwh 기반 추정.
    """
    if not diagnoses:
        return diagnoses

    nilm = payload.get("nilm") or {}
    anomaly_events = {e.get("event_id"): e for e in (nilm.get("anomaly_events") or [])}
    mode_refs      = nilm.get("mode_references") or {}
    recent_events  = nilm.get("recent_events") or []
    top_consumers  = {tc.get("appliance"): tc for tc in (nilm.get("top_consumers") or [])}
    unit_krw = _resolve_unit_krw(payload.get("cashback") or {})

    # (가전·모드) → recent event 빈도
    recent_freq: dict[tuple[str, str], int] = {}
    for e in recent_events:
        key = (e.get("appliance", ""), e.get("mode", ""))
        recent_freq[key] = recent_freq.get(key, 0) + 1

    # 모든 anomaly_event의 가전명 집합 — diagnosis/cause에 등장하지 않으면 다른 가전 차용 의심
    known_apps = {e.get("appliance") for e in (nilm.get("anomaly_events") or []) if e.get("appliance")}

    polished: list[dict] = []
    for d in diagnoses:
        eid     = d.get("event_id", "")
        evt     = anomaly_events.get(eid) or {}
        app     = evt.get("appliance") or _extract_appliance_from_diagnosis(d.get("diagnosis", ""))
        mode    = evt.get("mode") or ""
        before  = float(evt.get("before_kw") or 0)
        ref     = (mode_refs.get(app) or {}) if isinstance(mode_refs, dict) else {}
        modes   = ref.get("modes") or {}
        mode_e  = (modes.get(mode) or {}) if isinstance(modes, dict) else {}
        low_conf = bool(mode_e.get("low_confidence"))
        freq     = recent_freq.get((app, mode), 0)

        category = d.get("category", "이상")
        # 사용변화 강제 조건 — 필드가 명시적으로 존재해야 발동 (필드 부재 시 LLM 판단 존중).
        # 이전엔 before_kw 키 부재 시에도 0으로 평가되어 모든 진단을 "사용변화"로 덮어쓰는 버그 있었음.
        if "before_kw" in evt and float(evt.get("before_kw") or 0) == 0:
            category = "사용변화"
        elif low_conf and freq <= _USAGE_CHANGE_SINGLE_EVENT_THRESHOLD:
            category = "사용변화"

        # expected_savings 보정
        savings = int(d.get("expected_savings_krw_per_month") or 0)
        if savings <= 0:
            daily_kwh = float((top_consumers.get(app) or {}).get("daily_kwh") or 0)
            if daily_kwh > 0:
                rate = 0.30 if category == "사용변화" else 0.05
                savings = int(daily_kwh * rate * 30 * unit_krw)

        # 가전 매칭 안전망: diagnosis/cause/action 중 어디든 다른 가전이 노출되면 일반 표현으로 교체.
        # known_apps끼리 부분 일치하는 경우(예: "일반 냉장고" ⊃ "냉장고")도 검출되도록 양방향 비교.
        diag_text   = d.get("diagnosis", "") or ""
        cause_text  = d.get("cause", "") or ""
        action_text = d.get("action", "") or ""

        def _mentions_other_app(text: str) -> bool:
            if not text or not app:
                return False
            for other in known_apps:
                if not other or other == app:
                    continue
                # 양방향 부분 일치 — "일반 냉장고"의 "냉장고"가 다른 가전 진단에 새어나오는 케이스
                if other in text or any(tok in text for tok in other.split() if len(tok) >= 2):
                    return True
            return False

        if app and (app not in diag_text or _mentions_other_app(diag_text) or _mentions_other_app(cause_text)):
            atype = ontology.appliance_type(app)
            diag_text, cause_text, action_text = _fallback_diagnosis_text(app, atype, mode)

        # LLM 응답에 "이(가)" 같은 양쪽 조사 패턴이 노출되면 받침 검사 후 단일 조사로 치환
        diag_text  = _fix_korean_josa(diag_text)
        cause_text = _fix_korean_josa(cause_text)

        polished.append({
            **d,
            "diagnosis": _clamp_friendly_numbers(diag_text),
            "cause":     _clamp_friendly_numbers(cause_text),
            "action":    action_text,
            "category":  category,
            "expected_savings_krw_per_month": max(0, savings),
        })
    return polished


def _extract_appliance_from_diagnosis(text: str) -> str:
    """diagnosis 첫 토큰을 가전명으로 추정 (event_id 매칭 실패 시 fallback)."""
    parts = (text or "").split()
    return parts[0] if parts else ""


_JOSA_PATTERN = re.compile(r"([가-힣A-Za-z0-9]+)\s*(이\(가\)|이/가|가\(이\)|을\(를\)|을/를|를\(을\)|은\(는\)|은/는|는\(은\))")
_JOSA_MAP = {
    "이(가)": ("이", "가"), "이/가": ("이", "가"), "가(이)": ("이", "가"),
    "을(를)": ("을", "를"), "을/를": ("을", "를"), "를(을)": ("을", "를"),
    "은(는)": ("은", "는"), "은/는": ("은", "는"), "는(은)": ("은", "는"),
}


def _fix_korean_josa(text: str) -> str:
    """LLM이 출력한 "이(가)" 같은 양쪽 조사 표기를 받침 검사 후 단일 조사로 치환."""
    if not text:
        return text

    def _repl(m: re.Match) -> str:
        word, josa_token = m.group(1), m.group(2)
        if not word:
            return m.group(0)
        last = word[-1]
        has_jongseong = "가" <= last <= "힣" and (ord(last) - ord("가")) % 28 != 0
        with_jong, without_jong = _JOSA_MAP[josa_token]
        return f"{word}{with_jong if has_jongseong else without_jong}"

    return _JOSA_PATTERN.sub(_repl, text)


def _build_diagnosis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """진단 호출용 payload — mode_references를 anomaly_events 가전만 남긴다.

    LLM이 GCS에서 baseline이 풍부한 다른 가전(예: 일반 냉장고)을 차용해 다른 가전 진단에
    적용하는 오류 방지. anomaly_events 가전의 baseline이 빈약하면 일반 표현 사용 유도.
    """
    nilm = payload.get("nilm") or {}
    anomaly_events = nilm.get("anomaly_events") or []
    anomaly_apps = {e.get("appliance") for e in anomaly_events if e.get("appliance")}
    if not anomaly_apps:
        return payload

    mode_refs = nilm.get("mode_references") or {}
    filtered_refs = {
        app: ref for app, ref in mode_refs.items()
        if app in anomaly_apps
    } if isinstance(mode_refs, dict) else mode_refs

    return {
        **payload,
        "nilm": {**nilm, "mode_references": filtered_refs},
    }


# ── 권고 후처리 ────────────────────────────────────────────────────────────────

_BANNED_TITLE_KEYWORDS = (
    "사용 시간 단축", "사용량 조절", "사용량 줄이기", "가동 시간 조절", "가동 시간 단축",
    "필요할 때만 사용", "사용 점검", "전력 절감", "효율적 사용", "사용 줄이기",
)
_DEFAULT_TIER_KRW = 140  # 단가 정보 부재 시 보수적 fallback (2단계 기준)
_MIN_VISIBLE_SAVINGS_KRW = 100  # 이 미만 권고는 사용자 체감 가치 낮음 — 노출 제외


def _resolve_unit_krw(cashback: dict[str, Any]) -> int:
    """cashback.progressive_tariff에서 한계 요율(원/kWh) 추출, 없으면 fallback."""
    if not isinstance(cashback, dict):
        return _DEFAULT_TIER_KRW
    tariff = cashback.get("progressive_tariff") or cashback.get("tariff") or {}
    rates = tariff.get("tier_rates_krw") or tariff.get("rates") or []
    tier  = tariff.get("current_tier") or 1
    if isinstance(rates, list) and rates and 1 <= tier <= len(rates):
        try:
            return int(rates[tier - 1]) or _DEFAULT_TIER_KRW
        except (TypeError, ValueError):
            return _DEFAULT_TIER_KRW
    return _DEFAULT_TIER_KRW


def _polish_recommendations(recs: list[dict], payload: dict[str, Any]) -> list[dict]:
    """LLM 권고 응답에서 금지 표현·0원 표기·누락 금액을 보정.

    LLM 프롬프트가 위반 사례를 명시했으나 gpt-4o-mini가 흔히 무시 — 코드 측 안전망 필수.
    """
    if not recs:
        return recs
    unit_krw = _resolve_unit_krw(payload.get("cashback") or {})

    polished: list[dict] = []
    for r in recs:
        title = (r.get("title") or "").strip()
        desc  = (r.get("description") or "").strip()
        kwh   = float(r.get("savings_kwh") or 0)
        krw   = int(r.get("savings_krw") or 0)

        # 1) savings_krw=0인데 savings_kwh가 의미 있는 값이면 재계산
        if krw <= 0 and kwh >= 0.1:
            krw = int(kwh * unit_krw)
        # 2) description의 모든 "N원" 금액 표기를 savings_krw와 일치시킴 (LLM이 description에 다른 추정치를 적는 경우 방지)
        if krw > 0:
            desc = re.sub(r"약\s*0\s*원", f"약 {krw:,}원", desc)
            desc = re.sub(r"(\d{1,3}(?:,\d{3})*|\d+)\s*원", f"{krw:,}원", desc)

        # 3) title 금지 키워드 매칭 — 첫 토큰(가전명) 보존 + 구체 행동으로 교체
        if any(kw in title for kw in _BANNED_TITLE_KEYWORDS):
            appliance = title.split()[0] if title else "기기"
            title = f"{appliance} 대기전력 차단 멀티탭"

        # 4) savings_krw가 끝내 0이면 권고 자체 제외 (단 fallback 최소 3건 미충족 시는 유지)
        polished.append({
            "title":        title[:30],
            "savings_kwh":  max(0.01, min(200.0, round(kwh, 2))),
            "savings_krw":  max(0, krw),
            "description":  desc[:150],
        })

    # savings_krw > 0 우선 정렬, 최소 3건 보장
    sorted_recs = sorted(polished, key=lambda x: x["savings_krw"], reverse=True)
    return sorted_recs


# ── 진단 분류 가이드 ──────────────────────────────────────────────────────────
_DIAGNOSIS_CATEGORY_GUIDE = """\
## 입력 트랙 2종 [먼저 인지]
- **피크 트랙** (`anomaly_events`/`anomaly_flags`): 이벤트 레벨 — 진짜 이상 신호 (피크스파이크·에너지이상 등). 본 호출에서 진단 대상.
- **WoW 트랙** (`appliance_wow`): 가전별 전주 대비 일일 kWh 증가 — 사용 패턴 변화 신호. **코드에서 이미 합성 진단을 생성하므로 LLM은 다루지 말 것.** anomaly_diagnoses 출력에 appliance_wow 항목을 포함시키지 말 것 (중복).

## 진단 카테고리 [최우선 규칙]
모든 anomaly_flag/anomaly_event를 아래 3가지 중 하나로 분류한다. 분류 기준을 엄격히 지킬 것.

### "이상" — 기기 결함·성능 저하 의심
판단 조건 (모두 해당해야 "이상"):
  ① baseline이 신뢰 가능 (low_confidence=false) AND
  ② 동일 가전·모드에서 baseline 대비 명확한 초과 (energy_wh ≥ baseline avg_energy_wh × 1.5 또는 duration_threshold 초과) AND
  ③ 패턴이 단발이 아닌 반복 (recent_events에서 같은 모드의 연속 초과 관찰)
또는 다음 단독 조건:
  ④ A/B 유형(상시·다단계) + 피크스파이크 ≥ 1000W → 컴프레서/모터 부하 의심
diagnosis: baseline 비교 수치 + 부품/구성요소 원인 추정 (예: "에어컨 냉방 모드 energy_wh가 baseline 120Wh의 2.1배. 송풍 단계 누락·필터 막힘 가능성")
action: 점검·청소·교체 등 정비성 권고 (headline형 1문장)

### "사용변화" — 평소와 다른 사용 패턴 (정상 행동 가능성 높음)
판단 조건 (하나라도 해당하면 "사용변화"):
  ① baseline avg_energy_wh가 매우 작거나 sample_count < 30 (low_confidence=true) — 평소 거의 안 쓰던 가전
  ② recent_events에 해당 가전·모드 이력이 거의 없는데 큰 값 단발 등장 — 신규 사용
  ③ peak_w ≥ 1000W지만 동일 가전 같은 모드의 다른 이벤트에서 유사 peak가 반복되지 않음
  ④ D 유형(장시간 세션: TV, 컴퓨터, 에어컨 등) + 사용 시간 증가만으로 플래그 — 사용자 선택에 가까움
diagnosis: 변화 사실 + "이상 아닐 가능성" 명시 (예: "TV 일일 사용량 6.2kWh로 전주 평균 0kWh에서 급증. 새로 시청을 시작했을 가능성")
action: 정보 전달 위주 (예: "사용 시간 확인 후 절감 의향 시 시청 시간 조절 권고") — 점검·교체 권고 금지

### "정상" — 진단 출력에서 제외
flag가 떴어도 위 두 분류에 모두 해당하지 않으면 anomaly_diagnoses 배열에서 제외.

## cause 필드 작성
관찰 근거 → 원인 추론 1~2문장. mode_references의 패턴을 인용.
- 예) "냉방 모드의 energy_wh가 baseline 평균의 2.1배로 관찰되며, 송풍 모드 비중이 평소 대비 낮음. 설정 온도가 평소보다 낮게 유지되었거나 필터 막힘에 따른 효율 저하 가능성"
- 예) "최근 7일 중 6일에 평균 5시간 이상 가동 기록. 평소 주 1~2회 단발 사용 대비 빈도가 늘었으나 단위 시간당 소비 패턴은 baseline과 일치"
"사용변화"이면 cause는 "이상 신호로 보기 어려운 이유"를 함께 기술.

## expected_savings_krw_per_month
"이상"  : 점검/수리 후 baseline 회복 가정. (이번 주 초과분 kWh ÷ 7 × 30 × tier_rates_krw[current_tier-1])을 정수로.
"사용변화" : 사용자가 절감 의향이 있을 경우의 가정치. 사용 시간 30% 단축 가정으로 계산.
계산 근거가 부족하면 0 사용.

## action 작성 (headline형 권고)
- "이상" 카테고리: 1문장 권고 (15~40자). 동사형 종결("권고/필요/점검 권장"). 명사 단독 금지.
  예) "필터 청소 및 냉매 누설 점검 권장"
  예) "전기밥솥 보온 회로 절연 상태 점검 필요"
- "사용변화" 카테고리: 정보성 안내 (15~40자).
  예) "시청 시간 조절 의향 있으면 1시간 단축 권고"
  예) "사용 빈도가 평소와 다름 — 의도된 사용인지 확인 권고"
- 2~6자 명사형 ("점검 의뢰", "필터 청소") 단독 사용 금지.

## 사용자 친화 표현 [MANDATORY — diagnosis·cause·action·description 전체 적용]
일반 가정 사용자에게 보일 텍스트다. 데이터 분석가가 아니라 가족이 읽는다고 생각하고 작성한다.

**금지 표현 (출력에 절대 노출 금지)**:
- 변수명·필드명: `energy_wh`, `peak_w`, `avg_w`, `baseline`, `duration_min`, `Wh`, `kWh` 단위 표기, `daily_kwh`, `sample_count`
- 분석 용어: "%초과", "× N배 관찰", "평균의 N배"
- 불안 유발 표현: "기기 부품 노후", "수명 다함", "고장", "긴급" 등 사고 통지 톤 — 사용자 불안 유발. 진단은 정보 전달 톤 유지.

**diagnosis 패턴 ("감지" 중심 — 무엇이 높게 관측됐는지)**:
- 기본 형식: "{가전}이(가) 평소보다 전기를 많이 쓰고 있어요"
- 또는 모드별: "{가전} {모드} 사용이 늘었어요" / "{가전}이 평소보다 자주 작동하고 있어요"
- 좋은 예) "냉장고가 평소보다 전기를 많이 쓰고 있어요"
- 좋은 예) "전기밥솥 보온 사용이 늘었어요"
- 좋은 예) "세탁기가 평소보다 전기를 많이 쓰고 있어요"
- 나쁜 예) "냉장고 사용에 변화가 보여요" ← 너무 막연. 무엇이 높은지 명시할 것.
- 나쁜 예) "10배 이상 더 많은 전기를..." ← 클램핑 부작용, 충격 표현 금지

**cause 패턴 ("감지된 패턴 + 무엇을 확인할지" 2단 구조)**:
- 형식: "{관찰된 모드 패턴}이(가) {평소보다 자주/오래/높게} 관찰됐어요. {확인할 점 1~2가지를 구체적으로}"
- 좋은 예) "냉장고가 평소보다 더 자주 작동하는 것으로 보여요. 문이 잘 닫혀 있는지, 냉장고 뒤쪽에 먼지가 많이 쌓여 있지는 않은지 확인해 보세요."
- 좋은 예) "세탁하거나 탈수할 때 평소보다 전력 사용이 높게 관찰됐어요. 빨래 양이 너무 많지는 않은지, 세탁기가 심하게 흔들리지는 않는지 확인해 보세요."
- 좋은 예) "전기밥솥을 보온 상태로 두는 시간이 평소보다 길어진 것으로 보여요. 식사 후 오래 보온하지 않으면 전기요금 절약에 도움이 될 수 있어요."
- 나쁜 예) "냉각 모드에서 평소보다 많이 사용하고 있어요." ← 확인 행동 없음 — 사용자가 뭘 해야 할지 모름
- 나쁜 예) "10배 이상 더 높게 관찰되며..." ← 숫자 강조 금지
- 나쁜 예) "단속냉각 모드 비중이..." ← 분석 보고서 톤 금지

**가전별 구체 확인 행동 (cause·action 작성 시 참고)**:
- 냉장고/김치냉장고: 문 닫힘 상태, 뒤쪽 먼지·코일, 문 패킹 손상
- 세탁기: 빨래 양, 흔들림, 배수 상태
- 에어컨: 설정 온도, 필터 청소 시기, 실외기 막힘
- 전기밥솥: 보온 시간, 내솥 상태
- 의류건조기: 필터 청소, 빨래 양, 배기구 막힘
- 전기장판/온수매트: 설정 온도, 사용 시간, 타이머 활용
- TV/컴퓨터/공기청정기: 사용 시간, 대기전력, 절전 모드 활용
- 전자레인지/에어프라이어/인덕션: 사용 시간, 예열 줄이기

**action 패턴 (구체 확인 행동, 추천 조치 title로 사용)**:
- 형식: "{가전} {확인 대상} 확인" — 끝에 "권장/권고/권유" 어미 붙이지 말 것
- 좋은 예) "냉장고 문 닫힘 상태와 뒤쪽 먼지 확인"
- 좋은 예) "세탁물 양과 세탁기 흔들림 확인"
- 좋은 예) "전기밥솥 보온 시간 줄이기"
- 좋은 예) "에어컨 설정 온도 1°C 올리기"
- 나쁜 예) "필터 점검 및 냉각 성능 확인 권장" ← "권장" 어미 금지
- 나쁜 예) "사용 패턴 한번 확인해보세요" ← 너무 막연

**description (권고 본문 — 원인 + 행동 + 절감 효과 3단)**:
- 형식: "{왜 그런 패턴이 나올 수 있는지}. {구체 확인·조치 행동}하면 월 기준 약 N원 절약이 예상됩니다."
- 좋은 예) "냉장고 문이 완전히 닫히지 않거나 냉장고 뒤쪽에 먼지가 많으면 냉장고가 더 자주 작동할 수 있어요. 문이 잘 닫히는지 확인하고, 냉장고 주변 먼지를 정리하면 월 기준 약 101원 절약이 예상됩니다."
- 좋은 예) "빨래 양이 너무 많거나 세탁기가 많이 흔들리면 전기를 더 많이 쓸 수 있어요. 세탁물 양을 조금 줄이고 세탁기가 안정적으로 놓여 있는지 확인하면 월 기준 약 49원 절약이 예상됩니다."
- 좋은 예) "밥을 먹은 뒤 보온 상태로 오래 두면 전기 사용량이 늘어날 수 있어요. 필요한 시간만 보온하고 남은 밥은 따로 보관하면 월 기준 약 302원 절약이 예상됩니다."
- 절감 금액은 반드시 명시 + "월 기준 약 N원 절약이 예상됩니다" 표현 사용.
"""


def _build_system_prompt() -> str:
    guidance         = ontology.appliance_guidance_text()
    essential        = "·".join(ontology.essential_appliances())
    essential_verbs  = "·".join(ontology.essential_forbidden_verbs())
    cooling          = "·".join(ontology.cooling_appliances())
    heating          = "·".join(ontology.heating_appliances())
    forbidden        = "·".join(ontology.forbidden_phrases())
    hot_t            = ontology.hot_threshold()
    cold_t           = ontology.cold_threshold()

    return f"""\
한국 가정 전력 절감 전문 코치.
NILM 모니터링 결과·캐시백 계산 결과·날씨 데이터를 받아 아래 JSON 형식으로만 응답.

## 입력 데이터
- nilm.anomaly_events: 실시간 이상 이벤트 (before_kw, after_kw 포함)
- nilm.top_consumers: 가전별 일일 kWh 상위
- nilm.peak_hours: 피크 시간대
- nilm.anomaly_flags: 비정상 플래그 (탐지 범위는 가전 유형에 따라 다름):
  과소비 = baseline avg_energy_wh × 1.5 초과 (C/D, 신뢰 baseline만).
  장시간 = baseline avg_duration_min × 2 또는 duration_threshold_min 초과 (C만, 신뢰 baseline만).
  피크스파이크 = peak_w ≥ 1000W (A/B/C/D 모두, low_confidence 모드 대상).
  에너지이상 = 그룹 중앙값 5배 초과 (C/D, low_confidence 모드 대상).
  각 플래그는 appliance·mode·flag_type·detail 필드를 포함.
  **주의**: anomaly_flags는 "검토 후보"일 뿐, 무조건 "이상"으로 단정 금지. 아래 카테고리 분류 규칙에 따라 "이상"·"사용변화"·"정상" 중 하나로 판정한다.
- nilm.mode_references: 가전별 모드 baseline + type 필드 (A상시/B다단계/C단발/D장시간).
  low_confidence: true이면 sample 부족 또는 마이크로 세그먼트 — 평소 거의 안 쓰던 가전을 의미.
  duration_threshold_min 있으면 해당 값이 장시간 판정 임계 (마이크로 세그먼트 보정).
- nilm.recent_events: 최근 가전 사용 이벤트 (avg_w < 5W 대기 세그먼트 제거 완료)
- cashback: 캐시백 절감 계산 결과
- weather: 최근 날씨 데이터

## 출력 형식
{{
  "anomaly_diagnoses": [
    {{"event_id": "...", "category": "이상|사용변화", "diagnosis": "...", "cause": "...", "action": "...", "expected_savings_krw_per_month": 0}}
  ],
  "recommendations": [{{"title": "...", "savings_kwh": 0.0, "savings_krw": 0, "description": "..."}}]
}}
계산 순서 (recommendations):
  1) savings_krw(원) = daily_kwh × 절감률(0.05~0.10) × 30 × tier_rates_krw[current_tier-1] → 정수(내림).
  2) savings_kwh = savings_krw ÷ tier_rates_krw[current_tier-1] → 소수점 둘째 자리.
  description의 "약 X원"은 savings_krw와 완전히 동일한 값이어야 함 (위반 시 오류).

## title 작성 규칙
title: 권고 핵심 행동을 짧고 구체적으로 (30자 이내). 일반 명사형 권고 금지.
- 금지 예) "가동 시간 단축", "사용 시간 줄이기", "전력 절감", "효율적 사용"
  → 이런 일반 조언은 AI가 없어도 누구나 할 수 있는 말이라 가치 없음. 절대 출력 금지.
- 권장 예) "에어컨 온도 1°C 상승 권고", "전기밥솥 보온 1시간 단축", "TV 저녁 1시간 단축"

## description 작성 규칙 [필수 구조]
description: 반드시 [관찰 근거] + [권고 행동] + [예상 절약 효과] 3단 구조 (150자 이내).
- [관찰 근거]: nilm 데이터에서 관찰한 구체 패턴 (모드 전환 횟수·사용 시간·평균 W 등).
- [권고 행동]: title에 적힌 권고를 다시 한 번 명시.
- [예상 절약 효과]: "1달 기준 약 X원 절약 예상"형식의 원화 금액 (월 단위).
- 예) "송풍↔냉방 전환이 잦은 것으로 보아 설정 온도가 너무 낮은 것으로 판단됩니다. 1°C 상승 시 1달 기준 약 50,000원 절약될 것으로 예상됩니다."
- 예) "취사 후 보온 구간이 평균 4시간으로 길게 관찰됩니다. 보온 1시간 단축 시 1달 기준 약 3,000원 절약될 것으로 예상됩니다."
- 예) "저녁 8~10시 TV 사용량이 가정 내 전력 소비 상위에 해당합니다. 저녁 1시간 단축 시 1달 기준 약 2,500원 절약될 것으로 예상됩니다."
- 금지 표현: "daily_kwh", "사용 패턴을 점검하세요" 류 일반 안내, 절약 금액 누락, 근거 없는 권고.

{_DIAGNOSIS_CATEGORY_GUIDE}

## 진단 출력 규칙
- event_id: nilm.anomaly_events[i].event_id 값을 그대로 사용 (임의 생성·변형 금지).
- 동일 가전에 여러 flag가 있으면 병합해 단일 진단으로 작성 (event_id는 가장 심각한 flag의 것 사용).
- "정상" 분류된 항목은 anomaly_diagnoses 배열에서 제외.
- 모든 anomaly_events에 대해 1:1 매핑할 필요 없음 — 같은 가전 병합 + 정상 제외로 출력 수 줄여도 됨.
- anomaly_events가 비어 있으면 anomaly_diagnoses는 빈 배열([]).

## flag_type별 원인 추정 가이드 (cause·action 작성 시 참고)
  - 과소비 + 냉방·제습·고온 모드 (baseline 신뢰): 필터·코일 막힘 등 성능 저하 의심 → "이상"
  - 과소비 + 기타 모드 (baseline 신뢰): 기기 부품 노후 의심 → "이상"
  - 장시간 (C 유형, baseline 신뢰): 사용 습관 변화 → "사용변화"
  - 피크스파이크 (A 상시·B 사이클) 반복: 컴프레서·모터·히터 부하 → "이상"
  - 피크스파이크 (A 상시·B 사이클) 단발: 일회성 → "사용변화" 또는 정상
  - 피크스파이크 (C·D, low_confidence): 평소 안 쓰던 가전 단발 가동 → "사용변화"
  - 에너지이상 (C·D, low_confidence): 평소 안 쓰던 가전이라 비교 자체가 불안정 → "사용변화" 우선
  - diagnosis·cause에 mode 명시: "에어컨 냉방 모드 ..." 형식으로 모드명 포함.

## 가구 컨텍스트 활용
household_profile의 members(가구원 수)·area_m2·appliances 목록을 참고해 권고 실현 가능성 판단.
appliances에 없는 기기는 권고 대상에서 제외.

## 누진 요금 활용
cashback.progressive_tariff를 참고해 권고의 요금 절감 임팩트를 구체화한다.
- current_tier=2이고 kwh_to_next_tier가 50 이하면 "단계 초과 방지" 관점 강조 가능
- current_tier=3이면 한계 요율(tier_rates_krw[2])이 높으므로 절감 권고가 더 강한 효과
- savings_kwh 산정 시 한계 요율을 고려해 절감 임팩트가 큰 기기를 우선 선택

## 안전 규칙 [MANDATORY]
1. 필수 가전({essential})은 어떤 경우에도 {essential_verbs} 표현 사용 금지. 사용 시간 단축·줄이기 등도 포함. 유일하게 허용되는 권고 방향: 도어·코일·가스켓 등 성능 점검.
2. 다음 표현은 title·action·diagnosis 어디에도 사용 금지: {forbidden}

## 계절 제약 [MANDATORY]
- 냉방 가전({cooling}): 기온 ≥ {hot_t}°C 시즌에만 권고. weather 기온이 미달이면 해당 가전은 권고 목록에서 제외.
- 난방 가전({heating}): 기온 ≤ {cold_t}°C 시즌에만 권고. weather 기온이 초과면 해당 가전은 권고 목록에서 제외.

## 권고 규칙
3~5개. top_consumers에서 daily_kwh 큰 순서로 선택.
- 동일 기기명은 시간대를 달리해도 절대 중복 사용 금지 — 기기명 기준으로 권고 목록 전체에서 단 1회만 등장.
- **"메인 분전반"·"메인분전반"·"MAIN"은 집계 채널이므로 어떤 경우에도 title·description에 포함 금지.**
savings_krw·savings_kwh: 출력 형식의 계산 순서 규칙을 따름. savings_kwh 범위 0.01~200.0.
- 각 항목은 서로 다른 기기
- daily_kwh 0.01 kWh 미만 기기 제외
- 가전 교체·구매·인프라 투자 금지
- mode_references 있으면 standby_avg_w가 높은 가전의 대기전력 절감 권고 추가 고려

## 권고 우선순위 [중요]
LLM 권고는 다음 순서로 선택한다:
1순위: mode_references 패턴 기반 구체 권고
   - 에어컨에서 송풍↔냉방 전환이 잦으면 → "에어컨 설정 온도 1°C 상승 권고"
   - 전기밥솥 보온 duration이 길게 관찰되면 → "전기밥솥 보온 1시간 단축"
   - 모드 전환·duration 등 mode_references에 있는 관찰값을 description의 근거로 명시.
2순위: 사용 시간·시간대 기반 권고 (mode 근거가 없을 때 fallback)
   - "저녁 TV 1시간 단축"처럼 시간대+기기+행동을 구체화. "단순 사용 시간 단축"은 금지.
3순위: 대기전력 권고 (standby_avg_w 관찰 시)

## NILM 관찰 범위 [필수 인식]
NILM은 전력 파형으로 가동 시간·소비량·대기전력·운전 모드 전환을 관찰한다. 내부 설정값(설정 온도·화력 단계)은 직접 측정 불가하나, 모드 전환 패턴에서 간접 추정은 가능.
금지 권고 방향: 시간대 이동·피크 회피 — 총 kWh 절감 없음.
title에 원화 금액 포함 금지 (금액은 description에만).
{guidance}"""


# ── 노드 함수 ──────────────────────────────────────────────────────────────────

def _build_retry_hint(feedback: list[str]) -> str:
    """평가자가 지적한 이슈를 시스템 프롬프트에 끼울 재시도 안내로 변환."""
    if not feedback:
        return ""
    bullets = "\n".join(f"- {f}" for f in feedback[:5])
    return (
        "\n\n## 재시도 호출 — 직전 출력에서 평가자가 발견한 품질 문제\n"
        f"{bullets}\n"
        "위 문제들을 모두 해소한 응답을 생성하라.\n"
    )


def report_node(state: dict[str, Any]) -> dict[str, Any]:
    """Module 5: NILM + 캐시백 데이터를 받아 이상 진단 + 절감 권고 생성.

    evaluator_feedback이 있으면 재시도 호출 — 시스템 프롬프트에 이슈 목록 끼움.
    """
    hh                = state["household_id"]
    nilm_output       = state.get("nilm_output") or {}
    cashback_output   = state.get("cashback_output") or {}
    rag_chunks        = state.get("rag_context") or []
    weather_output    = state.get("weather_output") or {}
    household_profile = state.get("household_profile") or {}
    feedback          = state.get("evaluator_feedback") or []

    payload = {
        "household_profile": household_profile,
        "nilm":              _slim_nilm_output(nilm_output),
        "cashback":          cashback_output,
        "weather":           weather_output,
        "rag_context":       rag_chunks,
    }

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, max_tokens=8192)
    retry_hint    = _build_retry_hint(feedback)
    system_prompt = _build_system_prompt() + retry_hint
    user_content  = json.dumps(payload, ensure_ascii=False, default=_json_default)

    # 진단 호출 전용 payload — mode_references를 anomaly_events 가전만 남겨
    # LLM이 다른 가전 baseline(예: 일반 냉장고)을 차용하지 못하게 한다.
    diag_payload = _build_diagnosis_payload(payload)
    diag_user_content = json.dumps(diag_payload, ensure_ascii=False, default=_json_default)

    diag_hint = (
        "\n\n[이번 호출은 anomaly_diagnoses만 생성한다. recommendations는 별도 호출에서 처리하니"
        " 출력에 포함하지 말 것. 진단 카테고리·cause·action·expected_savings_krw_per_month 채우기.]\n"
        "## 진단 가전 매칭 [위반 금지]\n"
        "1. 각 진단 항목의 diagnosis·cause는 반드시 그 event_id에 해당하는 anomaly_event.appliance를 주어로 작성한다.\n"
        "   예) event.appliance='세탁기'면 diagnosis는 '세탁기가 평소보다...' 형태로 시작.\n"
        "2. 다른 가전(특히 데이터가 풍부한 가전)의 baseline·모드명을 인용해 진단에 끼워넣지 말 것.\n"
        "   예) 세탁기 진단에 '냉장고의 단속냉각 모드' 같이 다른 가전 정보 노출 금지.\n"
        "3. mode_references에서 해당 가전 baseline이 부족하면 일반 표현으로 작성 ('평소보다 오래/많이 사용')."
    )

    diagnoses: list = []
    try:
        diag_result: _DiagnosisOnly = (
            llm
            .with_structured_output(_DiagnosisOnly)
            .invoke([
                SystemMessage(system_prompt + diag_hint),
                HumanMessage(content=diag_user_content),
            ])
        )
        diagnoses = [d.model_dump() for d in diag_result.anomaly_diagnoses]
    except Exception as e:
        logger.exception("진단 호출 실패 — 빈 배열로 진행 (household=%s): %s", hh, e)

    diagnoses = _polish_diagnoses(diagnoses, payload)

    # WoW 트랙: LLM 진단(피크/에너지이상)이 이미 다룬 가전은 스킵하고 나머지를 코드에서 합성.
    _anomaly_evt_map = {e.get("event_id"): e for e in (nilm_output.get("anomaly_events") or [])}
    existing_apps = {
        (_anomaly_evt_map.get(d.get("event_id")) or {}).get("appliance")
        for d in diagnoses
    }
    existing_apps.discard(None)
    existing_apps.discard("")
    wow_items = (nilm_output.get("appliance_wow") or [])
    unit_krw = _resolve_unit_krw(cashback_output)
    diagnoses = diagnoses + _build_wow_diagnoses(wow_items, existing_apps, unit_krw)

    # 권고 호출은 진단 결과를 함께 입력 — "방금 진단한 가전 기준의 구체 권고" 유도
    rec_payload = {**payload, "diagnoses_already_made": diagnoses}
    rec_user_content = json.dumps(rec_payload, ensure_ascii=False, default=_json_default)
    rec_hint = (
        "\n\n[이번 호출은 recommendations만 생성한다. anomaly_diagnoses는 이미 별도 호출에서 처리됐고"
        " diagnoses_already_made 키로 입력에 포함돼 있다.]\n"
        "## 권고 호출 하드 룰 [위반 금지]\n"
        "1. diagnoses_already_made에 항목이 있으면, 그 가전 중심으로 우선 권고 (해당 가전·모드를 description에 명시).\n"
        "2. 일반 명사형 title 절대 금지: \"사용 시간 단축\", \"사용량 조절\", \"가동 시간 조절\", \"필요할 때만 사용\".\n"
        "   → 위반 시 응답 자체가 무효. 반드시 \"X°C 상승\", \"보온 N시간 단축\", \"필터 청소\" 같은 구체 행동만.\n"
        "3. savings_krw = 0인 권고 출력 금지. cashback.progressive_tariff와 daily_kwh로 산정하면 최소 100원 이상 나와야 정상.\n"
        "   - savings_krw가 100원 미만으로 계산되면 그 가전은 제외하고 다른 가전으로 권고 작성.\n"
        "4. description에 \"약 0원 절약\" 또는 \"약 0원\" 문구 절대 금지.\n"
        "5. description은 [관찰 근거] + [구체 행동] + [예상 절약 X원] 3단 구조 — 한 단이라도 빠지면 무효."
    )

    try:
        rec_result: _RecommendationsOnly = (
            llm
            .with_structured_output(_RecommendationsOnly)
            .invoke([
                SystemMessage(system_prompt + rec_hint),
                HumanMessage(content=rec_user_content),
            ])
        )
        recommendations = [r.model_dump() for r in rec_result.recommendations]
    except Exception as e:
        logger.exception("권고 호출 실패 — fallback 권고 사용 (household=%s): %s", hh, e)
        recommendations = _build_fallback(nilm_output)["recommendations"]

    recommendations = _polish_recommendations(recommendations, payload)

    return {"final_output": {
        "anomaly_diagnoses": diagnoses,
        "recommendations":   recommendations,
    }}
