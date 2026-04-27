"""학습데이터 parquet → HouseDayData 변환.

ch01: 메타데이터 (temperature 등)
ch02~ch23: 가전 이벤트 구간 → 1440분 전력 프로파일 재구성
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

BASE_DIR = Path(r'C:\Users\juyeon\Desktop\ax_nilm_데이터\학습데이터-라벨링데이터')

TARGET_HOUSES = [
    'house_067', 'house_049', 'house_054', 'house_011', 'house_017',
    'house_015', 'house_035', 'house_046', 'house_065', 'house_002',
]


@dataclass
class HouseDayData:
    house_id: str
    day: date
    profile_1440: np.ndarray  # (1440,) W — 분당 평균 전력
    temperature: float | None
    is_weekday: bool

    def window_kwh(self, start_h: int, end_h: int) -> float:
        """특정 시간 구간 소비량 (kWh)."""
        return float(self.profile_1440[start_h * 60:end_h * 60].sum()) / 60.0 / 1000.0

    def hourly_mean(self) -> np.ndarray:
        """(24,) 시간대 평균 전력 (W)."""
        return self.profile_1440.reshape(24, 60).mean(axis=1)


def _load_temperature(house_path: Path) -> dict[str, float]:
    """ch01 parquet → {date_str: temperature} 딕셔너리."""
    ch01 = house_path / 'ch01.parquet'
    if not ch01.exists():
        return {}
    df = pd.read_parquet(ch01)
    result = {}
    for _, row in df.iterrows():
        temp = pd.to_numeric(row.get('temperature', None), errors='coerce')
        if not pd.isna(temp):
            result[str(row['date'])] = float(temp)
    return result


def _build_profiles(house_path: Path) -> dict[date, np.ndarray]:
    """ch02~ch23 이벤트 → {day: (1440,) profile}."""
    day_profiles: dict[date, np.ndarray] = {}

    for ch_num in range(2, 24):
        path = house_path / f'ch{ch_num:02d}.parquet'
        if not path.exists():
            continue

        df = pd.read_parquet(path)
        df['start_time'] = pd.to_datetime(df['start_time'], errors='coerce')
        df['end_time']   = pd.to_datetime(df['end_time'],   errors='coerce')
        df['power_w']    = pd.to_numeric(df['power_consumption'], errors='coerce').fillna(0)
        df = df.dropna(subset=['start_time'])

        for _, row in df.iterrows():
            day = row['start_time'].date()
            if day not in day_profiles:
                day_profiles[day] = np.zeros(1440, dtype=np.float32)

            st = int(row['start_time'].hour * 60 + row['start_time'].minute)
            et_ts = pd.to_datetime(row['end_time'], errors='coerce')
            et = int(et_ts.hour * 60 + et_ts.minute) if pd.notna(et_ts) else st + 1

            st = max(0, min(st, 1439))
            et = max(st + 1, min(et, 1440))
            day_profiles[day][st:et] += row['power_w']

    return day_profiles


def load_house_data(house_id: str) -> list[HouseDayData]:
    house_path = BASE_DIR / house_id
    if not house_path.exists():
        print(f'  [경고] {house_id} 폴더 없음')
        return []

    temperature_map = _load_temperature(house_path)
    day_profiles    = _build_profiles(house_path)

    result = []
    for day, profile in sorted(day_profiles.items()):
        date_str   = day.strftime('%Y%m%d')
        temp       = temperature_map.get(date_str)
        is_weekday = datetime.combine(day, datetime.min.time()).weekday() < 5
        result.append(HouseDayData(
            house_id     = house_id,
            day          = day,
            profile_1440 = profile,
            temperature  = temp,
            is_weekday   = is_weekday,
        ))
    return result


def load_all_target_houses() -> dict[str, list[HouseDayData]]:
    all_data: dict[str, list[HouseDayData]] = {}
    for house_id in TARGET_HOUSES:
        print(f'  Loading {house_id}...')
        data = load_house_data(house_id)
        if data:
            all_data[house_id] = data
    return all_data
