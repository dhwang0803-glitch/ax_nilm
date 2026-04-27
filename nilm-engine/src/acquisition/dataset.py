from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from .loader import (
    build_active_mask,
    find_house_channels,
    get_appliance_name,
    get_house_start_date,
    load_all_labels,
    load_channel_data,
)
from .preprocessor import PowerScaler

# 22종 가전 고정 인덱스 — config/dataset.yaml 순서와 동일하게 유지
APPLIANCE_INDEX: dict[str, int] = {
    "TV": 0,
    "전기포트": 1,
    "선풍기": 2,
    "의류건조기": 3,
    "전기밥솥": 4,
    "식기세척기/건조기": 5,
    "세탁기": 6,
    "헤어드라이기": 7,
    "에어프라이어": 8,
    "진공청소기(유선)": 9,
    "전자레인지": 10,
    "에어컨": 11,
    "인덕션(전기레인지)": 12,
    "전기장판/담요": 13,
    "온수매트": 14,
    "제습기": 15,
    "컴퓨터": 16,
    "공기청정기": 17,
    "전기다리미": 18,
    "일반 냉장고": 19,
    "김치냉장고": 20,
    "무선공유기/셋톱박스": 21,
}
N_APPLIANCES = len(APPLIANCE_INDEX)  # 22


def _event_window_starts(
    on_off_mask: np.ndarray,   # (N_APPLIANCES, n_samples) bool
    validity: np.ndarray,       # (N_APPLIANCES,) bool
    n_samples: int,
    window_size: int,
    stride: int,
    event_context: int,
    steady_stride: int,
) -> tuple[list[int], int, int, int]:
    """
    이벤트 기반 윈도우 시작 인덱스를 반환한다.

    반환:
        (sorted 시작 인덱스 목록, 검출된 전환점 수, 이벤트 윈도우 수, 정상 전용 윈도우 수)
        이벤트 윈도우: 전환점 ±event_context 구간에서 생성된 윈도우
        정상 전용 윈도우: steady_stride 샘플링 중 이벤트 윈도우와 겹치지 않는 것
    """
    event_starts: set[int] = set()
    n_transitions = 0

    for app_idx in range(on_off_mask.shape[0]):
        if not validity[app_idx]:
            continue
        diff = np.diff(on_off_mask[app_idx].astype(np.int8), prepend=0)
        transition_idxs = np.where(diff != 0)[0]
        n_transitions += len(transition_idxs)

        for t in transition_idxs:
            center_start = int(t) - window_size // 2
            for k in range(-event_context, event_context + 1):
                s = center_start + k * stride
                if 0 <= s <= n_samples - window_size:
                    event_starts.add(s)

    # 정상 구간 희소 커버리지 (냉장고 등 상시 ON 가전 과소표집 방지)
    steady_starts: set[int] = set()
    for s in range(0, n_samples - window_size + 1, steady_stride):
        steady_starts.add(s)

    n_steady_only = len(steady_starts - event_starts)
    return sorted(event_starts | steady_starts), n_transitions, len(event_starts), n_steady_only


