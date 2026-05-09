from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from classifier.label_map import N_APPLIANCES
from features.tda import TDA_DIM


class _FastBranch(nn.Module):

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32), nn.ReLU(),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32), nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64), nn.ReLU(),
            nn.AdaptiveMaxPool1d(4), nn.Flatten(),
        )
        self.proj = nn.Linear(256, 128)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.conv(x))


class _MediumBranch(nn.Module):

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 30, kernel_size=10, padding=4),
            nn.BatchNorm1d(30), nn.ReLU(),
            nn.Conv1d(30, 40, kernel_size=8, padding=3),
            nn.BatchNorm1d(40), nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(40, 50, kernel_size=6, padding=2),
            nn.BatchNorm1d(50), nn.ReLU(),
            nn.Conv1d(50, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64), nn.ReLU(),
            nn.AdaptiveAvgPool1d(4), nn.Flatten(),
        )
        self.proj = nn.Linear(256, 256)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.conv(x))


class _SlowBranch(nn.Module):

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=32, padding=15),
            nn.BatchNorm1d(16), nn.ReLU(),
            nn.Conv1d(16, 32, kernel_size=16, padding=7),
            nn.BatchNorm1d(32), nn.ReLU(),
            nn.MaxPool1d(4),
            nn.Conv1d(32, 32, kernel_size=8, padding=3),
            nn.BatchNorm1d(32), nn.ReLU(),
            nn.AdaptiveAvgPool1d(4), nn.Flatten(),
        )
        self.proj = nn.Linear(128, 128)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.conv(x))


class _CrossAttention(nn.Module):

    def __init__(self, cnn_dim: int, tda_dim: int):
        super().__init__()
        self.attn_proj = nn.Linear(cnn_dim, tda_dim)
        self.context_proj = nn.Linear(tda_dim, cnn_dim)

    def forward(self, cnn_feat: torch.Tensor, tda_feat: torch.Tensor) -> torch.Tensor:
        attn = F.softmax(self.attn_proj(cnn_feat), dim=-1)
        context = self.context_proj(attn * tda_feat)
        return cnn_feat + context


class SharedEncoder(nn.Module):
    """Fast/Medium/Slow 3-branch CNN + TDA cross-attention -> 256-dim feature."""

    _CNN_DIM = 512
    _TDA_EMBED = 128
    OUT_DIM = 256

    def __init__(self, window_size: int = 1024, dropout: float = 0.1):
        super().__init__()
        self.fast = _FastBranch()
        self.medium = _MediumBranch()
        self.slow = _SlowBranch()
        self.tda_mlp = nn.Sequential(
            nn.Linear(TDA_DIM, 64), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(64, self._TDA_EMBED), nn.ReLU(),
        )
        self.cross_attn = _CrossAttention(self._CNN_DIM, self._TDA_EMBED)
        self.feat = nn.Sequential(
            nn.Linear(self._CNN_DIM, self._CNN_DIM), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(self._CNN_DIM, self.OUT_DIM), nn.ReLU(), nn.Dropout(dropout),
        )

    def forward(self, agg: torch.Tensor, tda: torch.Tensor | None = None) -> torch.Tensor:
        f = self.fast(agg)
        m = self.medium(agg)
        s = self.slow(agg)
        embed = torch.cat([f, m, s], dim=-1)  # (batch, 512)
        if tda is not None:
            tda_f = self.tda_mlp(tda)
            embed = self.cross_attn(embed, tda_f)
        return self.feat(embed)  # (batch, 256)


class ApplianceHead(nn.Module):
    """Per-appliance regression + classification head."""

    def __init__(self, input_dim: int = 256):
        super().__init__()
        self.reg = nn.Linear(input_dim, 1)
        self.cls = nn.Linear(input_dim, 1)

    def forward(self, feat: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        return self.reg(feat).squeeze(-1), self.cls(feat).squeeze(-1)


class PerApplianceNILM(nn.Module):
    """SharedEncoder + 22 independent ApplianceHead.

    Args:
        window_size: CNN input window length.
        n_appliances: number of appliance heads.
        dropout: dropout rate for encoder.

    Forward:
        agg: (batch, 1, window_size)
        tda: (batch, TDA_DIM) or None
        active_heads: optional list of head indices (for efficient serving)
    Returns:
        preds:  (batch, n_active) regression output (raw W)
        logits: (batch, n_active) classification logits
    """

    def __init__(self, window_size: int = 1024, n_appliances: int = N_APPLIANCES,
                 dropout: float = 0.1):
        super().__init__()
        self.encoder = SharedEncoder(window_size, dropout)
        self.heads = nn.ModuleList([
            ApplianceHead(SharedEncoder.OUT_DIM) for _ in range(n_appliances)
        ])
        self.n_appliances = n_appliances

    def forward(
        self,
        agg: torch.Tensor,
        tda: torch.Tensor | None = None,
        active_heads: list[int] | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        feat = self.encoder(agg, tda)  # (batch, 256)
        if active_heads is None:
            active_heads = range(self.n_appliances)
        preds, logits = [], []
        for i in active_heads:
            p, l = self.heads[i](feat)
            preds.append(p)
            logits.append(l)
        return torch.stack(preds, dim=-1), torch.stack(logits, dim=-1)


def transfer_weights(
    ckpt_path: str,
    new_model: PerApplianceNILM,
    device: str | torch.device = "cpu",
) -> PerApplianceNILM:
    """CNNMultiScaleHybrid checkpoint -> PerApplianceNILM weight transfer.

    Mapping:
        fast_branch.*     -> encoder.fast.*
        medium_branch.*   -> encoder.medium.*
        slow_branch.*     -> encoder.slow.*
        tda_mlp.*         -> encoder.tda_mlp.*
        cross_attn.*      -> encoder.cross_attn.*
        fusion_feat.*     -> encoder.feat.*
        fusion_reg.weight[i,:] -> heads[i].reg.weight
        fusion_cls.weight[i,:] -> heads[i].cls.weight
    """
    ckpt = torch.load(str(ckpt_path), map_location=device, weights_only=True)
    old_state = ckpt["model_state"] if "model_state" in ckpt else ckpt
    new_state = new_model.state_dict()

    prefix_map = {
        "fast_branch.": "encoder.fast.",
        "medium_branch.": "encoder.medium.",
        "slow_branch.": "encoder.slow.",
        "tda_mlp.": "encoder.tda_mlp.",
        "cross_attn.": "encoder.cross_attn.",
        "fusion_feat.": "encoder.feat.",
    }

    transferred = 0
    for old_key, val in old_state.items():
        for old_prefix, new_prefix in prefix_map.items():
            if old_key.startswith(old_prefix):
                new_key = old_key.replace(old_prefix, new_prefix, 1)
                if new_key in new_state and new_state[new_key].shape == val.shape:
                    new_state[new_key] = val
                    transferred += 1
                break

    for layer in ("reg", "cls"):
        w_key = f"fusion_{layer}.weight"
        b_key = f"fusion_{layer}.bias"
        if w_key in old_state:
            w = old_state[w_key]
            b = old_state[b_key]
            for i in range(min(w.shape[0], len(new_model.heads))):
                new_state[f"heads.{i}.{layer}.weight"] = w[i:i + 1]
                new_state[f"heads.{i}.{layer}.bias"] = b[i:i + 1]
                transferred += 1

    new_model.load_state_dict(new_state)
    print(f"Weight transfer complete: {transferred} blocks")
    return new_model
