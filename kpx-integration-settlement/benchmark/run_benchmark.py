"""전체 벤치마크 실행 스크립트.

사용:
  python -m benchmark.run_benchmark          # 전체 실행
  python -m benchmark.run_benchmark --embedding
  python -m benchmark.run_benchmark --cbl
  python -m benchmark.run_benchmark --arch

결과:
  models_output/benchmark/*.csv   — 수치 결과
  models_output/benchmark/*.png   — 시각화
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.architectures import (
    Hybrid, HybridLLM, PredictionOnly, RuleOnly, evaluate_architectures,
)
from benchmark.cbl_methods import Mid610, Mid810, evaluate_cbl
from benchmark.data_loader import load_all_target_houses
from benchmark.embeddings import (
    StatisticalEmbedder, SentenceTransformerEmbedder, compare_embeddings,
)

_FONT_PATH = r'C:\Windows\Fonts\malgun.ttf'
fm.fontManager.addfont(_FONT_PATH)
plt.rcParams['font.family']      = 'sans-serif'
plt.rcParams['font.sans-serif']  = [fm.FontProperties(fname=_FONT_PATH).get_name(), 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = Path(__file__).parent.parent / 'models_output' / 'benchmark'


def _save(df: pd.DataFrame, name: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUTPUT_DIR / f'{name}.csv')
    print(f'\n[{name}]\n{df.to_string()}')
    print(f'  → {OUTPUT_DIR / name}.csv')


def _plot(df: pd.DataFrame, metric: str, title: str, fname: str) -> None:
    methods = df.index.tolist()
    values  = df[metric].values
    min_val = values.min()
    colors  = ['#E74C3C' if v == min_val else '#4A90D9' for v in values]

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(methods, values, color=colors, width=0.5, edgecolor='white')
    for bar, v in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + max(values) * 0.01,
                f'{v:.4f}', ha='center', va='bottom', fontsize=9)

    ax.set_title(title, fontsize=12, pad=12)
    ax.set_ylabel(metric)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines[['top', 'right']].set_visible(False)
    plt.tight_layout()

    out = OUTPUT_DIR / fname
    plt.savefig(out, dpi=150)
    plt.close()
    print(f'  → {out}')


def _get_cluster_labels(all_data: dict) -> dict[str, int]:
    model_path = (
        Path(__file__).parent.parent.parent
        / 'dr-savings-prediction' / 'models_output' / 'clusterizer.joblib'
    )
    if not model_path.exists():
        print('  [경고] clusterizer.joblib 없음 — 모두 C0 설정')
        return {h: 0 for h in all_data}

    dr_src = Path(__file__).parent.parent.parent / 'dr-savings-prediction'
    sys.path.insert(0, str(dr_src))
    from src.features.cluster_features import ClusterFeaturizer
    clf = ClusterFeaturizer.load(model_path)
    labels = {}
    for house_id, day_data in all_data.items():
        profiles = np.stack([d.profile_1440 for d in day_data])
        ids      = clf.transform(profiles)
        labels[house_id] = int(Counter(ids).most_common(1)[0][0])
    return labels


# ── 임베딩 비교 ───────────────────────────────────────────────────────────────

def run_embedding(all_data: dict) -> None:
    print('\n=== 임베딩 비교 ===')
    embedders = [StatisticalEmbedder(), SentenceTransformerEmbedder()]

    try:
        from benchmark.embeddings import TS2VecEmbedder
        embedders.append(TS2VecEmbedder())
    except ImportError:
        print('  [건너뜀] TS2Vec: pip install ts2vec')

    try:
        from benchmark.embeddings import MOMENTEmbedder
        embedders.append(MOMENTEmbedder())
    except ImportError:
        print('  [건너뜀] MOMENT-small: pip install momentfm')

    df = compare_embeddings(all_data, embedders)
    _save(df.set_index('임베딩 방법'), 'embedding_compare')
    _plot(df.set_index('임베딩 방법'), 'Precision@5',
          '임베딩 방법별 유사 날 검색 정확도 (Precision@5)', 'embedding_compare.png')


# ── CBL 비교 ──────────────────────────────────────────────────────────────────

def run_cbl(all_data: dict) -> None:
    print('\n=== CBL 예측 비교 ===')
    methods = [Mid810(), Mid610()]

    try:
        from benchmark.cbl_methods import XGBoostCBL
        methods.append(XGBoostCBL())
    except ImportError:
        print('  [건너뜀] XGBoost: pip install xgboost')

    try:
        from benchmark.cbl_methods import TTMCBL
        methods.append(TTMCBL())
    except ImportError:
        print('  [건너뜀] TTM: pip install tsfm_public')

    df = evaluate_cbl(all_data, methods)
    _save(df, 'cbl_compare')
    _plot(df, 'MAE', 'CBL 예측 방법별 MAE (kWh)', 'cbl_compare.png')


# ── 아키텍처 비교 ─────────────────────────────────────────────────────────────

def run_arch(all_data: dict) -> None:
    print('\n=== 아키텍처 비교 ===')
    cluster_labels = _get_cluster_labels(all_data)
    archs = [RuleOnly(), Hybrid(), HybridLLM()]

    try:
        archs.insert(1, PredictionOnly())
    except Exception as e:
        print(f'  [건너뜀] PredictionOnly — {e}')

    df = evaluate_architectures(all_data, cluster_labels, archs)
    _save(df, 'arch_compare')
    _plot(df, 'MAE', '아키텍처별 CBL 예측 MAE (kWh)', 'arch_compare.png')


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--embedding', action='store_true')
    parser.add_argument('--cbl',       action='store_true')
    parser.add_argument('--arch',      action='store_true')
    args = parser.parse_args()

    run_all = not any([args.embedding, args.cbl, args.arch])

    print('=== 데이터 로딩 ===')
    all_data = load_all_target_houses()
    print(f'로드 완료: {len(all_data)}개 가구')

    if run_all or args.embedding:
        run_embedding(all_data)
    if run_all or args.cbl:
        run_cbl(all_data)
    if run_all or args.arch:
        run_arch(all_data)

    print('\n=== 완료 ===')
    print(f'결과 저장 위치: {OUTPUT_DIR}')


if __name__ == '__main__':
    main()
