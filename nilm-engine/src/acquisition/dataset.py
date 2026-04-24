from __future__ import annotations

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
    ):
        """
        week       : 1-based 주차 번호. 각 house의 시작일 기준으로 7일 구간을 자동 계산.
        date_range : ("YYYY-MM-DD", "YYYY-MM-DD") — week 미지정 시 사용.
        scaler     : 외부에서 fit된 PowerScaler. 제공 시 바로 적용.
        fit_scaler : True면 이 dataset의 aggregate 전력값으로 scaler를 새로 fit.
                     train dataset 생성 시 True, test dataset은 train.scaler를 전달.
        """
        from datetime import timedelta

        self.window_size = window_size
        self.stride = stride
        self.scaler: PowerScaler | None = scaler

        data_root = Path(data_root)

        # 세그먼트: (agg_power, target_power, on_off, validity) 배열
        self._segments: list[
            tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]
        ] = []
        self._window_index: list[tuple[int, int]] = []  # (seg_idx, start)
        _all_agg: list[np.ndarray] = []  # fit_scaler용 aggregate 수집

        for house_id in houses:
            channels = find_house_channels(data_root, house_id)
            if "ch01" not in channels:
                print(f"[NILMDataset] {house_id}: ch01 없음 — 스킵")
                continue

            # house별 날짜 범위 결정
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

            # (22, n_samples) 출력 배열 초기화
            target_power = np.zeros((N_APPLIANCES, n_samples), dtype=np.float32)
            on_off_mask = np.zeros((N_APPLIANCES, n_samples), dtype=bool)
            validity = np.zeros(N_APPLIANCES, dtype=bool)

            for ch in channels:
                if ch == "ch01":
                    continue

                name = get_appliance_name(data_root, house_id, ch)
                if name not in APPLIANCE_INDEX:
                    continue  # 22종 외 기타 채널 무시

                idx = APPLIANCE_INDEX[name]

                tgt_df = load_channel_data(data_root, house_id, ch, dr)

                # timestamp 기준 정렬 후 aggregate와 길이 맞춤
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
            seg_idx = len(self._segments)
            self._segments.append((agg_power, target_power, on_off_mask, validity))

            for start in range(0, n_samples - window_size + 1, stride):
                self._window_index.append((seg_idx, start))

        # scaler fit 후 전체 세그먼트에 적용
        if fit_scaler and _all_agg:
            self.scaler = PowerScaler().fit(np.concatenate(_all_agg))

        if self.scaler is not None:
            self._segments = [
                (
                    self.scaler.transform(agg),
                    self.scaler.transform(tgt),
                    on_off,
                    validity,
                )
                for agg, tgt, on_off, validity in self._segments
            ]

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
