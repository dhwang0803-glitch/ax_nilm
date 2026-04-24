from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

if TYPE_CHECKING:
    import gcsfs as gcsfs_type

# ── GCS 경로 상수 ─────────────────────────────────────────────────────────────
GCS_BUCKET = "ax-nilm-data-dhwang0803-us"
GCS_RAW_PREFIX = "nilm/training_dev10"
GCS_LABEL_FILE = "nilm/labels/training.parquet"

_DEFAULT_RAW_PREFIX = f"{GCS_BUCKET}/{GCS_RAW_PREFIX}"
_DEFAULT_LABEL_PATH = f"{GCS_BUCKET}/{GCS_LABEL_FILE}"

APPLIANCE_INDEX: dict[str, int] = {
    "TV": 0, "전기포트": 1, "선풍기": 2, "의류건조기": 3, "전기밥솥": 4,
    "식기세척기/건조기": 5, "세탁기": 6, "헤어드라이기": 7, "에어프라이어": 8,
    "진공청소기(유선)": 9, "전자레인지": 10, "에어컨": 11, "인덕션(전기레인지)": 12,
    "전기장판/담요": 13, "온수매트": 14, "제습기": 15, "컴퓨터": 16,
    "공기청정기": 17, "전기다리미": 18, "일반 냉장고": 19, "김치냉장고": 20,
    "무선공유기/셋톱박스": 21,
}
N_APPLIANCES = 22

_labels_cache: dict[str, pd.DataFrame] = {}


def _yyyymmdd(d: str) -> str:
    return str(d).replace("-", "")


def _pa_fs(gcs_fs: "gcsfs_type.GCSFileSystem"):
    """gcsfs → pyarrow FSSpec 래퍼 (parquet/dataset 읽기용)."""
    from pyarrow.fs import PyFileSystem, FSSpecHandler
    return PyFileSystem(FSSpecHandler(gcs_fs))


# ── labels 캐시 ───────────────────────────────────────────────────────────────

def _load_labels_df(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    label_path: str = _DEFAULT_LABEL_PATH,
) -> pd.DataFrame:
    if label_path not in _labels_cache:
        import pyarrow.parquet as pq
        table = pq.read_table(label_path, filesystem=_pa_fs(gcs_fs))
        _labels_cache[label_path] = table.to_pandas()
    return _labels_cache[label_path]


# ── 탐색 함수 ─────────────────────────────────────────────────────────────────

def list_channels_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    bucket_prefix: str = _DEFAULT_RAW_PREFIX,
) -> list[str]:
    """GCS 파티션에서 house의 channel 목록 반환."""
    path = f"{bucket_prefix}/household_id={house_id}/"
    try:
        items = gcs_fs.ls(path)
        channels = []
        for item in items:
            name = item.rstrip("/").split("/")[-1]
            if name.startswith("channel="):
                channels.append(name[len("channel="):])
        return sorted(channels)
    except Exception as e:
        print(f"[list_channels_gcs] {path} 접근 실패: {e}")
        return []


def get_house_start_date_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str = "ch01",
    bucket_prefix: str = _DEFAULT_RAW_PREFIX,
) -> date:
    """GCS 날짜 파티션에서 house의 데이터 시작일 반환."""
    path = f"{bucket_prefix}/household_id={house_id}/channel={channel}/"
    try:
        items = gcs_fs.ls(path)
    except Exception as e:
        raise FileNotFoundError(f"date 파티션 없음: {path}") from e

    dates = []
    for item in items:
        name = item.rstrip("/").split("/")[-1]
        if name.startswith("date="):
            d = name[len("date="):]
            dates.append(date(int(d[:4]), int(d[4:6]), int(d[6:8])))

    if not dates:
        raise FileNotFoundError(f"date 파티션 없음: {path}")
    return min(dates)


# ── 원천데이터 로드 ────────────────────────────────────────────────────────────

def load_channel_data_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str,
    date_range: tuple[str, str] | None = None,
    bucket_prefix: str = _DEFAULT_RAW_PREFIX,
) -> pd.DataFrame:
    """GCS 파티션에서 채널 데이터 로드."""
    import pyarrow.dataset as ds

    path = f"{bucket_prefix}/household_id={house_id}/channel={channel}"
    dataset = ds.dataset(path, filesystem=_pa_fs(gcs_fs), partitioning="hive")

    if date_range is not None:
        start, end = _yyyymmdd(date_range[0]), _yyyymmdd(date_range[1])
        filt = (ds.field("date") >= start) & (ds.field("date") <= end)
        table = dataset.to_table(filter=filt)
    else:
        table = dataset.to_table()

    _PART_COLS = {"household_id", "channel", "date"}
    drop = [c for c in table.column_names if c in _PART_COLS]
    if drop:
        table = table.drop(drop)

    df = table.to_pandas()
    df["date_time"] = pd.to_datetime(df["date_time"])
    return df.sort_values("date_time").reset_index(drop=True)


# ── 라벨 로드 ─────────────────────────────────────────────────────────────────

