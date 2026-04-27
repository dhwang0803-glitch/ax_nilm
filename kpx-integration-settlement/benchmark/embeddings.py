"""임베딩 방법 4종 비교.

방법:
  1. 통계 피처   — 24차원 평균 + 블록 비율 (baseline)
  2. TS2Vec      — contrastive learning (optional: pip install ts2vec)
  3. MOMENT-small — foundation model (optional: pip install momentfm)
  4. SentenceTransformer — 텍스트 변환 후 임베딩 (기존 구현)

평가 지표: Precision@5 — 유사도 top-5 중 실제 18~19시 소비량이 ±30% 이내인 날의 비율
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.data_loader import HouseDayData


class Embedder(Protocol):
    name: str

    def embed(self, profile_1440: np.ndarray, temperature: float | None = None) -> np.ndarray: ...
    def embed_batch(self, profiles: list[np.ndarray], temperatures: list | None = None) -> np.ndarray: ...


# ── 1. 통계 피처 ──────────────────────────────────────────────────────────────

class StatisticalEmbedder:
    name = "통계피처"

    def embed(self, profile_1440: np.ndarray, temperature: float | None = None) -> np.ndarray:
        hourly = profile_1440.reshape(24, 60).mean(axis=1)
        total  = hourly.sum() + 1e-9
        norm_h = hourly / total

        blocks = [
            norm_h[0:6].sum(),    # 자정~06시
            norm_h[6:12].sum(),   # 06~12시
            norm_h[12:18].sum(),  # 12~18시
            norm_h[18:24].sum(),  # 18~24시
        ]
        feat = np.concatenate([
            hourly,
            norm_h,
            [hourly.mean(), hourly.std(), hourly.max(), float(np.argmax(hourly))],
            blocks,
            [temperature or 0.0],
        ])
        n = np.linalg.norm(feat)
        return feat / (n + 1e-9)

    def embed_batch(self, profiles, temperatures=None):
        temps = temperatures or [None] * len(profiles)
        return np.stack([self.embed(p, t) for p, t in zip(profiles, temps)])


# ── 2. TS2Vec ─────────────────────────────────────────────────────────────────

class TS2VecEmbedder:
    name = "TS2Vec"

    def __init__(self, output_dims: int = 320):
        try:
            from ts2vec import TS2Vec
            self._cls   = TS2Vec
            self._dims  = output_dims
            self._model = None
        except ImportError:
            raise ImportError("pip install ts2vec 필요")

    def fit(self, profiles: np.ndarray) -> None:
        """profiles: (N, 1440)"""
        self._model = self._cls(input_dims=1, output_dims=self._dims)
        X = profiles[:, :, np.newaxis]
        self._model.fit(X, verbose=False)

    def embed(self, profile_1440: np.ndarray, temperature: float | None = None) -> np.ndarray:
        if self._model is None:
            raise RuntimeError("fit() 먼저 호출")
        X   = profile_1440[np.newaxis, :, np.newaxis]
        rep = self._model.encode(X, encoding_window='full_series')[0]
        return rep / (np.linalg.norm(rep) + 1e-9)

    def embed_batch(self, profiles, temperatures=None):
        if self._model is None:
            raise RuntimeError("fit() 먼저 호출")
        X    = np.stack(profiles)[:, :, np.newaxis]
        reps = self._model.encode(X, encoding_window='full_series')
        norms = np.linalg.norm(reps, axis=1, keepdims=True)
        return reps / (norms + 1e-9)


# ── 3. MOMENT-small ───────────────────────────────────────────────────────────

class MOMENTEmbedder:
    name = "MOMENT-small"

    def __init__(self):
        try:
            from momentfm import MOMENTForecastingPipeline
            self._model = MOMENTForecastingPipeline.from_pretrained(
                "AutonLab/MOMENT-1-small",
                model_kwargs={"task_name": "embedding"},
            )
        except ImportError:
            raise ImportError("pip install momentfm 필요")

    def _to_512(self, profile_1440: np.ndarray) -> np.ndarray:
        return np.interp(np.linspace(0, 1439, 512), np.arange(1440), profile_1440)

    def embed(self, profile_1440: np.ndarray, temperature: float | None = None) -> np.ndarray:
        import torch
        x = torch.tensor(self._to_512(profile_1440), dtype=torch.float32).unsqueeze(0).unsqueeze(0)
        with torch.no_grad():
            emb = self._model(x).embeddings[0].numpy()
        return emb / (np.linalg.norm(emb) + 1e-9)

    def embed_batch(self, profiles, temperatures=None):
        return np.stack([self.embed(p) for p in profiles])


# ── 4. SentenceTransformer ────────────────────────────────────────────────────

class SentenceTransformerEmbedder:
    name = "SentenceTransformer"

    def __init__(self):
        from src.rag.embedder import PowerPatternEmbedder
        self._embedder = PowerPatternEmbedder()

    def embed(self, profile_1440: np.ndarray, temperature: float | None = None) -> np.ndarray:
        return self._embedder.embed_profile(profile_1440, temperature)

    def embed_batch(self, profiles, temperatures=None):
        temps = temperatures or [None] * len(profiles)
        return np.stack([self.embed(p, t) for p, t in zip(profiles, temps)])


# ── 평가 ──────────────────────────────────────────────────────────────────────

def compare_embeddings(
    all_data: dict[str, list[HouseDayData]],
    embedders: list,
    dr_start_h: int = 18,
    dr_end_h: int = 19,
    top_k: int = 5,
    tolerance: float = 0.3,
) -> pd.DataFrame:
    """Precision@k 기반 임베딩 품질 비교.

    유사도 top-k 중 실제 DR 구간 소비량이 query ±tolerance 이내인 날의 비율.
    """
    rows = []

    for embedder in embedders:
        precisions: list[float] = []

        for house_id, day_data in all_data.items():
            wd = [d for d in day_data if d.is_weekday]
            if len(wd) < top_k + 1:
                continue

            profiles = [d.profile_1440 for d in wd]
            temps    = [d.temperature  for d in wd]

            if hasattr(embedder, 'fit') and getattr(embedder, '_model', None) is None:
                try:
                    embedder.fit(np.stack(profiles))
                except Exception as e:
                    print(f'  [{embedder.name}] fit 실패: {e}')
                    break

            try:
                embs = embedder.embed_batch(profiles, temps)
            except Exception as e:
                print(f'  [{embedder.name}] {house_id} 실패: {e}')
                continue

            for i, query_day in enumerate(wd):
                q_actual = query_day.window_kwh(dr_start_h, dr_end_h)
                if q_actual == 0:
                    continue

                others      = np.delete(embs, i, axis=0)
                other_days  = [wd[j] for j in range(len(wd)) if j != i]
                sims        = others @ embs[i]
                top_idx     = np.argsort(sims)[-top_k:]

                hits = sum(
                    1 for idx in top_idx
                    if abs(other_days[idx].window_kwh(dr_start_h, dr_end_h) - q_actual)
                       / (q_actual + 1e-9) <= tolerance
                )
                precisions.append(hits / top_k)

        rows.append({
            '임베딩 방법':   embedder.name,
            f'Precision@{top_k}': round(float(np.mean(precisions)), 4) if precisions else 0.0,
            '샘플 수':       len(precisions),
        })

    return pd.DataFrame(rows)
