"""타겟 10가구의 군집 배정 확인.

ch02~ch23 이벤트 parquet → 일간 1440분 전력 프로파일 재구성 → clusterizer 예측
"""
import sys
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.features.cluster_features import ClusterFeaturizer

BASE_DIR   = Path(r'C:\Users\juyeon\Desktop\ax_nilm_데이터\학습데이터-라벨링데이터')
MODEL_PATH = Path(__file__).parent.parent / 'models_output' / 'clusterizer.joblib'

TARGET_HOUSES = [
    'house_067', 'house_049', 'house_054', 'house_011', 'house_017',
    'house_015', 'house_035', 'house_046', 'house_065', 'house_002',
]

CLUSTER_LABEL = {0: 'C0 저소비', 1: 'C1 고소비', 2: 'C2 중소비'}


def build_daily_profiles(house: str) -> tuple[np.ndarray, list]:
    """ch02~ch23 이벤트 → (N_days, 1440) 전력 프로파일 (W)."""
    house_path = BASE_DIR / house
    events = []

    for ch_num in range(2, 24):
        path = house_path / f'ch{ch_num:02d}.parquet'
        if not path.exists():
            continue
        df = pd.read_parquet(path)
        df['start_time'] = pd.to_datetime(df['start_time'], errors='coerce')
        df['end_time']   = pd.to_datetime(df['end_time'],   errors='coerce')
        df['power_w']    = pd.to_numeric(df['power_consumption'], errors='coerce').fillna(0)
        events.append(df[['start_time', 'end_time', 'power_w']].dropna())

    if not events:
        return np.empty((0, 1440)), []

    all_events = pd.concat(events, ignore_index=True)

    # 날짜 목록
    dates = sorted(set(all_events['start_time'].dt.date.dropna()))

    profiles = []
    for day in dates:
        profile = np.zeros(1440, dtype=np.float32)
        day_events = all_events[all_events['start_time'].dt.date == day]
        for _, row in day_events.iterrows():
            st_min = int(row['start_time'].hour * 60 + row['start_time'].minute)
            et_min = int(
                pd.to_datetime(row['end_time']).hour * 60 +
                pd.to_datetime(row['end_time']).minute
            ) if pd.notna(row['end_time']) else st_min + 1
            st_min = max(0, min(st_min, 1439))
            et_min = max(st_min + 1, min(et_min, 1440))
            profile[st_min:et_min] += row['power_w']
        profiles.append(profile)

    return np.stack(profiles), dates


def main():
    clusterizer = ClusterFeaturizer.load(MODEL_PATH)

    rows = []
    for house in TARGET_HOUSES:
        try:
            profiles, dates = build_daily_profiles(house)
            if len(profiles) == 0:
                rows.append({'가구': house, '대표군집': '데이터 없음', '분포': '', '총일수': 0})
                continue

            labels = clusterizer.transform(profiles)
            most_common = Counter(labels).most_common(1)[0][0]
            dist = Counter(labels)
            total = len(labels)
            dist_str = '  '.join(
                f'C{k}:{v}일({v/total*100:.0f}%)'
                for k, v in sorted(dist.items())
            )
            rows.append({
                '가구':     house,
                '대표군집': CLUSTER_LABEL[most_common],
                '분포':     dist_str,
                '총일수':   total,
            })
        except Exception as e:
            rows.append({'가구': house, '대표군집': f'오류: {e}', '분포': '', '총일수': 0})

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))


if __name__ == '__main__':
    main()
