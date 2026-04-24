import math

import torch
import torch.nn as nn

from classifier.label_map import N_APPLIANCES


class BERT4NILM(nn.Module):
    """
    BERT4NILM (Yue & Johansson 2020) — multi-output 확장판.

    입력: (batch, window_size)      aggregate 유효전력 시퀀스 (채널 차원 없음)
    출력: (batch, N_APPLIANCES)     윈도우 중심점 각 가전 전력값

    BERT의 [CLS] 토큰 대신 시퀀스 중심 위치 출력을 분류에 사용.
    """

    def __init__(
        self,
        window_size: int = 1024,
        d_model: int = 256,
        n_heads: int = 8,
        n_layers: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()
        self.window_size = window_size
        self.center = window_size // 2

        # 스칼라 전력값 → d_model 차원 임베딩
        self.input_proj = nn.Linear(1, d_model)

        # 위치 인코딩 (학습 가능)
        self.pos_embedding = nn.Embedding(window_size, d_model)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)

        self.head = nn.Sequential(
            nn.Linear(d_model, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, N_APPLIANCES),
        )

    def forward(self, x):
        # x: (batch, window_size)
        batch = x.size(0)

        x = x.unsqueeze(-1)                                           # (batch, window_size, 1)
        x = self.input_proj(x)                                        # (batch, window_size, d_model)

        positions = torch.arange(self.window_size, device=x.device)
        x = x + self.pos_embedding(positions)                        # 위치 정보 추가

        x = self.transformer(x)                                       # (batch, window_size, d_model)
        center_feat = x[:, self.center, :]                            # (batch, d_model)

        return self.head(center_feat)                                 # (batch, N_APPLIANCES)
