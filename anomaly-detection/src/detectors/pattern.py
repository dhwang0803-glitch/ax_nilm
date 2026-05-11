"""ANOM-002: 학습 기반 비정상 작동 패턴 탐지 (Isolation Forest)."""
from __future__ import annotations

import pickle
import uuid
from datetime import datetime

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from anomaly_detection.src.models.schemas import (
    AnomalyEvent,
    AnomalyType,
    DisaggregationResult,
    Severity,
)


class PatternAnomalyDetector:
    """ANOM-002: Isolation Forest 기반 비정상 패턴 탐지 + 요일/시간대 주기성 편차 감지.

    LSTM Autoencoder 확장 여지 있음 (PyOD / TensorFlow — ANOM-002 요구사항 참조).
    """

    def __init__(
        self,
        contamination: float = 0.05,
        n_estimators: int = 100,
        random_state: int = 42,
        periodicity_std_multiplier: float = 2.0,
    ) -> None:
        self.contamination = contamination
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.periodicity_std_multiplier = periodicity_std_multiplier
        self._models: dict[str, IsolationForest] = {}
        self._baselines: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------ #
    #  public API                                                          #
    # ------------------------------------------------------------------ #

    def fit(self, records: list[DisaggregationResult]) -> None:
        """정상 기간 데이터로 Isolation Forest 학습.

        30Hz 입력이 들어와도 1분 리샘플 후 학습 — hour/dayofweek 피처는
        1분 이하 해상도에서 정보량 증가가 없어 중복 샘플만 늘어나기 때문.
        """
        if not records:
            return

        df = self._to_df(records)
        for appliance, group in df.groupby("appliance_type"):
            group = self._resample_1min(group)
            features = self._features(group)
            if len(features) < 10:
                continue
            model = IsolationForest(
                contamination=self.contamination,
                n_estimators=self.n_estimators,
                random_state=self.random_state,
            )
            model.fit(features)
            self._models[appliance] = model
            self._baselines[appliance] = group

    def detect(self, records: list[DisaggregationResult]) -> list[AnomalyEvent]:
        if not records:
            return []

        df = self._to_df(records)
        events: list[AnomalyEvent] = []

        for appliance, group in df.groupby("appliance_type"):
            events.extend(self._detect_isolation_forest(appliance, group))
            events.extend(self._detect_periodicity(appliance, group))

        return events

    # ------------------------------------------------------------------ #
    #  private                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resample_1min(group: pd.DataFrame) -> pd.DataFrame:
        """타임스탬프 인덱스 기준 1분 리샘플. hour/dayofweek 재계산."""
        resampled = (
            group.set_index("timestamp")[["power_w", "is_on"]]
            .resample("1min")
            .agg({"power_w": "mean", "is_on": "max"})
            .dropna()
            .reset_index()
        )
        resampled["hour"]      = resampled["timestamp"].dt.hour
        resampled["dayofweek"] = resampled["timestamp"].dt.dayofweek
        return resampled

    def _to_df(self, records: list[DisaggregationResult]) -> pd.DataFrame:
        df = pd.DataFrame(
            [
                {
                    "appliance_type": r.appliance_type,
                    "timestamp": r.timestamp,
                    "power_w": r.power_w,
                    "is_on": int(r.is_on),
                }
                for r in records
            ]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["hour"] = df["timestamp"].dt.hour
        df["dayofweek"] = df["timestamp"].dt.dayofweek
        return df

    def _features(self, group: pd.DataFrame) -> np.ndarray:
        return group[["power_w", "is_on", "hour", "dayofweek"]].values

    def _detect_isolation_forest(
        self, appliance: str, group: pd.DataFrame
    ) -> list[AnomalyEvent]:
        model = self._models.get(appliance)
        if model is None:
            return []

        preds = model.predict(self._features(group))
        anomaly_ratio = (preds == -1).mean()

        if anomaly_ratio == 0:
            return []

        severity = (
            Severity.HIGH if anomaly_ratio > 0.3
            else Severity.MEDIUM if anomaly_ratio > 0.1
            else Severity.LOW
        )
        return [
            AnomalyEvent(
                event_id=str(uuid.uuid4()),
                appliance_type=appliance,
                anomaly_type=AnomalyType.PERIODICITY_CHANGE,
                severity=severity,
                detected_at=datetime.now(),
                description=(
                    f"{appliance} 작동 패턴에서 "
                    f"{round(anomaly_ratio * 100, 1)}%의 이상 구간이 탐지되었습니다."
                ),
                recommended_action="기기의 비정상 작동 구간을 확인하세요.",
            )
        ]

    # ------------------------------------------------------------------ #
    #  모델 영속성                                                         #
    # ------------------------------------------------------------------ #

    def save(self, path: str) -> None:
        """학습된 모델을 pickle로 저장.

        Colab: path = '/content/drive/MyDrive/.../pattern_house049.pkl'
        """
        payload = {"models": self._models, "baselines": self._baselines}
        with open(path, "wb") as f:
            pickle.dump(payload, f)

    @classmethod
    def load(cls, path: str, **kwargs) -> "PatternAnomalyDetector":
        """pickle에서 인스턴스를 복원.

        kwargs는 __init__ 파라미터 (contamination 등) 오버라이드용.
        """
        with open(path, "rb") as f:
            payload = pickle.load(f)
        instance = cls(**kwargs)
        instance._models    = payload["models"]
        instance._baselines = payload["baselines"]
        return instance

    def _detect_periodicity(
        self, appliance: str, group: pd.DataFrame
    ) -> list[AnomalyEvent]:
        """요일/시간대별 패턴 편차 > 정상 범위 감지."""
        baseline = self._baselines.get(appliance)
        if baseline is None or baseline.empty:
            return []

        def hourly_profile(df: pd.DataFrame) -> pd.Series:
            return df.groupby("hour")["power_w"].mean()

        baseline_profile = hourly_profile(baseline)
        current_profile = hourly_profile(group)

        common = baseline_profile.index.intersection(current_profile.index)
        if len(common) < 6:
            return []

        diff = (current_profile[common] - baseline_profile[common]).abs()
        threshold = baseline_profile[common].std() * self.periodicity_std_multiplier

        if diff.max() <= threshold:
            return []

        return [
            AnomalyEvent(
                event_id=str(uuid.uuid4()),
                appliance_type=appliance,
                anomaly_type=AnomalyType.PERIODICITY_CHANGE,
                severity=Severity.LOW,
                detected_at=datetime.now(),
                description=f"{appliance}의 시간대별 사용 패턴이 평소와 크게 다릅니다.",
                recommended_action="기기 사용 스케줄 변경 여부를 확인하세요.",
            )
        ]
