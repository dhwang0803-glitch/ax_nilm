"""단기 메모리 이벤트 빌더 — 모드 분류 + 수치 집계 + TDA fingerprint."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from anomaly_detection.src.detectors.statistical import (
    ALWAYS_ON,
    DEFAULT_ON_THRESHOLD,
    ON_THRESHOLDS,
)
from anomaly_detection.src.memory.schemas import ShortTermEvent, StandbyEvent
from anomaly_detection.src.models.schemas import DisaggregationResult
from anomaly_detection.src.tda.mode_detector import (
    APPLIANCE_MAX_W,
    TDA_APPLIANCES,
    classify_mode_attention,
    compute_fingerprint,
    load_references,
)

_STANDBY_MIN_W = 1.0
_STANDBY_MIN_MIN = 30.0
_ENTROPY_FALLBACK = 1.0   # entropy > 이 값이면 attention 결과 미채택 → W-range 모드 유지
_HYSTERESIS_W = 10.0  # 경계 dead-band: 현재 모드 이탈에 ±10W 추가 마진 요구

# 코드에서 사용하는 가전명 → thresholds.yaml 키 매핑
# (yaml은 괄호/슬래시/공백 없이 축약, 코드는 AI Hub 표기 그대로)
_THRESHOLD_KEY_MAP: dict[str, str] = {
    "일반 냉장고": "일반냉장고",
    "식기세척기/건조기": "식기세척기",
    "전기장판/담요": "전기장판",
    "무선공유기/셋톱박스": "무선공유기",
    "인덕션(전기레인지)": "인덕션",
    "진공청소기(유선)": "진공청소기",
}


def _load_thresholds(config_path: str | Path) -> dict:
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)["appliances"]


def _classify_with_hysteresis(
    smoothed_w: np.ndarray, states: list[dict]
) -> np.ndarray:
    """rolling mean 값에 히스테리시스를 적용해 경계 진동을 억제한다.

    현재 모드에서 벗어나려면 경계를 _HYSTERESIS_W만큼 추가로 넘어야 한다.
    초기 모드는 첫 샘플 기준 nominal 분류로 결정된다.
    """
    if not states or len(smoothed_w) == 0:
        return np.full(len(smoothed_w), "unknown", dtype=object)

    def _nominal(w: float) -> str:
        for state in states:
            lo = state.get("min_w", 0.0)
            hi = state.get("max_w")
            if w >= lo and (hi is None or w < hi):
                return state["name"]
        return "unknown"

    modes = np.full(len(smoothed_w), "unknown", dtype=object)
    current = _nominal(float(smoothed_w[0]))
    modes[0] = current

    for i in range(1, len(smoothed_w)):
        w = float(smoothed_w[i])
        cur_state = next((s for s in states if s["name"] == current), None)
        if cur_state is None:
            current = _nominal(w)
        else:
            lo = cur_state.get("min_w", 0.0)
            hi = cur_state.get("max_w")
            if (hi is not None and w >= hi + _HYSTERESIS_W) or w < lo - _HYSTERESIS_W:
                current = _nominal(w)
        modes[i] = current

    return modes


def _detect_standby(series: pd.Series, on_thr: float) -> StandbyEvent | None:
    mask = (series >= _STANDBY_MIN_W) & (series < on_thr)
    standby = series[mask]
    if standby.empty:
        return None

    sample_min = series.index.to_series().diff().median().total_seconds() / 60
    duration = len(standby) * sample_min
    if duration < _STANDBY_MIN_MIN:
        return None

    sample_h = sample_min / 60
    return StandbyEvent(
        duration_min=round(duration, 1),
        avg_w=round(float(standby.mean()), 2),
        energy_wh=round(float(standby.sum() * sample_h), 3),
    )


class ShortTermBuilder:
    """DisaggregationResult → ShortTermEvent 변환.

    TDA 적용 가전: W 범위로 세그먼트 경계 검출 후 Persistence Image L2 거리로 모드 재분류.
    TDA 미적용 가전: W 범위 룩업으로만 모드 분류.
    references_path가 없거나 파일 미존재 시 전체 W 범위 룩업으로 폴백.
    """

    def __init__(
        self,
        thresholds_path: str | Path,
        references_path: str | Path | None = None,
    ) -> None:
        self._thresholds = _load_thresholds(thresholds_path)
        self._references: dict = {}
        if references_path is not None:
            self._references = load_references(references_path)
        if self._references:
            print(f"TDA 레퍼런스 로드: {list(self._references.keys())}")
        else:
            print("TDA 레퍼런스 없음 — W 범위 룩업으로 폴백")

    def build(
        self,
        records: list[DisaggregationResult],
        min_confidence: float = 0.6,
    ) -> list[ShortTermEvent]:
        if not records:
            return []

        df = pd.DataFrame(
            [
                {
                    "appliance": r.appliance_type,
                    "timestamp": r.timestamp,
                    "power_w": r.power_w,
                    "confidence": r.confidence,
                }
                for r in records
            ]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df[df["confidence"] >= min_confidence].set_index("timestamp").sort_index()

        events: list[ShortTermEvent] = []
        for appliance, group in df.groupby("appliance"):
            events.extend(self._build_appliance(appliance, group))
        return events

    def _build_appliance(
        self, appliance: str, group: pd.DataFrame
    ) -> list[ShortTermEvent]:
        on_thr = ON_THRESHOLDS.get(appliance, DEFAULT_ON_THRESHOLD)
        standby = _detect_standby(group["power_w"], on_thr)

        if appliance in ALWAYS_ON:
            work = group.copy()
        else:
            work = group[group["power_w"] >= on_thr].copy()
            if work.empty:
                return []

        # 1초 rolling mean으로 듀티사이클 노이즈 감소 후 히스테리시스로 경계 진동 억제
        smoothed_w = work["power_w"].rolling("1s", min_periods=1).mean().values
        key = _THRESHOLD_KEY_MAP.get(appliance, appliance)
        states = self._thresholds.get(key, {}).get("states", [])
        work = work.copy()
        work["mode"] = _classify_with_hysteresis(smoothed_w, states)
        work["seg"] = (work["mode"] != work["mode"].shift()).cumsum()

        events = []
        for i, (_, segment) in enumerate(work.groupby("seg")):
            if len(segment) < 2:
                continue
            event = self._make_event(
                appliance=appliance,
                segment=segment,
                standby=standby if i == 0 else None,
            )
            events.append(event)

        return events

    def _make_event(
        self,
        appliance: str,
        segment: pd.DataFrame,
        standby: StandbyEvent | None,
    ) -> ShortTermEvent:
        delta = segment.index.to_series().diff().dropna().median()
        sample_h = (
            delta.total_seconds() / 3600
            if not pd.isna(delta)
            else 1 / (30 * 3600)  # 30Hz fallback — 1샘플 세그먼트 대비
        )
        avg_w = float(segment["power_w"].mean())
        mode = segment["mode"].iloc[0]

        fingerprint = None
        mode_confidence = None
        if appliance in TDA_APPLIANCES:
            max_w = APPLIANCE_MAX_W.get(appliance, 1.0)
            fingerprint = compute_fingerprint(segment["power_w"].values, max_w)
            tda_mode, entropy = classify_mode_attention(appliance, fingerprint, self._references)
            if tda_mode is not None and (entropy is None or entropy <= _ENTROPY_FALLBACK):
                mode = tda_mode
                mode_confidence = entropy

        return ShortTermEvent(
            appliance=appliance,
            mode=mode,
            started_at=segment.index[0].to_pydatetime(),
            duration_min=round(len(segment) * sample_h * 60, 1),
            energy_wh=round(float(segment["power_w"].sum() * sample_h), 3),
            avg_w=round(avg_w, 2),
            peak_w=round(float(segment["power_w"].max()), 2),
            tda_fingerprint=fingerprint,
            mode_confidence=mode_confidence,
            standby=standby,
        )
