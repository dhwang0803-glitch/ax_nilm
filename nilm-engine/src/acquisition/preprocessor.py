from __future__ import annotations

import json
from pathlib import Path

import numpy as np


class PowerScaler:
    """
    active_power 시계열 정규화: (x - mean) / std

    학습 데이터 aggregate 채널 기준으로 fit하고,
    aggregate·appliance 채널 모두에 동일 스케일 적용.
    (상대적 전력 비율 보존을 위해 단일 스케일러 사용)
    """

    def __init__(self) -> None:
        self.mean: float = 0.0
        self.std: float = 1.0

    def fit(self, series: np.ndarray) -> PowerScaler:
        """series: 1D float array (학습용 aggregate 전력값 전체)."""
        self.mean = float(np.mean(series))
        self.std  = float(np.std(series))
        if self.std < 1e-8:
            self.std = 1.0
        return self

    def transform(self, series: np.ndarray) -> np.ndarray:
        return ((series - self.mean) / self.std).astype(np.float32)

    def transform_target(self, series: np.ndarray) -> np.ndarray:
        """가전 target: raw W 그대로 반환. BCE가 주 loss → target scale 정규화 불필요."""
        return series.astype(np.float32)

    def inverse_transform(self, series: np.ndarray) -> np.ndarray:
        return (series * self.std + self.mean).astype(np.float32)

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mean": self.mean, "std": self.std}, indent=2))

    @classmethod
    def load(cls, path: Path) -> PowerScaler:
        data = json.loads(Path(path).read_text())
        scaler = cls()
        scaler.mean = data["mean"]
        scaler.std  = data["std"]
        return scaler
