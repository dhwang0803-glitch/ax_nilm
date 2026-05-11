from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from classifier.label_map import N_APPLIANCES, APPLIANCE_LABELS


class PerApplianceScaler:
    """Per-appliance mean/std normalization.

    Three modes:
        balanced  — ON-state only sampling (sparse/high-power appliances)
        fulldata  — full dataset (always-on appliances)
        groupwise — mixed: balanced for sparse, fulldata for always-on
    """

    ALWAYS_ON_LABELS = {
        "refrigerator", "air_filter", "air_conditioner",
        "heater", "rice_cooker", "tv", "pc",
    }

    def __init__(self, scalers: dict[int, tuple[float, float]]):
        self.scalers = scalers

    def normalize(self, power: np.ndarray, appliance_id: int) -> np.ndarray:
        mean, std = self.scalers.get(appliance_id, (0.0, 1.0))
        return ((power - mean) / (std + 1e-8)).astype(np.float32)

    def denormalize(self, norm_power: np.ndarray, appliance_id: int) -> np.ndarray:
        mean, std = self.scalers.get(appliance_id, (0.0, 1.0))
        return (norm_power * (std + 1e-8) + mean).astype(np.float32)

    def get_mean_std(self, appliance_id: int) -> tuple[float, float]:
        return self.scalers.get(appliance_id, (0.0, 1.0))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {}
        for i, name in enumerate(APPLIANCE_LABELS):
            if i in self.scalers:
                mean, std = self.scalers[i]
                data[name] = {"mean": mean, "std": std}
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> PerApplianceScaler:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        scalers: dict[int, tuple[float, float]] = {}
        for i, name in enumerate(APPLIANCE_LABELS):
            if name in raw:
                scalers[i] = (raw[name]["mean"], raw[name]["std"])
        return cls(scalers)

    @classmethod
    def fit(
        cls,
        targets: np.ndarray,
        on_offs: np.ndarray,
        validity: np.ndarray,
        mode: str = "groupwise",
    ) -> PerApplianceScaler:
        """Compute per-appliance mean/std from training data.

        Args:
            targets: (N, 22) raw W values.
            on_offs: (N, 22) binary ON/OFF labels.
            validity: (N, 22) or (22,) validity mask.
            mode: "balanced" | "fulldata" | "groupwise".
        """
        if validity.ndim == 1:
            validity = np.broadcast_to(validity[np.newaxis, :], targets.shape)

        scalers: dict[int, tuple[float, float]] = {}

        for i, name in enumerate(APPLIANCE_LABELS):
            valid_mask = validity[:, i] > 0
            if not valid_mask.any():
                continue

            use_on_only = (
                mode == "balanced"
                or (mode == "groupwise" and name not in cls.ALWAYS_ON_LABELS)
            )

            if use_on_only:
                on_mask = valid_mask & (on_offs[:, i] > 0)
                if on_mask.sum() < 10:
                    on_mask = valid_mask
                vals = targets[on_mask, i]
            else:
                vals = targets[valid_mask, i]

            mean = float(np.mean(vals))
            std = float(np.std(vals))
            if std < 1e-8:
                std = 1.0
            scalers[i] = (mean, std)

        return cls(scalers)
