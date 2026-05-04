from __future__ import annotations

import numpy as np

from classifier.label_map import APPLIANCE_LABELS, APPLIANCE_LABELING

# always_on 가전 인덱스 — threshold_kind=="always_on"인 냉장고 2종
# evaluate()에서 on_off_arr.any(axis=0)로 보유 여부를 먼저 확인한 뒤 적용
ALWAYS_ON_IDX: list[int] = [
    i for i, name in enumerate(APPLIANCE_LABELS)
    if APPLIANCE_LABELING.get(name, {}).get("threshold_kind") == "always_on"
]


def _remove_short_on(arr: np.ndarray, min_steps: int) -> np.ndarray:
    """ON 연속구간 길이 < min_steps 이면 OFF로 전환."""
    out = arr.copy()
    n, i = len(out), 0
    while i < n:
        if not out[i]:
            i += 1
            continue
        j = i
        while j < n and out[j]:
            j += 1
        if j - i < min_steps:
            out[i:j] = False
        i = j
    return out


def _fill_short_off(arr: np.ndarray, max_gap_steps: int) -> np.ndarray:
    """ON 사이 OFF 구간 길이 <= max_gap_steps 이면 ON으로 메우기 (앞뒤 ON 있을 때만)."""
    out = arr.copy()
    n = len(out)
    # 첫 번째 ON 위치 찾기
    i = 0
    while i < n and not out[i]:
        i += 1
    while i < n:
        if out[i]:
            i += 1
            continue
        j = i
        while j < n and not out[j]:
            j += 1
        # 뒤에 ON이 있고 gap이 짧으면 채우기
        if j < n and j - i <= max_gap_steps:
            out[i:j] = True
        i = j
    return out


def apply_postprocess(
    pred_on: np.ndarray,
    stride_sec: float = 1.0,
) -> np.ndarray:
    """APPLIANCE_LABELING 기준으로 예측 후처리.

    적용 순서:
      1. gap_seconds 이하 OFF 구간 → ON으로 메우기 (짧은 단절 복원)
      2. min_active_seconds 미만 ON spike → OFF로 제거 (오탐 제거)

    Args:
        pred_on: (N_windows, N_appliances) bool 배열
        stride_sec: 윈도우 간 시간 간격 (초). fast=1.0, slow/always_on=30.0
    """
    out = pred_on.copy()
    for i, name in enumerate(APPLIANCE_LABELS):
        crit = APPLIANCE_LABELING.get(name)
        if crit is None:
            continue

        gap_sec = crit.get("gap_seconds")
        if gap_sec is not None and gap_sec > 0 and stride_sec > 0:
            max_gap = max(1, round(gap_sec / stride_sec))
            out[:, i] = _fill_short_off(out[:, i], max_gap)

        min_sec = crit.get("min_active_seconds")
        if min_sec is not None and min_sec > 0 and stride_sec > 0:
            min_steps = max(1, round(min_sec / stride_sec))
            out[:, i] = _remove_short_on(out[:, i], min_steps)

    return out
