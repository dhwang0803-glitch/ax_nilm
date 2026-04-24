from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd


def _parse_label_date(d: str) -> date:
    """'20231030' 또는 '2023-10-30' 양쪽 형식을 date로 변환."""
    d = str(d).replace("-", "")
    return date(int(d[:4]), int(d[4:6]), int(d[6:8]))


def get_house_start_date(data_root: Path, house_id: str) -> date:
    """house의 라벨 parquet 전체에서 가장 이른 날짜를 반환."""
    label_dir = data_root / house_id / "라벨데이터"
    min_date: date | None = None
    for f in sorted(label_dir.glob("ch*.parquet")):
        df = pd.read_parquet(f, columns=["date"])
        for d in df["date"]:
            parsed = _parse_label_date(d)
            if min_date is None or parsed < min_date:
                min_date = parsed
    if min_date is None:
        raise FileNotFoundError(f"라벨 데이터 없음: {label_dir}")
    return min_date


def find_house_channels(data_root: Path, house_id: str) -> list[str]:
    """house의 원천데이터 디렉토리에서 채널 목록 반환 (parquet 파일명 기준)."""
    src_dir = data_root / house_id / "원천데이터"
    if not src_dir.exists():
        return []
    return sorted(p.stem for p in src_dir.glob("ch*.parquet"))


def load_channel_data(
    data_root: Path,
    house_id: str,
    channel: str,
    date_range: tuple[str, str] | None = None,
) -> pd.DataFrame:
    """채널 parquet을 읽어 date_range 구간만 반환.

    columns: date_time(datetime), active_power, voltage, current,
             frequency, apparent_power, reactive_power,
             power_factor, phase_difference, current_phase, voltage_phase
    """
    path = data_root / house_id / "원천데이터" / f"{channel}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"parquet not found: {path}")

    df = pd.read_parquet(path)
    df["date_time"] = pd.to_datetime(df["date_time"])

    if date_range is not None:
        start = pd.Timestamp(date_range[0])
        df = df[df["date_time"] >= start]
        if date_range[1] is not None:
            end = pd.Timestamp(date_range[1]) + pd.Timedelta(days=1) - pd.Timedelta(milliseconds=1)
            df = df[df["date_time"] <= end]

    return df.sort_values("date_time").reset_index(drop=True)


def load_all_labels(
    data_root: Path,
    house_id: str,
    channel: str,
    date_range: tuple[str, str] | None = None,
) -> list[dict]:
    """채널 라벨 parquet을 읽어 date_range 구간 행을 dict 리스트로 반환."""
    path = data_root / house_id / "라벨데이터" / f"{channel}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"label parquet not found: {path}")

    df = pd.read_parquet(path)

    if date_range is not None:
        start = date.fromisoformat(date_range[0])
        end = date.fromisoformat(date_range[1])
        df = df[df["date"].apply(lambda d: start <= _parse_label_date(d) <= end)]

    return df.to_dict(orient="records")


def get_appliance_name(data_root: Path, house_id: str, channel: str) -> str | None:
    """채널의 가전 이름(name 컬럼)을 반환. 실패 시 None."""
    try:
        labels = load_all_labels(data_root, house_id, channel)
        return labels[0]["name"] if labels else None
    except (FileNotFoundError, IndexError, KeyError):
        return None


def find_appliance_channel(
    data_root: Path, house_id: str, channels: list[str], appliance_name: str
) -> str | None:
    """appliance_name과 일치하는 채널을 반환. 없으면 None."""
    for ch in channels:
        if ch == "ch01":
            continue
        if get_appliance_name(data_root, house_id, ch) == appliance_name:
            return ch
    return None


def build_active_mask(labels: list[dict], timestamps: pd.Series) -> np.ndarray:
    """라벨 rows의 active_inactive 구간을 합산해 boolean 마스크 반환.

    active_inactive는 문자열로 저장된 [[start, end], ...] 형태.
    shape: (len(timestamps),)
    """
    mask = np.zeros(len(timestamps), dtype=bool)
    for label in labels:
        raw = label.get("active_inactive")
        if not raw:
            continue
        intervals = ast.literal_eval(raw) if isinstance(raw, str) else raw
        for start_str, end_str in intervals:
            start = pd.Timestamp(start_str)
            end = pd.Timestamp(end_str)
            mask |= (timestamps >= start) & (timestamps <= end)
    return mask