def load_all_labels_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str,
    date_range: tuple[str, str] | None = None,
    label_path: str = _DEFAULT_LABEL_PATH,
) -> list[dict]:
    """labels/training.parquet에서 house+channel 라벨 조회."""
    df = _load_labels_df(gcs_fs, label_path)
    mask = (df["household_id"] == house_id) & (df["channel"] == channel)

    if date_range is not None:
        start, end = _yyyymmdd(date_range[0]), _yyyymmdd(date_range[1])
        mask &= df["date"].apply(lambda d: start <= _yyyymmdd(str(d)) <= end)

    return df[mask].to_dict(orient="records")


def get_appliance_name_gcs(
    gcs_fs: "gcsfs_type.GCSFileSystem",
    house_id: str,
    channel: str,
    label_path: str = _DEFAULT_LABEL_PATH,
) -> str | None:
    """channel의 가전 이름 반환. 없으면 None."""
    df = _load_labels_df(gcs_fs, label_path)
    rows = df[(df["household_id"] == house_id) & (df["channel"] == channel)]
    if rows.empty or "appliance_name" not in rows.columns:
        return None
    return rows.iloc[0]["appliance_name"]


# ── Dataset ───────────────────────────────────────────────────────────────────

class GCSNILMDataset(Dataset):
    """GCS에서 직접 읽는 NILM 슬라이딩 윈도우 데이터셋."""

    def __init__(
        self,
        houses: list[str],
        gcs_fs: "gcsfs_type.GCSFileSystem",
        bucket_prefix: str = _DEFAULT_RAW_PREFIX,
        label_path: str = _DEFAULT_LABEL_PATH,
        window_size: int = 1024,
        stride: int = 30,
        date_range: tuple[str, str] | None = None,
        week: int | None = None,
        max_week: int | None = None,
        scaler=None,
        fit_scaler: bool = False,
    ):
        from datetime import timedelta

        try:
            from .preprocessor import PowerScaler
            from .loader import build_active_mask
        except ImportError:
            from acquisition.preprocessor import PowerScaler
            from acquisition.loader import build_active_mask

        self.window_size = window_size
        self.stride = stride
        self.scaler = scaler
        self._segments: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
        self._window_index: list[tuple[int, int]] = []
        _all_agg: list[np.ndarray] = []

        for house_id in houses:
            channels = list_channels_gcs(gcs_fs, house_id, bucket_prefix)
            if "ch01" not in channels:
                print(f"[GCSNILMDataset] {house_id}: ch01 없음 — 스킵")
                continue

            if max_week is not None:
                start_date = get_house_start_date_gcs(gcs_fs, house_id, bucket_prefix=bucket_prefix)
                dr: tuple[str, str] | None = (
                    start_date.isoformat(),
                    (start_date + timedelta(days=max_week * 7 - 1)).isoformat(),
                )
            elif week is not None:
                start_date = get_house_start_date_gcs(gcs_fs, house_id, bucket_prefix=bucket_prefix)
                dr = (
                    (start_date + timedelta(days=(week - 1) * 7)).isoformat(),
                    (start_date + timedelta(days=week * 7 - 1)).isoformat(),
                )
            else:
                dr = date_range

            agg_df = load_channel_data_gcs(gcs_fs, house_id, "ch01", dr, bucket_prefix)
            timestamps = agg_df["date_time"]
            n_samples = len(agg_df)

            target_power = np.zeros((N_APPLIANCES, n_samples), dtype=np.float32)
            on_off_mask = np.zeros((N_APPLIANCES, n_samples), dtype=bool)
            validity = np.zeros(N_APPLIANCES, dtype=bool)

            for ch in channels:
                if ch == "ch01":
                    continue
                name = get_appliance_name_gcs(gcs_fs, house_id, ch, label_path)
                if name not in APPLIANCE_INDEX:
                    continue
                idx = APPLIANCE_INDEX[name]
                try:
                    tgt_df = load_channel_data_gcs(gcs_fs, house_id, ch, dr, bucket_prefix)
                    merged = agg_df[["date_time"]].merge(
                        tgt_df[["date_time", "active_power"]],
                        on="date_time",
                        how="left",
                    )
                    target_power[idx] = merged["active_power"].fillna(0).to_numpy(dtype=np.float32)
                    tgt_labels = load_all_labels_gcs(gcs_fs, house_id, ch, dr, label_path)
                    on_off_mask[idx] = build_active_mask(tgt_labels, timestamps)
                    validity[idx] = True
                except Exception as e:
                    print(f"[GCSNILMDataset] {house_id}/{ch} 로드 실패: {e}")

            agg_power = agg_df["active_power"].to_numpy(dtype=np.float32)
            if fit_scaler:
                _all_agg.append(agg_power)
            seg_idx = len(self._segments)
            self._segments.append((agg_power, target_power, on_off_mask, validity))
            for start in range(0, n_samples - window_size + 1, stride):
                self._window_index.append((seg_idx, start))

        if fit_scaler and _all_agg:
            self.scaler = PowerScaler().fit(np.concatenate(_all_agg))

        if self.scaler is not None:
            self._segments = [
                (self.scaler.transform(agg), self.scaler.transform(tgt), on_off, validity)
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
