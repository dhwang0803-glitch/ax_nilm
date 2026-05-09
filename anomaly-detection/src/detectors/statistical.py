"""ANOM-001: 통계 기반 소비 패턴 이상 탐지."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from anomaly_detection.src.models.schemas import (
    AnomalyEvent,
    AnomalyType,
    DisaggregationResult,
    Severity,
    _SEVERITY_ORDER,
)

# (MEDIUM 기준 비율, HIGH 기준 비율)
_THRESHOLDS: dict[AnomalyType, tuple[float, float]] = {
    AnomalyType.CONSUMPTION_INCREASE: (0.25, 0.40),
    AnomalyType.PEAK_INCREASE: (0.30, 0.50),
    AnomalyType.ABNORMAL_RUNTIME: (0.30, 0.50),
}

# AI Hub 별첨4 기준 가전별 ON 판정 임계값 (W)
# 출처: nilm-engine/docs/appliance_labeling_criteria.md
_ON_THRESHOLDS: dict[str, float] = {
    "TV": 5.0,
    "전기포트": 15.0,
    "선풍기": 2.0,
    "의류건조기": 5.0,
    "전기밥솥": 5.0,
    "식기세척기/건조기": 10.0,
    "세탁기": 10.0,
    "헤어드라이기": 15.0,
    "에어프라이어": 10.0,
    "진공청소기(유선)": 6.0,
    "전자레인지": 10.0,
    "에어컨": 2.0,
    "인덕션(전기레인지)": 15.0,
    "전기장판/담요": 5.0,
    "온수매트": 5.0,
    "제습기": 3.0,
    "컴퓨터": 5.0,
    "공기청정기": 3.0,
    "전기다리미": 15.0,
    "일반 냉장고": 5.0,
    "김치냉장고": 5.0,
    "무선공유기/셋톱박스": 1.0,
}
_DEFAULT_ON_THRESHOLD = 10.0

# Always-On 가전: 런타임 이상 탐지 무의미
_ALWAYS_ON: frozenset[str] = frozenset({"일반 냉장고", "김치냉장고", "무선공유기/셋톱박스"})

# 사이클 기반 탐지 대상 (AI Hub TYPE C + 단발 고전력 TYPE A)
# 이 가전들은 ON→OFF 사이클 단위로 에너지·소요시간을 비교한다
_CYCLE_APPLIANCES: frozenset[str] = frozenset({
    "세탁기", "전기밥솥", "식기세척기/건조기", "의류건조기",
    "전자레인지", "에어프라이어", "전기포트", "전기다리미", "인덕션(전기레인지)",
})

# 사이클 추출 임계값 (W) — "실제 동작 중인가" 판단용
# ON_THRESHOLDS와 다른 경우: 인버터 에어컨처럼 대기전력 > ON 임계값인 가전
# 에어컨은 대기전력 ~6W이므로, ON 임계값 2W로는 대기 구간 전체가 사이클이 됨
# → 압축기 가동 구간(~12W 이상)만 사이클로 인식하도록 별도 임계값 사용
_CYCLE_THRESHOLDS: dict[str, float] = {k: v for k, v in _ON_THRESHOLDS.items()}

# 사이클로 인정하는 최소 지속 시간 (분) — 노이즈성 짧은 ON 제거
_MIN_CYCLE_MIN: dict[str, float] = {
    "세탁기": 5.0,
    "전기밥솥": 5.0,
    "식기세척기/건조기": 5.0,
    "의류건조기": 5.0,
    "에어컨": 3.0,
    "전자레인지": 0.5,
    "에어프라이어": 1.0,
    "전기포트": 0.5,
    "전기다리미": 0.5,
    "인덕션(전기레인지)": 0.5,
}
_DEFAULT_MIN_CYCLE_MIN = 1.0


class StatisticalAnomalyDetector:
    """ANOM-001: 이동 평균 비교 기반 소비 패턴 이상 탐지.

    탐지 결과만으로 기기 성능 저하인지 과다 사용인지 구분 불가.
    원인 해석은 ANOM-003 (LLM 진단 리포트) 담당.

    평가 구간 : 직전 24시간  (실시간 알림 대응)
    베이스라인: 이전 3주 (poc_mode) / 이전 3개월 (production)

    탐지 방식
    ─────────
    연속 부하 가전 (냉장고·제습기 등)
        _check_consumption : 24h 평균 vs 베이스라인 일평균
        _check_peak        : 24h 최대 vs 베이스라인 최대
        _check_runtime     : 24h ON 시간 vs 베이스라인 일 ON 시간

    사이클 가전 (_CYCLE_APPLIANCES: 세탁기·전기밥솥·에어컨 등)
        _check_consumption / _check_peak  : 동일
        _check_cycle       : ON→OFF 사이클별 에너지(Wh)·소요시간 vs 베이스라인 사이클 분포
    """

    def __init__(
        self,
        consumption_threshold: float = 0.25,
        consumption_high: float = 0.40,
        runtime_threshold: float = 0.30,
        runtime_high: float = 0.50,
        peak_threshold: float = 0.30,
        peak_high: float = 0.50,
        min_confidence: float = 0.60,
        poc_mode: bool = True,
    ) -> None:
        self.thresholds = {
            AnomalyType.CONSUMPTION_INCREASE: (consumption_threshold, consumption_high),
            AnomalyType.PEAK_INCREASE: (peak_threshold, peak_high),
            AnomalyType.ABNORMAL_RUNTIME: (runtime_threshold, runtime_high),
        }
        self.min_confidence = min_confidence
        self.poc_mode = poc_mode

    # ------------------------------------------------------------------ #
    #  public API                                                          #
    # ------------------------------------------------------------------ #

    def detect(self, records: list[DisaggregationResult]) -> list[AnomalyEvent]:
        if not records:
            return []

        df = self._to_dataframe(records)
        events: list[AnomalyEvent] = []

        for appliance, group in df.groupby("appliance_type"):
            filtered = group[group["confidence"] >= self.min_confidence]
            if filtered.empty:
                continue

            events.extend(self._check_consumption(appliance, filtered))
            events.extend(self._check_peak(appliance, filtered))

            if appliance in _CYCLE_APPLIANCES:
                events.extend(self._check_cycle(appliance, filtered))
            elif appliance not in _ALWAYS_ON:
                events.extend(self._check_runtime(appliance, filtered))

        return events

    # ------------------------------------------------------------------ #
    #  private — 공통                                                      #
    # ------------------------------------------------------------------ #

    def _to_dataframe(self, records: list[DisaggregationResult]) -> pd.DataFrame:
        df = pd.DataFrame(
            [
                {
                    "appliance_type": r.appliance_type,
                    "timestamp": r.timestamp,
                    "power_w": r.power_w,
                    "confidence": r.confidence,
                    "is_on": r.is_on,
                }
                for r in records
            ]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df.set_index("timestamp").sort_index()

    def _split(self, group: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame] | tuple[None, None]:
        now = group.index.max()
        eval_start = now - timedelta(hours=24)  # 직전 24시간

        if self.poc_mode:
            baseline_start = now - timedelta(weeks=4)
        else:
            baseline_start = now - timedelta(weeks=13)  # ~3개월

        baseline = group[(group.index >= baseline_start) & (group.index < eval_start)]
        eval_period = group[group.index >= eval_start]

        if baseline.empty or eval_period.empty:
            return None, None
        return baseline, eval_period

    def _severity(self, ratio: float, anomaly_type: AnomalyType) -> Severity | None:
        med, high = self.thresholds.get(anomaly_type, (0.20, 0.40))
        if ratio >= high:
            return Severity.HIGH
        if ratio >= med:
            return Severity.MEDIUM
        return None

    def _make_event(
        self,
        appliance: str,
        anomaly_type: AnomalyType,
        severity: Severity,
        description: str,
        recommended_action: str,
    ) -> AnomalyEvent:
        return AnomalyEvent(
            event_id=str(uuid.uuid4()),
            appliance_type=appliance,
            anomaly_type=anomaly_type,
            severity=severity,
            detected_at=datetime.now(),
            description=description,
            recommended_action=recommended_action,
        )

    # ------------------------------------------------------------------ #
    #  private — 연속 부하 공통 체크 (24h vs 베이스라인)                   #
    # ------------------------------------------------------------------ #

    def _check_consumption(self, appliance: str, group: pd.DataFrame) -> list[AnomalyEvent]:
        baseline, eval_period = self._split(group)
        if baseline is None:
            return []

        baseline_mean = baseline["power_w"].resample("D").mean().mean()
        eval_mean = eval_period["power_w"].mean()  # 24h 단일 구간
        if baseline_mean <= 0:
            return []

        ratio = (eval_mean - baseline_mean) / baseline_mean
        severity = self._severity(ratio, AnomalyType.CONSUMPTION_INCREASE)
        if severity is None:
            return []

        return [
            self._make_event(
                appliance,
                AnomalyType.CONSUMPTION_INCREASE,
                severity,
                f"{appliance} 소비량이 기준 대비 {round(ratio * 100, 1)}% 증가했습니다.",
                "기기 상태 점검 및 필터 청소를 권장합니다.",
            )
        ]

    def _check_peak(self, appliance: str, group: pd.DataFrame) -> list[AnomalyEvent]:
        baseline, eval_period = self._split(group)
        if baseline is None:
            return []

        baseline_peak = baseline["power_w"].max()
        eval_peak = eval_period["power_w"].max()
        if baseline_peak <= 0:
            return []

        ratio = (eval_peak - baseline_peak) / baseline_peak
        severity = self._severity(ratio, AnomalyType.PEAK_INCREASE)
        if severity is None:
            return []

        return [
            self._make_event(
                appliance,
                AnomalyType.PEAK_INCREASE,
                severity,
                f"{appliance} 최대 전력이 기준 대비 {round(ratio * 100, 1)}% 상승했습니다.",
                "기기의 즉각적인 점검이 필요합니다.",
            )
        ]

    def _check_runtime(self, appliance: str, group: pd.DataFrame) -> list[AnomalyEvent]:
        """연속 부하 가전용: 24h ON 시간 vs 베이스라인 일평균 ON 시간."""
        baseline, eval_period = self._split(group)
        if baseline is None:
            return []

        on_thr = _ON_THRESHOLDS.get(appliance, _DEFAULT_ON_THRESHOLD)

        baseline_daily_on = (
            (baseline["power_w"] >= on_thr)
            .resample("D").sum()
            .mean()
        )
        eval_on = (eval_period["power_w"] >= on_thr).sum()

        if baseline_daily_on <= 0:
            return []

        ratio = (eval_on - baseline_daily_on) / baseline_daily_on
        severity = self._severity(ratio, AnomalyType.ABNORMAL_RUNTIME)
        if severity is None:
            return []

        return [
            self._make_event(
                appliance,
                AnomalyType.ABNORMAL_RUNTIME,
                severity,
                f"{appliance} 일 평균 작동시간이 기준 대비 {round(ratio * 100, 1)}% 증가했습니다.",
                "기기 사용 패턴 변화 또는 성능 저하를 확인하세요.",
            )
        ]

    # ------------------------------------------------------------------ #
    #  private — 사이클 가전 전용                                          #
    # ------------------------------------------------------------------ #

    def _extract_cycles(
        self, series: pd.Series, on_thr: float, min_dur_min: float
    ) -> list[dict]:
        """ON→OFF 사이클을 추출한다.

        Returns list of {'energy_wh': float, 'duration_min': float}.
        입력 series는 1분 리샘플 기준을 가정 (disaggregator 출력).
        """
        if len(series) < 2:
            return []

        sample_h = (
            series.index.to_series().diff().median().total_seconds() / 3600
        )

        is_on = series >= on_thr
        diff = is_on.astype(int).diff().fillna(0)

        on_starts = series.index[diff == 1].tolist()
        off_times = series.index[diff == -1].tolist()

        # 시리즈 시작이 이미 ON 상태인 경우 첫 인덱스를 시작으로 추가
        if is_on.iloc[0]:
            on_starts = [series.index[0]] + on_starts

        cycles = []
        for start in on_starts:
            ends = [t for t in off_times if t > start]
            end = ends[0] if ends else series.index[-1]

            duration_min = (end - start).total_seconds() / 60
            if duration_min < min_dur_min:
                continue

            segment = series[start:end]
            energy_wh = float(segment.sum() * sample_h)
            cycles.append({"energy_wh": energy_wh, "duration_min": duration_min})

        return cycles

    def _check_cycle(self, appliance: str, group: pd.DataFrame) -> list[AnomalyEvent]:
        """사이클 가전 전용: 직전 24h 사이클 에너지·소요시간 vs 베이스라인 사이클 분포."""
        baseline, eval_period = self._split(group)
        if baseline is None:
            return []

        cycle_thr = _CYCLE_THRESHOLDS.get(appliance, _DEFAULT_ON_THRESHOLD)
        min_dur = _MIN_CYCLE_MIN.get(appliance, _DEFAULT_MIN_CYCLE_MIN)

        bl_cycles = self._extract_cycles(baseline["power_w"], cycle_thr, min_dur)
        ev_cycles = self._extract_cycles(eval_period["power_w"], cycle_thr, min_dur)

        if not bl_cycles or not ev_cycles:
            return []

        bl_energy = float(np.mean([c["energy_wh"] for c in bl_cycles]))
        ev_energy = float(np.mean([c["energy_wh"] for c in ev_cycles]))
        bl_dur = float(np.mean([c["duration_min"] for c in bl_cycles]))
        ev_dur = float(np.mean([c["duration_min"] for c in ev_cycles]))

        events: list[AnomalyEvent] = []

        if bl_energy > 0:
            ratio = (ev_energy - bl_energy) / bl_energy
            sev = self._severity(ratio, AnomalyType.CONSUMPTION_INCREASE)
            if sev:
                events.append(
                    self._make_event(
                        appliance,
                        AnomalyType.CONSUMPTION_INCREASE,
                        sev,
                        f"{appliance} 사이클당 에너지가 기준 대비 {round(ratio * 100, 1)}% 증가했습니다."
                        f" (기준 {bl_energy:.1f}Wh → 현재 {ev_energy:.1f}Wh)",
                        "필터 청소 또는 기기 노후화 점검을 권장합니다.",
                    )
                )

        if bl_dur > 0:
            ratio = (ev_dur - bl_dur) / bl_dur
            sev = self._severity(ratio, AnomalyType.ABNORMAL_RUNTIME)
            if sev:
                events.append(
                    self._make_event(
                        appliance,
                        AnomalyType.ABNORMAL_RUNTIME,
                        sev,
                        f"{appliance} 사이클 소요시간이 기준 대비 {round(ratio * 100, 1)}% 증가했습니다."
                        f" (기준 {bl_dur:.0f}분 → 현재 {ev_dur:.0f}분)",
                        "기기 성능 저하 또는 과부하 여부를 확인하세요.",
                    )
                )

        return events
