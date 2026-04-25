import torch
import torch.nn as nn

from classifier.label_map import N_APPLIANCES


class Seq2Point(nn.Module):
    """
    Seq2Point (Zhang et al. 2018) — multi-output 확장판.

    입력: (batch, 1, window_size)   aggregate 유효전력 윈도우
    출력: (batch, N_APPLIANCES)     윈도우 중심점 각 가전 전력값

    원본은 단일 가전 출력이지만, 여기서는 22종 동시 출력으로 확장.
    """

    def __init__(self, window_size: int = 1024, dropout: float = 0.1):
        super().__init__()

        self.conv = nn.Sequential(
            nn.Conv1d(1, 30, kernel_size=10, padding=4),
            nn.ReLU(),
            nn.Conv1d(30, 30, kernel_size=8, padding=3),
            nn.ReLU(),
            nn.Conv1d(30, 40, kernel_size=6, padding=2),
            nn.ReLU(),
            nn.Conv1d(40, 50, kernel_size=5, padding=2),
            nn.ReLU(),
            nn.Conv1d(50, 50, kernel_size=5, padding=2),
            nn.ReLU(),
        )

        # conv 통과 후 실제 길이를 동적으로 계산 (padding 불일치 방지)
        with torch.no_grad():
            _dummy = torch.zeros(1, 1, window_size)
            conv_out_dim = self.conv(_dummy).numel()

        self.fc = nn.Sequential(
            nn.Flatten(),
            nn.Linear(conv_out_dim, 1024),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(1024, 512),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(512, N_APPLIANCES),
            # ReLU 제거: 정규화 공간에서 타깃은 음수 → 역변환 후 클리핑으로 처리
        )

    def forward(self, x):
        # x: (batch, 1, window_size)
        x = self.conv(x)   # (batch, 50, window_size)
        return self.fc(x)  # (batch, N_APPLIANCES)
