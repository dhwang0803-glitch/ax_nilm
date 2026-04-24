"""
NILMDisaggregator — 분해 파이프라인 public API.

Confidence-Gated 추론:
  1. 윈도우마다 CNN만으로 confidence score 계산 (빠름)
  2. confidence >= threshold  → CNN head만 사용 (fast path)
     confidence <  threshold  → TDA 계산 후 fusion head 사용 (slow path)
"""

from __future__ import annotations

import numpy as np
import torch

from features.tda import compute_tda_features
from models.cnn_tda import CNNTDAHybrid
from classifier.label_map import APPLIANCE_LABELS, N_APPLIANCES


class NILMDisaggregator:
    """
    단일 분전반 전력 시계열 → 가전 22종 전력 분해.

    Args:
        model_path         : 학습된 CNNTDAHybrid 체크포인트 (.pt)
        window_size        : 슬라이딩 윈도우 크기 (샘플 수), 기본 1024
        stride             : 윈도우 이동 간격, 기본 window_size // 2
        confidence_threshold: gate 임계값 — 이 값 이상이면 TDA 스킵, 기본 0.5
        device             : "cpu" | "cuda" | None (자동 감지)
    """

    def __init__(
        self,
        model_path: str,
        window_size: int = 1024,
        stride: int | None = None,
        confidence_threshold: float = 0.5,
        device: str | None = None,
    ):
        self.window_size = window_size
        self.stride = stride if stride is not None else window_size // 2
        self.threshold = confidence_threshold

        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        self.model = CNNTDAHybrid(
            window_size=window_size,
            confidence_threshold=confidence_threshold,
        ).to(self.device)
        self.model.load_state_dict(
            torch.load(model_path, map_location=self.device)
        )
        self.model.eval()

    def disaggregate(
        self,
        power_series: np.ndarray,
        sample_rate: int = 30,
    ) -> dict[str, np.ndarray]:
        """
        Args:
            power_series: shape (N,) — 유효전력 [W], 30Hz
            sample_rate : Hz (현재 미사용, 확장용)

        Returns:
            dict[appliance_label → np.ndarray shape (N,)]  각 가전 추정 전력 [W]
            윈도우 경계 바깥 샘플은 0으로 채움.
        """
        n = len(power_series)
        accumulator = np.zeros((n, N_APPLIANCES), dtype=np.float32)
        counts      = np.zeros(n, dtype=np.float32)

        for start in range(0, n - self.window_size + 1, self.stride):
            end    = start + self.window_size
            window = power_series[start:end].astype(np.float32)
            center = start + self.window_size // 2

            pred = self._predict_window(window)   # (N_APPLIANCES,)
            accumulator[center] += pred
            counts[center]      += 1.0

        # 예측이 없는 샘플은 인접 center 값으로 채우지 않고 0 유지
        valid = counts > 0
        result_matrix = np.zeros((n, N_APPLIANCES), dtype=np.float32)
        result_matrix[valid] = accumulator[valid] / counts[valid, np.newaxis]

        return {
            label: result_matrix[:, i]
            for i, label in enumerate(APPLIANCE_LABELS)
        }

    def _predict_window(self, window: np.ndarray) -> np.ndarray:
        """단일 윈도우 → (N_APPLIANCES,) numpy array."""
        agg = torch.from_numpy(window).unsqueeze(0).unsqueeze(0).to(self.device)
        # (1, 1, window_size)

        # --- Fast path 판정 (TDA 계산 없이) ---
        confidence = self.model.get_confidence(agg)   # (1, 1)
        if confidence.item() >= self.threshold:
            pred, _ = self.model(agg, tda=None)
            return pred.squeeze(0).cpu().numpy()

        # --- Slow path: TDA 계산 후 fusion ---
        tda_feat = compute_tda_features(window)
        tda = torch.from_numpy(tda_feat).unsqueeze(0).to(self.device)  # (1, TDA_DIM)
        pred, _ = self.model(agg, tda=tda)
        return pred.squeeze(0).cpu().numpy()
