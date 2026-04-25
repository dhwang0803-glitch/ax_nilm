"""최종 아키텍처 4종 비교.

방법:
  1. Rule only     — Mid(6/10), 군집 미사용
  2. Prediction only — XGBoost CBL, 군집 미사용
  3. Hybrid        — 군집 가중치 × Mid(6/10)
  4. Hybrid + LLM  — 군집 가중치 × Mid(6/10) + LLM 행동 권고 효과 (모의)

평가 지표: MAE (kWh) — 예측 CBL vs 실제 18~19시 소비량

Note:
  Hybrid+LLM의 LLM 효과는 모의값 (C1 고소비 +5%, C2 중소비 +2%).
  실 서비스에서는 사용자 행동 로그 기반으로 학습 필요.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from benchmark.cbl_methods import Mid610, XGBoostCBL
from benchmark.data_loader import HouseDayData

# 군집별 CBL 조정 가중치 (C1 고소비는 baseline을 높게 잡아야 절감 여지가 큼)
CLUSTER_WEIGHT = {0: 0.95, 1: 1.10, 2: 1.00}

# LLM 행동 권고로 발생하는 추가 절감 기여 비율 (모의)
LLM_EFFECT = {0: 0.00, 1: 0.05, 2: 0.02}


class RuleOnly:
    name = "Rule only"
    _cbl = Mid610()

    def predict(self, history: list[HouseDayData], cluster: int,
                start_h: int, end_h: int) -> float:
        return self._cbl.calc_cbl(history, start_h, end_h)


class PredictionOnly:
    name = "Prediction only"

    def __init__(self):
        self._cbl    = XGBoostCBL()
        self._fitted = False

    def fit(self, all_days: list[HouseDayData], start_h: int, end_h: int) -> None:
        self._cbl.fit(all_days, start_h, end_h)
        self._fitted = True

    def predict(self, history: list[HouseDayData], cluster: int,
                start_h: int, end_h: int) -> float:
        if not self._fitted:
            raise RuntimeError("fit() 먼저 호출")
        return self._cbl.calc_cbl(history, start_h, end_h)


class Hybrid:
    name = "Hybrid"
    _cbl = Mid610()

    def predict(self, history: list[HouseDayData], cluster: int,
                start_h: int, end_h: int) -> float:
        cbl    = self._cbl.calc_cbl(history, start_h, end_h)
        weight = CLUSTER_WEIGHT.get(cluster, 1.0)
        return cbl * weight


class HybridLLM:
    name = "Hybrid+LLM"
    _cbl = Mid610()

    def predict(self, history: list[HouseDayData], cluster: int,
                start_h: int, end_h: int) -> float:
        cbl    = self._cbl.calc_cbl(history, start_h, end_h)
        weight = CLUSTER_WEIGHT.get(cluster, 1.0)
        effect = LLM_EFFECT.get(cluster, 0.0)
        return cbl * weight * (1.0 + effect)


# ── 평가 ──────────────────────────────────────────────────────────────────────

def evaluate_architectures(
    all_data: dict[str, list[HouseDayData]],
    cluster_labels: dict[str, int],
    architectures: list,
    dr_start_h: int = 18,
    dr_end_h: int = 19,
    min_history: int = 10,
) -> pd.DataFrame:
    """Leave-one-out 방식으로 각 아키텍처의 MAE 비교."""
    all_days = [d for days in all_data.values() for d in days if d.is_weekday]
    for arch in architectures:
        if hasattr(arch, 'fit'):
            try:
                arch.fit(all_days, dr_start_h, dr_end_h)
                print(f'  [{arch.name}] fit 완료')
            except Exception as e:
                print(f'  [{arch.name}] fit 실패: {e}')

    records = []
    for arch in architectures:
        for house_id, day_data in all_data.items():
            cluster = cluster_labels.get(house_id, 0)
            wd = [d for d in day_data if d.is_weekday]
            if len(wd) < min_history + 1:
                continue
            for i in range(min_history, len(wd)):
                history = wd[max(0, i - min_history):i]
                try:
                    cbl = arch.predict(history, cluster, dr_start_h, dr_end_h)
                except Exception:
                    continue
                actual = wd[i].window_kwh(dr_start_h, dr_end_h)
                records.append({
                    '아키텍처':   arch.name,
                    'house_id':   house_id,
                    'cbl_kwh':    round(cbl, 4),
                    'actual_kwh': round(actual, 4),
                    'abs_error':  round(abs(cbl - actual), 4),
                })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return (
        df.groupby('아키텍처')
        .agg(MAE=('abs_error', 'mean'), std=('abs_error', 'std'),
             샘플수=('abs_error', 'count'))
        .round(4)
    )
