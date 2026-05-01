"""군집화 결과 시각화 → PNG 저장."""
import matplotlib
matplotlib.use('Agg')  # 스크립트 실행 시 비대화형 백엔드 (pyplot import 전에 설정)

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import seaborn as sns
from pathlib import Path
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import silhouette_score
from sklearn.cluster import KMeans

# 모듈 로드 시점에 폰트 등록 (캐시 무관하게 직접 로드)
_FONT_PATH = r'C:\Windows\Fonts\malgun.ttf'
fm.fontManager.addfont(_FONT_PATH)
_FONT_PROP = fm.FontProperties(fname=_FONT_PATH)
_FONT_NAME = _FONT_PROP.get_name()


def _setup_font():
    sns.set_style('whitegrid')
    plt.rcParams['font.family'] = 'sans-serif'
    plt.rcParams['font.sans-serif'] = [_FONT_NAME, 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False


def _save(fig: plt.Figure, path: Path, name: str) -> None:
    fig.savefig(path / name, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'  저장: {name}')


def save_all(
    profiles: np.ndarray,
    meta_df: pd.DataFrame,
    labels: np.ndarray,
    output_dir: Path,
) -> None:
    """모든 시각화를 output_dir/plots/ 에 PNG로 저장.

    profiles : (N, 1440)
    meta_df  : house, date_dt, house_size, is_weekend, temperature 포함
    labels   : (N,) 클러스터 ID
    """
    _setup_font()
    plots_dir = output_dir / 'plots'
    plots_dir.mkdir(parents=True, exist_ok=True)
    print('시각화 저장 시작...')

    n_clusters = len(np.unique(labels))
    palette = sns.color_palette('tab10', n_clusters)
    hours_axis = np.arange(1440) / 60

    # ── 1. 가구 규모 × 요일 프로파일 ─────────────────────────────────────────
    fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=False)
    for ax, size in zip(axes, ['1인', '2~3인', '4인+']):
        for is_we, label, color in [(False, '평일', 'steelblue'), (True, '주말', 'tomato')]:
            mask = (meta_df['house_size'] == size) & (meta_df['is_weekend'] == is_we)
            if mask.sum() == 0:
                continue
            ax.plot(hours_axis, profiles[mask.values].mean(axis=0),
                    color=color, label=label, linewidth=1.5)
        ax.set_title(f'{size} 가구'); ax.set_xlabel('시간 (h)'); ax.set_ylabel('전력 (W)')
        ax.set_xticks(range(0, 25, 4)); ax.legend()
    plt.suptitle('가구 규모·요일별 평균 전력 프로파일', fontsize=13, y=1.01)
    plt.tight_layout()
    _save(fig, plots_dir, '01_profile_by_size_weekday.png')

    # ── 2. PCA Scree Plot ────────────────────────────────────────────────────
    hourly = profiles.reshape(len(profiles), 24, 60).mean(axis=2)
    X_scaled = StandardScaler().fit_transform(hourly)
    pca_full = PCA().fit(X_scaled)
    cumvar = np.cumsum(pca_full.explained_variance_ratio_)

    fig, axes = plt.subplots(1, 2, figsize=(12, 4))
    axes[0].plot(range(1, min(21, len(cumvar) + 1)), cumvar[:20], marker='o', ms=4)
    axes[0].axhline(0.9, color='r', ls='--', label='90%')
    axes[0].set_xlabel('PC 수'); axes[0].set_ylabel('누적 분산'); axes[0].set_title('Scree Plot')
    axes[0].legend()
    axes[1].bar(range(1, 11), pca_full.explained_variance_ratio_[:10])
    axes[1].set_xlabel('PC'); axes[1].set_ylabel('분산 비율'); axes[1].set_title('개별 PC 기여도')
    plt.tight_layout()
    _save(fig, plots_dir, '02_pca_scree.png')

    # ── 3. Elbow + Silhouette ────────────────────────────────────────────────
    k_range = range(2, 10)
    inertias, silhouettes = [], []
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        lbl = km.fit_predict(X_scaled)
        inertias.append(km.inertia_)
        silhouettes.append(silhouette_score(X_scaled, lbl, sample_size=1000, random_state=42))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))
    ax1.plot(list(k_range), inertias, marker='o')
    ax1.set_xlabel('k'); ax1.set_ylabel('Inertia'); ax1.set_title('Elbow')
    ax2.plot(list(k_range), silhouettes, marker='o', color='orange')
    ax2.axvline(n_clusters, color='r', ls='--', label=f'선택 k={n_clusters}')
    ax2.set_xlabel('k'); ax2.set_ylabel('Silhouette Score'); ax2.set_title('Silhouette Score')
    ax2.legend()
    plt.tight_layout()
    _save(fig, plots_dir, '03_elbow_silhouette.png')

    # ── 4. PCA 산점도 ────────────────────────────────────────────────────────
    X_pca = PCA(n_components=2).fit_transform(X_scaled)
    fig, ax = plt.subplots(figsize=(9, 6))
    for c in range(n_clusters):
        mask = labels == c
        ax.scatter(X_pca[mask, 0], X_pca[mask, 1],
                   color=palette[c], alpha=0.4, s=15, label=f'C{c} ({mask.sum()}건)')
    ax.set_title('KMeans 군집화 결과 (PCA 2D)'); ax.set_xlabel('PC1'); ax.set_ylabel('PC2')
    ax.legend(markerscale=2, bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    _save(fig, plots_dir, '04_cluster_pca_scatter.png')

    # ── 5. 클러스터별 시간대 소비 패턴 ──────────────────────────────────────
    fig, axes = plt.subplots(1, n_clusters, figsize=(4 * n_clusters, 4), sharey=False)
    if n_clusters == 1:
        axes = [axes]
    for c, ax in enumerate(axes):
        c_profiles = profiles[labels == c]
        h_mat = c_profiles.reshape(-1, 24, 60).mean(axis=2)
        ax.plot(range(24), h_mat.mean(axis=0), color=palette[c], linewidth=2)
        ax.fill_between(range(24),
                        h_mat.mean(axis=0) - h_mat.std(axis=0),
                        h_mat.mean(axis=0) + h_mat.std(axis=0),
                        color=palette[c], alpha=0.2)
        ax.set_title(f'Cluster {c}  ({(labels==c).sum()}건)', fontsize=11)
        ax.set_xlabel('시간 (h)'); ax.set_ylabel('전력 (W)')
        ax.set_xticks(range(0, 24, 4))
    plt.suptitle('클러스터별 시간대 평균 전력 소비 패턴', fontsize=13, y=1.02)
    plt.tight_layout()
    _save(fig, plots_dir, '05_cluster_hourly_patterns.png')

    # ── 6. 사후 분석: 평일/주말 + 가구원수 ──────────────────────────────────
    result_df = meta_df.copy()
    result_df['cluster'] = labels

    cross_week = result_df.groupby(['cluster', 'is_weekend']).size().unstack(fill_value=0)
    cross_week.columns = ['평일', '주말']
    cross_week_pct = cross_week.div(cross_week.sum(axis=1), axis=0)

    cross_size = result_df.groupby(['cluster', 'house_size']).size().unstack(fill_value=0)
    cross_size_pct = cross_size.div(cross_size.sum(axis=1), axis=0)

    fig, axes = plt.subplots(1, 2, figsize=(13, 4))
    cross_week_pct.plot(kind='bar', ax=axes[0], color=['steelblue', 'tomato'], edgecolor='white')
    axes[0].set_title('클러스터별 평일/주말 비율')
    axes[0].set_xlabel('Cluster'); axes[0].set_ylabel('비율')
    axes[0].set_xticklabels(axes[0].get_xticklabels(), rotation=0); axes[0].legend()
    cross_size_pct.plot(kind='bar', ax=axes[1], edgecolor='white')
    axes[1].set_title('클러스터별 가구원수 비율')
    axes[1].set_xlabel('Cluster'); axes[1].set_ylabel('비율')
    axes[1].set_xticklabels(axes[1].get_xticklabels(), rotation=0)
    axes[1].legend(title='가구원수')
    plt.tight_layout()
    _save(fig, plots_dir, '06_cluster_cross_analysis.png')

    # ── 7. 4시간 윈도우별 소비 분포 ──────────────────────────────────────────
    # profiles (N, 1440) → 6개 윈도우 평균 전력 (N, 6)
    n_windows = 6
    win_size  = 1440 // n_windows          # 240분 = 4시간
    win_avg   = profiles.reshape(len(profiles), n_windows, win_size).mean(axis=2)
    win_labels = ['0~4h', '4~8h', '8~12h', '12~16h', '16~20h', '20~24h']

    fig, axes = plt.subplots(1, n_clusters, figsize=(4 * n_clusters, 5), sharey=True)
    if n_clusters == 1:
        axes = [axes]
    for c, ax in enumerate(axes):
        data = win_avg[labels == c]        # (n_samples, 6)
        ax.boxplot(
            [data[:, w] for w in range(n_windows)],
            labels=win_labels,
            patch_artist=True,
            boxprops=dict(facecolor=palette[c], alpha=0.4),
            medianprops=dict(color='red', linewidth=2),
            whiskerprops=dict(color='gray'),
            capprops=dict(color='gray'),
        )
        ax.set_title(f'Cluster {c}  ({(labels == c).sum()}건)', fontsize=11)
        ax.set_xlabel('시간대 윈도우')
        if c == 0:
            ax.set_ylabel('평균 전력 (W)')
        ax.tick_params(axis='x', rotation=30)
    plt.suptitle('클러스터별 4시간 윈도우 소비 분포', fontsize=13, y=1.02)
    plt.tight_layout()
    _save(fig, plots_dir, '07_window_4h_distribution.png')

    print(f'완료. 총 7개 PNG → {plots_dir}')
