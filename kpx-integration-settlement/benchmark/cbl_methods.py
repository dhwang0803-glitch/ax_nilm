"""CBL 예측 방법 4종 비교.

방법:
  1. Mid(8/10)  — 10일 중 상위1·하위1 제외 8일 평균
  2. Mid(6/10)  — 10일 중 상위2·하위2 제외 6일 평균 (KPX 표준, 우리 채택)
  3. XGBoost    — ML 기반 CBL 예측 (optional: pip install xgboost)
  4. TTM        — IBM Tiny Time Mixer (optional: pip install tsfm_public)

평가 지표: MAE (kWh) — 예측 CBL vs 실제 18~19시 소비량
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import numpy as np
import pandas as pd

from benchmark.data_loader import HouseDayData


class CBLMethod(Protocol):
    name: str
    def calc_cbl(self, history: list[HouseDayData], start_h: int, end_h: int) -> float: ...


# ── 1. Mid(8/10) ─────────────────────────────────────────────────────────────

class Mid810:
    name = "Mid(8/10)"

    def calc_cbl(self, history: list[HouseDayData], start_h: int, end_h: int) -> float:
        vals = sorted(d.window_kwh(start_h, end_h) for d in history)
        if len(vals) < 3:
            return float(np.mean(vals)) if vals else 0.0
        return float(np.mean(vals[1:-1]))  # 하위1·상위1 제외


# ── 2. Mid(6/10) ─────────────────────────────────────────────────────────────

class Mid610:
    name = "Mid(6/10)"

    def calc_cbl(self, history: list[HouseDayData], start_h: int, end_h: int) -> float:
        vals = sorted(d.window_kwh(start_h, end_h) for d in history)
        if len(vals) < 6:
            return float(np.mean(vals)) if vals else 0.0
        return float(np.mean(vals[2:-2]))  # 하위2·상위2 제외


# ── 3. XGBoost ────────────────────────────────────────────────────────────────

class XGBoostCBL:
    name = "XGBoost"

    def __init__(self):
        try:
            from xgboost import XGBRegressor
            self._model = XGBRegressor(
                n_estimators=200, max_depth=4,
                learning_rate=0.05, random_state=42, verbosity=0,
            )
            self._fitted = False
        except ImportError:
            raise ImportError("pip install xgboost 필요")

    def _features(self, d: HouseDayData, start_h: int, end_h: int) -> list[float]:
        h = d.hourly_mean()
        return [
            d.day.weekday(),
            d.day.month,
            d.temperature or 0.0,
            float(h[start_h - 1]) if start_h > 0 else 0.0,   # 이벤트 직전 시간 전력
            float(h[:start_h].mean()),                         # 이벤트 전 평균
            float(h.max()),                                     # 일 최대 전력
            float(h.std()),                                     # 일 표준편차
        ]

    def fit(self, all_days: list[HouseDayData], start_h: int, end_h: int) -> None:
        X = [self._features(d, start_h, end_h) for d in all_days]
        y = [d.window_kwh(start_h, end_h) for d in all_days]
        self._model.fit(X, y)
        self._fitted = True
        self._start_h, self._end_h = start_h, end_h

    def calc_cbl(self, history: list[HouseDayData], start_h: int, end_h: int) -> float:
        if not self._fitted:
            raise RuntimeError("fit() 먼저 호출")
        X = [self._features(d, start_h, end_h) for d in history[-3:]]
        return float(np.mean(self._model.predict(X)))


# ── 4. TTM (Tiny Time Mixer) ─────────────────────────────────────────────────

class TTMCBL:
    name = "TTM"

    def __init__(self):
        try:
            from tsfm_public import TinyTimeMixerForPrediction
            self._model = TinyTimeMixerForPrediction.from_pretrained(
                "ibm/TTM", revision="main"
            )
        except ImportError:
            raise ImportError("pip install tsfm_public 필요")

    def calc_cbl(self, history: list[HouseDayData], start_h: int, end_h: int) -> float:
        import torch
        # 시간 단위 시계열 구성 (최대 512 타임스텝)
        hourly_vals: list[float] = []
        for d in history:
            hourly_vals.extend(d.hourly_mean().tolist())

        ctx = np.array(hourly_vals[-512:], dtype=np.float32)
        x   = torch.tensor(ctx).unsqueeze(0).unsqueeze(-1)

        with torch.no_grad():
            out = self._model(x)

        pred_24 = out.prediction_outputs[0, :24, 0].numpy()
        return float(pred_24[start_h:end_h].sum() / 1000.0)


# ── 평가 ──────────────────────────────────────────────────────────────────────

def evaluate_cbl(
    all_data: dict[str, list[HouseDayData]],
    methods: list,
    dr_start_h: int = 18,
    dr_end_h: int = 19,
    min_history: int = 10,
) -> pd.DataFrame:
    """Leave-one-out 방식으로 각 CBL 방법의 MAE 비교."""
    # XGBoost는 전체 데이터로 사전 fit
    all_days = [d for days in all_data.values() for d in days if d.is_weekday]
    for m in methods:
        if hasattr(m, 'fit'):
            try:
                m.fit(all_days, dr_start_h, dr_end_h)
                print(f'  [{m.name}] fit 완료')
            except Exception as e:
                print(f'  [{m.name}] fit 실패: {e}')

    records = []
    for m in methods:
        for house_id, day_data in all_data.items():
            wd = [d for d in day_data if d.is_weekday]
            if len(wd) < min_history + 1:
                continue
            for i in range(min_history, len(wd)):
                history = wd[max(0, i - min_history):i]
                try:
                    cbl = m.calc_cbl(history, dr_start_h, dr_end_h)
                except Exception:
                    continue
                actual = wd[i].window_kwh(dr_start_h, dr_end_h)
                records.append({
                    'method':     m.name,
                    'house_id':   house_id,
                    'cbl_kwh':    round(cbl, 4),
                    'actual_kwh': round(actual, 4),
                    'error':      round(cbl - actual, 4),
                    'abs_error':  round(abs(cbl - actual), 4),
                })

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    return (
        df.groupby('method')
        .agg(MAE=('abs_error', 'mean'), 편향_kWh=('error', 'mean'),
             std=('abs_error', 'std'), 샘플수=('abs_error', 'count'))
        .round(4)
    )
