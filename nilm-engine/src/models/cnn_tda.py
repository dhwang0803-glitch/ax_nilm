from __future__ import annotations

import torch
import torch.nn as nn
import torch.nn.functional as F

from classifier.label_map import N_APPLIANCES
from features.tda import TDA_DIM


class _CrossAttention(nn.Module):
    """
    CNN feature vector가 TDA feature vector에 attend.

    CNN features → attention weights over TDA dimensions →
    weighted TDA context → residual add to CNN features.
    """

    def __init__(self, cnn_dim: int, tda_dim: int):
        super().__init__()
        self.attn_proj    = nn.Linear(cnn_dim, tda_dim)
        self.context_proj = nn.Linear(tda_dim, cnn_dim)

    def forward(self, cnn_feat: torch.Tensor, tda_feat: torch.Tensor) -> torch.Tensor:
        attn    = F.softmax(self.attn_proj(cnn_feat), dim=-1)   # (batch, tda_dim)
        context = self.context_proj(attn * tda_feat)             # (batch, cnn_dim)
        return cnn_feat + context                                 # residual


class CNNTDAHybrid(nn.Module):
    """
    Confidence-Gated CNN + TDA Cross-Attention Hybrid.

    학습: TDA 항상 제공 → soft mixture(gate * cnn_pred + (1-gate) * fusion_pred)
          → 두 헤드 모두 학습됨, gate는 자연스럽게 수렴
    추론: get_confidence()로 gate만 먼저 계산 →
          high confidence → cnn_head만 (빠름)
          low confidence  → TDA 계산 후 fusion_head (정밀)

    입력:
        agg : (batch, 1, window_size)
        tda : (batch, TDA_DIM)  — None이면 fast path
    출력:
        pred       : (batch, N_APPLIANCES)
        confidence : (batch, 1)  — 높을수록 CNN만으로 충분
    """

    _CNN_EMBED = 512
    _TDA_EMBED = 128

    def __init__(self, window_size: int = 1024, dropout: float = 0.1,
                 confidence_threshold: float = 0.5):
        super().__init__()
        self.confidence_threshold = confidence_threshold

        self.cnn = nn.Sequential(
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
            nn.AdaptiveAvgPool1d(8),
            nn.Flatten(),                              # → (batch, 512)
        )

        # CNN features만으로 gate score 계산 (TDA 계산 전에 호출 가능)
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

        # Fast path: CNN features → 공유 feature → regression + classification
        self.cnn_feat = nn.Sequential(
            nn.Linear(self._CNN_EMBED, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.cnn_reg = nn.Linear(256, N_APPLIANCES)   # 회귀 헤드 (W)
        self.cnn_cls = nn.Linear(256, N_APPLIANCES)   # 분류 로짓 (BCE용)

        # Slow path: fused features → 공유 feature → regression + classification
        self.fusion_feat = nn.Sequential(
            nn.Linear(self._CNN_EMBED, 512),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Dropout(dropout),
        )
        self.fusion_reg = nn.Linear(256, N_APPLIANCES)  # 회귀 헤드 (W)
        self.fusion_cls = nn.Linear(256, N_APPLIANCES)  # 분류 로짓 (BCE용)

    def forward(
        self, agg: torch.Tensor, tda: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, ...]:
        """
        반환 (tda 제공 시): (pred, confidence, cnn_logit, fusion_logit)
        반환 (tda=None):    (pred, confidence)   — fast inference path
        """
        cnn_embed  = self.cnn(agg)                      # (batch, 512)
        confidence = self.gate(cnn_embed)               # (batch, 1)

        cnn_f    = self.cnn_feat(cnn_embed)             # (batch, 256)
        cnn_pred = self.cnn_reg(cnn_f)                  # (batch, N_APPLIANCES)

        if tda is None:
            return cnn_pred, confidence

        tda_feat    = self.tda_mlp(tda)                                  # (batch, 128)
        fused       = self.cross_attn(cnn_embed, tda_feat)               # (batch, 512)
        fusion_f    = self.fusion_feat(fused)                            # (batch, 256)
        fusion_pred = self.fusion_reg(fusion_f)                          # (batch, N_APPLIANCES)

        pred = confidence * cnn_pred + (1 - confidence) * fusion_pred   # soft mixture

        cnn_logit    = self.cnn_cls(cnn_f)                               # (batch, N_APPLIANCES)
        fusion_logit = self.fusion_cls(fusion_f)                         # (batch, N_APPLIANCES)

        return pred, confidence, cnn_logit, fusion_logit

    def get_confidence(self, agg: torch.Tensor) -> torch.Tensor:
        """TDA 계산 전, CNN만으로 gate score 반환. 추론 파이프라인용."""
        with torch.no_grad():
            return self.gate(self.cnn(agg))            # (batch, 1)