class NILMDataset(Dataset):
    """
    Multi-output 슬라이딩 윈도우 NILM 데이터셋.

    반환값:
        aggregate : (window_size,)            float32 — ch01 유효전력 윈도우
        target    : (N_APPLIANCES, window_size) float32 — 22종 가전 유효전력
        on_off    : (N_APPLIANCES, window_size) bool    — 22종 ON/OFF 마스크
        validity  : (N_APPLIANCES,)            bool    — 이 house에 실제 존재하는 가전

    loss 계산 시 validity=False 채널은 무시하고 학습.

    사용 예:
        ds = NILMDataset(
            houses=["house_067", "house_004"],
            data_root="/path/to/data",
            event_context=20,   # 전환점 ±20 윈도우 (≈ ±20초)
            steady_stride=600,  # 정상 구간 20초마다 1개
        )
        agg, target, on_off, validity = ds[0]
        # agg.shape      → (1024,)
        # target.shape   → (22, 1024)
        # on_off.shape   → (22, 1024)
        # validity.shape → (22,)
    """

    def __init__(
        self,
        houses: list[str],
        data_root: str | Path,
        window_size: int = 1024,
        stride: int = 30,
        date_range: tuple[str, str] | None = None,
        week: int | None = None,
        scaler: PowerScaler | None = None,
        fit_scaler: bool = False,
        cache_dir: str | Path | None = None,
        event_context: int | None = None,
        steady_stride: int | None = None,
    ):
        """
        week          : 1-based 주차 번호. 각 house의 시작일 기준으로 7일 구간을 자동 계산.
        date_range    : ("YYYY-MM-DD", "YYYY-MM-DD") — week 미지정 시 사용.
        scaler        : 외부에서 fit된 PowerScaler. 제공 시 바로 적용.
        fit_scaler    : True면 이 dataset의 aggregate 전력값으로 scaler를 새로 fit.
        cache_dir     : 지정 시 _segments(raw numpy)를 npz로 캐시. window_index는 항상 재생성.
        event_context : 전환점 기준 ±N 윈도우. None이면 전수 슬라이딩.
        steady_stride : 정상 구간 커버리지 stride. None이면 stride × 20 자동 설정.
        """
        from datetime import timedelta

        self.window_size = window_size
        self.stride = stride
        self.scaler: PowerScaler | None = scaler

        data_root = Path(data_root)

        # 캐시 키: 샘플링 파라미터(event_context, steady_stride)는 제외 — window_index는 항상 재생성
        _key = hashlib.md5(
            f"{sorted(houses)}|{date_range}|{week}|{window_size}|{stride}".encode()
        ).hexdigest()[:12]
        self.cache_key = _key
        _cache_path = Path(cache_dir) / f"nilm_{_key}.npz" if cache_dir else None

        self._segments: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        self._window_index: list[tuple[int, int]] = []
        _all_agg: list[np.ndarray] = []

        # ── 1단계: _segments 로드 (캐시 우선) ────────────────────────────────
        if _cache_path and _cache_path.exists():
            _d = np.load(str(_cache_path))
            n_seg = int(_d["n_segments"])
            self._segments = [
                (_d[f"agg_{i}"], _d[f"target_{i}"], _d[f"on_off_{i}"], _d[f"validity_{i}"])
                for i in range(n_seg)
            ]
            if fit_scaler:
                _all_agg = [seg[0] for seg in self._segments]
            print(f"[NILMDataset] 캐시 로드: {_cache_path.name}")
        else:
            for house_id in houses:
                channels = find_house_channels(data_root, house_id)
                if "ch01" not in channels:
                    print(f"[NILMDataset] {house_id}: ch01 없음 — 스킵")
                    continue

                if week is not None:
                    start_date = get_house_start_date(data_root, house_id)
                    dr: tuple[str, str] | None = (
                        (start_date + timedelta(days=(week - 1) * 7)).isoformat(),
                        (start_date + timedelta(days=week * 7 - 1)).isoformat(),
                    )
                else:
                    dr = date_range

                agg_df = load_channel_data(data_root, house_id, "ch01", dr)
                timestamps = agg_df["date_time"]
                n_samples = len(agg_df)

                target_power = np.zeros((N_APPLIANCES, n_samples), dtype=np.float32)
                on_off_mask = np.zeros((N_APPLIANCES, n_samples), dtype=bool)
                validity = np.zeros(N_APPLIANCES, dtype=bool)

                for ch in channels:
                    if ch == "ch01":
                        continue

                    name = get_appliance_name(data_root, house_id, ch)
                    if name not in APPLIANCE_INDEX:
                        continue

                    idx = APPLIANCE_INDEX[name]

                    tgt_df = load_channel_data(data_root, house_id, ch, dr)

                    merged = agg_df[["date_time"]].merge(
                        tgt_df[["date_time", "active_power"]],
                        on="date_time",
                        how="left",
                    )
                    power_values = merged["active_power"].fillna(0).to_numpy(dtype=np.float32)
                    target_power[idx] = power_values

                    tgt_labels = load_all_labels(data_root, house_id, ch, dr)
                    on_off_mask[idx] = build_active_mask(tgt_labels, timestamps)
                    validity[idx] = True

                agg_power = agg_df["active_power"].to_numpy(dtype=np.float32)
                if fit_scaler:
                    _all_agg.append(agg_power)
                self._segments.append((agg_power, target_power, on_off_mask, validity))

            if _cache_path:
                Path(cache_dir).mkdir(parents=True, exist_ok=True)
                _save: dict = {"n_segments": np.array(len(self._segments))}
                for i, (agg, tgt, on_off, val) in enumerate(self._segments):
                    _save[f"agg_{i}"] = agg
                    _save[f"target_{i}"] = tgt
                    _save[f"on_off_{i}"] = on_off
                    _save[f"validity_{i}"] = val
                np.savez_compressed(str(_cache_path), **_save)
                print(f"[NILMDataset] 캐시 저장: {_cache_path.name}")

        # ── 2단계: scaler fit & 적용 ──────────────────────────────────────────
        if fit_scaler and _all_agg:
            self.scaler = PowerScaler().fit(np.concatenate(_all_agg))

        if self.scaler is not None:
            self._segments = [
                (
                    self.scaler.transform(agg),
                    self.scaler.transform_target(tgt),
                    on_off,
                    validity,
                )
                for agg, tgt, on_off, validity in self._segments
            ]

        # ── 3단계: window_index 생성 (항상 재생성, 캐시 불필요) ───────────────
        _ss = steady_stride if steady_stride is not None else stride * 20
        total_transitions = 0
        total_event_windows = 0
        total_steady_windows = 0

        for seg_idx, (agg, _, on_off, validity) in enumerate(self._segments):
            n_samples = len(agg)
            if event_context is not None:
                starts, n_trans, n_event, n_steady = _event_window_starts(
                    on_off, validity, n_samples, window_size, stride, event_context, _ss
                )
                total_transitions += n_trans
                total_event_windows += n_event
                total_steady_windows += n_steady
            else:
                starts = range(0, n_samples - window_size + 1, stride)

            for s in starts:
                self._window_index.append((seg_idx, s))

        if event_context is not None:
            _ratio = total_steady_windows / total_event_windows if total_event_windows > 0 else float("inf")
            print(
                f"[NILMDataset] event_context={event_context}  steady_stride={_ss}  전환점={total_transitions:,}\n"
                f"  이벤트 윈도우={total_event_windows:,} / 정상 전용={total_steady_windows:,}"
                f"  → 비율 1:{_ratio:.1f}\n"
                f"  총 {len(self._window_index):,} windows"
            )
        else:
            print(f"[NILMDataset] full sliding  →  {len(self._window_index):,} windows")

    def __len__(self) -> int:
        return len(self._window_index)

    def __getitem__(self, idx: int):
        seg_idx, start = self._window_index[idx]
        agg, target, on_off, validity = self._segments[seg_idx]
        end = start + self.window_size
        return (
            torch.from_numpy(agg[start:end].copy()),
            torch.from_numpy(target[:, start:end].copy()),
            torch.from_numpy(on_off[:, start:end].copy()),
            torch.from_numpy(validity.copy()),
        )
