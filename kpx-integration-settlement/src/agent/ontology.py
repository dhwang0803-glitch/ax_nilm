"""도메인 온톨로지 로더.

domain_ontology.yaml을 읽어 타입 안전한 접근자를 제공한다.
@lru_cache로 프로세스 내 1회만 파싱.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_YAML_PATH = Path(__file__).parent / "domain_ontology.yaml"


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(_YAML_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── 캐시백 정책 ───────────────────────────────────────────────────────────────

def cashback_tiers() -> list[tuple[float, float]]:
    """(threshold, rate_krw_per_kwh) 튜플 리스트. 내림차순 정렬 보장."""
    tiers = _load()["cashback_policy"]["tiers"]
    return [(t["threshold"], t["rate_krw_per_kwh"]) for t in tiers]


def cashback_fallback_rate() -> float:
    return float(_load()["cashback_policy"]["fallback_rate_krw_per_kwh"])


def cashback_savings_cap() -> float:
    return float(_load()["cashback_policy"]["max_savings_cap"])


# ── 계절 임계값 ───────────────────────────────────────────────────────────────

def hot_threshold() -> float:
    return float(_load()["seasonal"]["hot_threshold_c"])


def cold_threshold() -> float:
    return float(_load()["seasonal"]["cold_threshold_c"])


# ── 가전 분류 ─────────────────────────────────────────────────────────────────

def essential_appliances() -> list[str]:
    return list(_load()["appliances"]["essential"]["names"])


def essential_forbidden_verbs() -> list[str]:
    return list(_load()["appliances"]["essential"]["forbidden_verbs"])


def cooling_appliances() -> list[str]:
    return list(_load()["appliances"]["cooling"]["names"])


def heating_appliances() -> list[str]:
    return list(_load()["appliances"]["heating"]["names"])


# ── 이상탐지 정책 분류 (A/B/C/D) ──────────────────────────────────────────────
# nilm_monitor·report_agent가 가전별 flag·WoW 임계를 분기할 때 사용.

def appliance_type(name: str) -> str:
    """가전명 → 'A'·'B'·'C'·'D'. 미지정 가전은 default(C)."""
    cfg = _load()["appliances"]["detection_type"]
    return cfg["map"].get(name, cfg["default"])


# ── 안전 규칙 ─────────────────────────────────────────────────────────────────

def forbidden_phrases() -> list[str]:
    return list(_load()["safety"]["forbidden_phrases"])


# ── 평가 키워드 ───────────────────────────────────────────────────────────────

def efficiency_keywords() -> list[str]:
    return list(_load()["evaluation"]["efficiency_keywords"])


# ── report_agent 프롬프트용 가이드라인 텍스트 생성 ────────────────────────────

def appliance_guidance_text() -> str:
    """guidance 항목을 report_agent 시스템 프롬프트 형식으로 직렬화."""
    guidance = _load()["appliances"]["guidance"]
    lines = []
    for g in guidance:
        names = "·".join(g["names"])
        lines.append(f"- {g['direction']}: {names} → \"{g['template']}\"")
    return "\n".join(lines)
