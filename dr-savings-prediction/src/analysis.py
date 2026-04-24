"""군집화 사후 분석 — 클러스터별 특성 요약 및 교차 분석.

파이프라인 흐름에서 '가구 특성·요일은 군집화 입력이 아닌 사후 해석용'에 해당.
"""
import numpy as np
import pandas as pd
from pathlib import Path


def cluster_summary(
    profiles: np.ndarray,
    meta_df: pd.DataFrame,
    labels: np.ndarray,
) -> pd.DataFrame:
    """클러스터별 전력 소비 특성 요약 DataFrame 반환.

    columns: 샘플수, 일소비량(kWh), DR윈도우(kWh), 평균전력(W),
             최대전력(W), 주말비율, 평균기온, 주요가구
    """
    hourly = profiles.reshape(len(profiles), 24, 60).mean(axis=2)
    total_kwh     = profiles.sum(axis=1) / 60 / 1000
    dr_window_kwh = profiles[:, 17*60:20*60].sum(axis=1) / 60 / 1000
    mean_w        = profiles.mean(axis=1)
    peak_w        = profiles.max(axis=1)

    df = meta_df.copy()
    df['cluster']       = labels
    df['total_kwh']     = total_kwh
    df['dr_window_kwh'] = dr_window_kwh
    df['mean_w']        = mean_w
    df['peak_w']        = peak_w

    temp = pd.to_numeric(df['temperature'], errors='coerce')
    df['temperature'] = temp

    summary = df.groupby('cluster').agg(
        샘플수        =('house', 'count'),
        일소비량_kWh  =('total_kwh', 'mean'),
        DR윈도우_kWh  =('dr_window_kwh', 'mean'),
        평균전력_W    =('mean_w', 'mean'),
        최대전력_W    =('peak_w', 'mean'),
        주말비율      =('is_weekend', 'mean'),
        평균기온      =('temperature', 'mean'),
        주요가구      =('house_size', lambda x: x.value_counts().index[0]),
    ).round(2)

    return summary


def weekday_cross(
    meta_df: pd.DataFrame,
    labels: np.ndarray,
) -> pd.DataFrame:
    """클러스터 × 평일/주말 비율 DataFrame 반환."""
    df = meta_df.copy()
    df['cluster'] = labels
    cross = df.groupby(['cluster', 'is_weekend']).size().unstack(fill_value=0)
    cross.columns = ['평일', '주말']
    return cross.div(cross.sum(axis=1), axis=0).round(3)


def house_size_cross(
    meta_df: pd.DataFrame,
    labels: np.ndarray,
) -> pd.DataFrame:
    """클러스터 × 가구원수 비율 DataFrame 반환."""
    df = meta_df.copy()
    df['cluster'] = labels
    cross = df.groupby(['cluster', 'house_size']).size().unstack(fill_value=0)
    return cross.div(cross.sum(axis=1), axis=0).round(3)


def temperature_stats(
    meta_df: pd.DataFrame,
    labels: np.ndarray,
) -> pd.DataFrame:
    """클러스터별 기온 분포 통계 DataFrame 반환."""
    df = meta_df.copy()
    df['cluster'] = labels
    df['temperature'] = pd.to_numeric(df['temperature'], errors='coerce')
    return df.groupby('cluster')['temperature'].describe().round(1)


def run_all(
    profiles: np.ndarray,
    meta_df: pd.DataFrame,
    labels: np.ndarray,
    output_dir: Path,
) -> dict[str, pd.DataFrame]:
    """전체 분석 실행 후 CSV 저장 + dict 반환."""
    output_dir = Path(output_dir)
    (output_dir / 'analysis').mkdir(parents=True, exist_ok=True)

    results = {
        'cluster_summary':    cluster_summary(profiles, meta_df, labels),
        'weekday_cross':      weekday_cross(meta_df, labels),
        'house_size_cross':   house_size_cross(meta_df, labels),
        'temperature_stats':  temperature_stats(meta_df, labels),
    }

    for name, df in results.items():
        path = output_dir / 'analysis' / f'{name}.csv'
        df.to_csv(path, encoding='utf-8-sig')
        print(f'  저장: analysis/{name}.csv')

    return results
