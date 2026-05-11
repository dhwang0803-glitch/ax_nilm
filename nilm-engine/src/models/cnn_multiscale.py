from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from classifier.label_map import N_APPLIANCES
from features.tda import TDA_DIM


class _FastBranch(nn.Module):
    """Spike detection branch — small kernels + MaxPool to preserve peaks."""

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.Conv1d(32, 32, kernel_size=3, padding=1),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(32, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.AdaptiveMaxPool1d(4),
            nn.Flatten(),
        )
        self.proj = nn.Linear(256, 128)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.conv(x))


class _MediumBranch(nn.Module):
    """Current-scale pattern branch — matches Run 3 kernel sizes."""

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 30, kernel_size=10, padding=4),
            nn.BatchNorm1d(30),
            nn.ReLU(),
            nn.Conv1d(30, 40, kernel_size=8, padding=3),
            nn.BatchNorm1d(40),
            nn.ReLU(),
            nn.MaxPool1d(2),
            nn.Conv1d(40, 50, kernel_size=6, padding=2),
            nn.BatchNorm1d(50),
            nn.ReLU(),
            nn.Conv1d(50, 64, kernel_size=5, padding=2),
            nn.BatchNorm1d(64),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(4),
            nn.Flatten(),
        )
        self.proj = nn.Linear(256, 256)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.proj(self.conv(x))


class _SlowBranch(nn.Module):
    """Sustained-pattern branch — large kernels for broad temporal features."""

    def __init__(self):
        super().__init__()
        self.conv = nn.Sequential(
            nn.Conv1d(1, 16, kernel_size=32, padding=15),
            nn.BatchNorm1d(16),
            nn.ReLU(),
            nn.Conv1d(16, 32, kernel_size=16, padding=7),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.MaxPool1d(4),
            nn.Conv1d(32, 32, kernel_size=8, padding=3),
            nn.BatchNorm1d(32),
            nn.ReLU(),
            nn.AdaptiveAvgPool1d(4),
            nn.Flatten(),
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


class CNNMultiScaleHybrid(nn.Module):
    """
    Multi-Scale CNN + TDA Hybrid for NILM disaggregation.

    Three parallel CNN branches (fast/medium/slow) capture different temporal
    scales, then fuse into the same 512-dim embedding used by the existing
    gate + TDA cross-attention + dual-head structure.

    Interface-compatible with CNNTDAHybrid (drop-in replacement).
    """

    _CNN_EMBED = 512
    _TDA_EMBED = 128
    _MASK_EMBED = 32

    def __init__(self, window_size: int = 1024, dropout: float = 0.1,
                 confidence_threshold: float = 0.5):
        super().__init__()
        self.confidence_threshold = confidence_threshold

        self.fast_branch = _FastBranch()
        self.medium_branch = _MediumBranch()
        self.slow_branch = _SlowBranch()

        self.gate = nn.Sequential(
            nn.Linear(self._CNN_EMBED, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

        self.tda_mlp = nn.Sequential(
            nn.Linear(TDA_DIM, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, self._TDA_EMBED),
            nn.ReLU(),
        )

        self.cross_attn = _CrossAttention(self._CNN_EMBED, self._TDA_EMBED)

        self.mask_proj = nn.Sequential(
            nn.Linear(N_APPLIANCES, self._MASK_EMBED),
            nn.ReLU(),
        )
        _feat_in = self._CNN_EMBED + self._MASK_EMBED  # 512 + 32 = 544

        self.cnn_feat = nn.Sequential(
            nn.Linear(_feat_in, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.cnn_reg = nn.Linear(256, N_APPLIANCES)
        self.cnn_cls = nn.Linear(256, N_APPLIANCES)

        self.fusion_feat = nn.Sequential(
            nn.Linear(_feat_in, 512),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.fusion_reg = nn.Linear(256, N_APPLIANCES)
        self.fusion_cls = nn.Linear(256, N_APPLIANCES)

    def _cnn_encode(self, agg: torch.Tensor) -> torch.Tensor:
        fast = self.fast_branch(agg)
        medium = self.medium_branch(agg)
        slow = self.slow_branch(agg)
        return torch.cat([fast, medium, slow], dim=-1)  # (batch, 512)

    def forward(
        self,
        agg: torch.Tensor,
        tda: torch.Tensor | None = None,
        house_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, ...]:
        cnn_embed = self._cnn_encode(agg)
        confidence = self.gate(cnn_embed)

        if house_mask is not None:
            mask_f = self.mask_proj(house_mask)
        else:
            mask_f = self.mask_proj(
                torch.ones(cnn_embed.shape[0], N_APPLIANCES, device=cnn_embed.device)
            )

        cnn_in = torch.cat([cnn_embed, mask_f], dim=-1)
        cnn_f = self.cnn_feat(cnn_in)
        cnn_pred = self.cnn_reg(cnn_f)

        if tda is None:
            return F.relu(cnn_pred), confidence

        tda_feat = self.tda_mlp(tda)
        fused = self.cross_attn(cnn_embed, tda_feat)
        fused_in = torch.cat([fused, mask_f], dim=-1)
        fusion_f = self.fusion_feat(fused_in)
        fusion_pred = self.fusion_reg(fusion_f)

        pred = F.relu(confidence * cnn_pred + (1 - confidence) * fusion_pred)

        cnn_logit = self.cnn_cls(cnn_f)
        fusion_logit = self.fusion_cls(fusion_f)

        return pred, confidence, cnn_logit, fusion_logit

    def get_confidence(self, agg: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return self.gate(self._cnn_encode(agg))
