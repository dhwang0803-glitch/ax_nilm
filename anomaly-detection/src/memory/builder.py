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
    WINDOW_SIZE,
    classify_mode_attention,
    compute_fingerprint,
    load_references,
)

_STANDBY_MIN_W = 1.0
_STANDBY_MIN_MIN = 30.0
_ENTROPY_FALLBACK = 1.0
_HYSTERESIS_W = 10.0

# 코드에서 사용하는 가전명 → thresholds.yaml 키 매핑
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

    TDA 적용 가전(10종): 고정 윈도우(WINDOW_SIZE) 슬라이딩 → TDA classify → 연속 동일 모드 병합.
    TDA 미적용 가전(12종): W 범위 + 히스테리시스 세그먼트.
    references_path 없거나 해당 가전 레퍼런스 없으면 W 범위로 폴백.
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
        if appliance in TDA_APPLIANCES and self._references.get(appliance):
            return self._build_tda_appliance(appliance, group)
        return self._build_wrange_appliance(appliance, group)

    # ── TDA 경로 ────────────────────────────────────────────────────────────

    def _build_tda_appliance(
        self, appliance: str, group: pd.DataFrame
    ) -> list[ShortTermEvent]:
        """고정 윈도우 TDA classify → 연속 동일 모드 병합 → 이벤트."""
        on_thr = ON_THRESHOLDS.get(appliance, DEFAULT_ON_THRESHOLD)
        standby = _detect_standby(group["power_w"], on_thr)

        # TDA는 레퍼런스 빌드(extract_on_segments)와 동일하게 원본 신호를 그대로 사용.
        # on_thr 필터링 시 듀티사이클 0W 구간이 제거되어 위상 구조가 달라지는 문제 방지.
        # 진짜 OFF 기간은 group 자체가 nilm-engine이 이미 걸러낸 결과.
        if not any(group["power_w"] >= on_thr):
            return []  # 전체가 대기전력 이하 → 이벤트 없음
        work = group.copy()

        max_w = APPLIANCE_MAX_W.get(appliance, 1.0)
        signals = work["power_w"].values
        n = len(signals)

        # 윈도우별 TDA 분류 — (start_idx, end_idx, mode, entropy, fingerprint)
        labeled: list[tuple[int, int, str, float | None, list | None]] = []
        for start in range(0, n, WINDOW_SIZE):
            end = min(start + WINDOW_SIZE, n)
            if end - start < 50:   # _MIN_POINTS 미만 꼬리 윈도우 스킵
                break
            fp = compute_fingerprint(signals[start:end], max_w)
            mode, entropy = classify_mode_attention(appliance, fp, self._references)
            if mode is None or (entropy is not None and entropy > _ENTROPY_FALLBACK):
                mode = "unknown"
                entropy = None
            labeled.append((start, end, mode, entropy, fp))

        if not labeled:
            return []

        # 연속 동일 모드 병합
        events: list[ShortTermEvent] = []
        seg_start = 0
        for i in range(1, len(labeled)):
            if labeled[i][2] != labeled[seg_start][2]:
                events.append(self._make_tda_event(
                    appliance, work, signals, labeled[seg_start:i],
                    standby if seg_start == 0 else None,
                ))
                seg_start = i
        if labeled[seg_start:]:
            events.append(self._make_tda_event(
                appliance, work, signals, labeled[seg_start:],
                standby if seg_start == 0 else None,
            ))

        return events

    def _make_tda_event(
        self,
        appliance: str,
        work: pd.DataFrame,
        signals: np.ndarray,
        labeled: list[tuple[int, int, str, float | None, list | None]],
        standby: StandbyEvent | None,
    ) -> ShortTermEvent:
        start_row = labeled[0][0]
        end_row = labeled[-1][1]
        segment = work.iloc[start_row:end_row]

        delta = segment.index.to_series().diff().dropna().median()
        sample_h = (
            delta.total_seconds() / 3600
            if not pd.isna(delta)
            else 1 / (30 * 3600)
        )

        mode = labeled[0][2]
        entropies = [e for _, _, _, e, _ in labeled if e is not None]
        mode_confidence = float(np.mean(entropies)) if entropies else None

        # 대표 fingerprint: 병합 구간 중앙 윈도우 (루프에서 계산한 값 재사용)
        fingerprint = labeled[len(labeled) // 2][4]

        return ShortTermEvent(
            appliance=appliance,
            mode=mode,
            started_at=segment.index[0].to_pydatetime(),
            duration_min=round(len(segment) * sample_h * 60, 1),
            energy_wh=round(float(segment["power_w"].sum() * sample_h), 3),
            avg_w=round(float(segment["power_w"].mean()), 2),
            peak_w=round(float(segment["power_w"].max()), 2),
            tda_fingerprint=fingerprint,
            mode_confidence=mode_confidence,
            standby=standby,
        )

    # ── W-range 경로 ─────────────────────────────────────────────────────────

    def _build_wrange_appliance(
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
            events.append(self._make_wrange_event(
                appliance=appliance,
                segment=segment,
                standby=standby if i == 0 else None,
            ))

        return events

    def _make_wrange_event(
        self,
        appliance: str,
        segment: pd.DataFrame,
        standby: StandbyEvent | None,
    ) -> ShortTermEvent:
        delta = segment.index.to_series().diff().dropna().median()
        sample_h = (
            delta.total_seconds() / 3600
            if not pd.isna(delta)
            else 1 / (30 * 3600)
        )

        return ShortTermEvent(
            appliance=appliance,
            mode=segment["mode"].iloc[0],
            started_at=segment.index[0].to_pydatetime(),
            duration_min=round(len(segment) * sample_h * 60, 1),
            energy_wh=round(float(segment["power_w"].sum() * sample_h), 3),
            avg_w=round(float(segment["power_w"].mean()), 2),
            peak_w=round(float(segment["power_w"].max()), 2),
            tda_fingerprint=None,
            mode_confidence=None,
            standby=standby,
        )
