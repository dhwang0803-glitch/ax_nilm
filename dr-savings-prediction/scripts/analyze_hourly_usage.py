"""타겟 가구 시간대별 가전 사용 빈도 분석 및 시각화.

대상: 채널 수 상위 5가구 (house_067, 049, 054, 011, 017)
출력: models_output/plots/hourly_appliance_usage.png
"""
import matplotlib
matplotlib.use('Agg')

import os
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
from collections import defaultdict
from pathlib import Path

# ── 설정 ─────────────────────────────────────────────────────────────────────
BASE_DIR     = Path(r'C:\Users\juyeon\Desktop\학습데이터-라벨링데이터')
OUTPUT_DIR   = Path(__file__).parent.parent / 'models_output' / 'plots'
TARGET_HOUSES = [
    'house_067', 'house_049', 'house_054', 'house_011', 'house_017',
    'house_015', 'house_035', 'house_046', 'house_065', 'house_002',
]
DR_START_H   = 18   # 시뮬레이션 DR 이벤트 시작 시각
DR_END_H     = 19   # 시뮬레이션 DR 이벤트 종료 시각

# ── 폰트 ─────────────────────────────────────────────────────────────────────
_FONT_PATH = r'C:\Windows\Fonts\malgun.ttf'
fm.fontManager.addfont(_FONT_PATH)
_FONT_NAME = fm.FontProperties(fname=_FONT_PATH).get_name()
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['font.sans-serif'] = [_FONT_NAME, 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def calc_hourly_usage(houses: list[str]) -> dict[int, int]:
    """가구별 parquet에서 시간대별 가전 사용 구간 겹침 수를 계산."""
    hour_count: dict[int, int] = defaultdict(int)

    for house in houses:
        house_path = BASE_DIR / house
        if not house_path.exists():
            print(f'  [경고] {house} 폴더 없음, 건너뜀')
            continue
        for fname in os.listdir(house_path):
            if fname == 'ch01.parquet' or not fname.endswith('.parquet'):
                continue
            df = pd.read_parquet(house_path / fname)
            for _, row in df.iterrows():
                try:
                    st = pd.to_datetime(row['start_time'])
                    et = pd.to_datetime(row['end_time'])
                    for h in range(6, 22):
                        ws = st.replace(hour=h,   minute=0, second=0, microsecond=0)
                        we = st.replace(hour=h+1, minute=0, second=0, microsecond=0)
                        if st < we and et > ws:
                            hour_count[h] += 1
                except Exception:
                    continue
    return dict(hour_count)


def plot_hourly_usage(hour_count: dict[int, int], output_dir: Path) -> None:
    hours  = sorted(hour_count)
    counts = [hour_count[h] for h in hours]
    labels = [f'{h:02d}시' for h in hours]

    colors = [
        '#E74C3C' if DR_START_H <= h < DR_END_H else '#4A90D9'
        for h in hours
    ]

    fig, ax = plt.subplots(figsize=(13, 5))
    bars = ax.bar(labels, counts, color=colors, width=0.6, edgecolor='white', linewidth=0.8)

    # 막대 위 수치
    for bar, cnt in zip(bars, counts):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 50,
            f'{cnt:,}',
            ha='center', va='bottom', fontsize=8.5, color='#333333'
        )

    # DR 이벤트 구간 배경
    dr_idx = hours.index(DR_START_H)
    ax.axvspan(dr_idx - 0.4, dr_idx + 0.4, alpha=0.12, color='#E74C3C', zorder=0)
    ax.axvline(dr_idx - 0.4, color='#E74C3C', linewidth=1.2, linestyle='--', alpha=0.6)
    ax.axvline(dr_idx + 0.4, color='#E74C3C', linewidth=1.2, linestyle='--', alpha=0.6)

    # 범례
    legend_handles = [
        mpatches.Patch(color='#4A90D9', label='일반 시간대'),
        mpatches.Patch(color='#E74C3C', label=f'DR 시뮬레이션 구간 ({DR_START_H:02d}~{DR_END_H:02d}시)'),
    ]
    ax.legend(handles=legend_handles, loc='upper right', fontsize=9)

    ax.set_title(
        f'타겟 가구 시간대별 가전 사용 빈도 (총 {len(TARGET_HOUSES)}가구)',
        fontsize=13, pad=14
    )
    ax.set_xlabel('시간대', fontsize=10)
    ax.set_ylabel('가전 사용 구간 수 (건)', fontsize=10)
    ax.set_ylim(0, max(counts) * 1.15)
    ax.grid(axis='y', linestyle='--', alpha=0.4)
    ax.spines[['top', 'right']].set_visible(False)

    plt.tight_layout()
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / '08_hourly_appliance_usage.png'
    fig.savefig(out_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    print(f'저장 완료: {out_path}')


if __name__ == '__main__':
    print(f'대상 가구: {TARGET_HOUSES}')
    print('시간대별 가전 사용 빈도 계산 중...')
    hour_count = calc_hourly_usage(TARGET_HOUSES)

    print('\n[결과]')
    for h in sorted(hour_count):
        bar = '#' * (hour_count[h] // 500)
        marker = ' <- DR 이벤트' if h == DR_START_H else ''
        print(f'  {h:02d}h: {bar} {hour_count[h]:,}{marker}')

    print('\n시각화 저장 중...')
    plot_hourly_usage(hour_count, OUTPUT_DIR)
