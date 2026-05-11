"""
라벨링 계획서용 I-V 궤적 패턴 이미지 일괄 저장
docs/labeling_criteria/iv_patterns/ 에 가전별 PNG 저장
"""

import json, os, csv, math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from collections import defaultdict

DATA_DIR  = os.path.dirname(os.path.abspath(__file__))
DIR_2017  = os.path.join(DATA_DIR, "2017")
OUT_DIR   = os.path.join(DATA_DIR, "..", "docs", "labeling_criteria", "iv_patterns")
os.makedirs(OUT_DIR, exist_ok=True)

FREQ  = 30_000
CYCLE = 500   # 30000Hz / 60Hz

COLORS = {
    "off-on":    "#4C72B0", "high":      "#DD3A3A", "medium":    "#E8852A", "low":       "#2CA02C",
    "highcool":  "#1F77B4", "highfan":   "#17BECF", "lowcool":   "#6BAED6", "lowfan":    "#9EDAE5",
    "highhot":   "#D62728", "highheat":  "#FF7F0E", "highwarm":  "#FFBB78",
    "lowhot":    "#8C564B", "lowheat":   "#C49C94", "lowwarm":   "#BCBD22",
    "mediumhot": "#E377C2", "noheat":    "#7F7F7F", "charging":  "#9467BD", "regular":   "#17BECF",
}

ORDER = {
    "Air Conditioner": ["highcool", "highfan", "lowcool", "lowfan"],
    "Fan":             ["high", "medium", "low"],
    "Hairdryer":       ["highhot", "highwarm", "highheat", "highcool",
                        "mediumhot", "lowhot", "lowwarm", "lowheat", "lowcool", "noheat"],
    "Microwave":       ["high", "medium", "regular"],
    "Vacuum":          ["off-on"],
    "Washing Machine": ["off-on"],
    "Fridge":          ["off-on"],
}

TARGET_APPLIANCES = list(ORDER.keys())


def load_csv(path, max_samples=90_000):
    currents, voltages = [], []
    with open(path, newline="") as f:
        for i, row in enumerate(csv.reader(f)):
            if i >= max_samples: break
            if len(row) < 2: continue
            currents.append(float(row[0]))
            voltages.append(float(row[1]))
    return currents, voltages


def load_meta():
    result = defaultdict(lambda: defaultdict(list))
    for mf in ["meta_2014.json", "meta_2017.json"]:
        with open(os.path.join(DATA_DIR, mf), encoding="utf-8") as f:
            for item in json.load(f):
                t = item["meta"]["appliance"]["type"]
                s = item["meta"]["appliance"]["status"]
                result[t][s].append(item["id"])
    return result


def plot_iv_grid(appliance, status_ids, n_cycles=1, skip_cycles=5):
    statuses = [s for s in ORDER.get(appliance, sorted(status_ids)) if s in status_ids]
    n = len(statuses)
    if n == 0:
        return

    ncols = min(n, 5)
    nrows = math.ceil(n / ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(3.5 * ncols, 3.5 * nrows), squeeze=False)
    fig.suptitle(f"{appliance} — I-V 궤적 (상태별)", fontsize=13, fontweight="bold")

    for idx, status in enumerate(statuses):
        ax = axes[idx // ncols][idx % ncols]
        file_id = status_ids[status][0]
        csv_path = os.path.join(DIR_2017, f"{file_id}.csv")
        if not os.path.exists(csv_path):
            ax.set_visible(False)
            continue

        currents, voltages = load_csv(csv_path)
        if not currents:
            ax.set_visible(False)
            continue

        start = skip_cycles * CYCLE
        end   = start + n_cycles * CYCLE
        i_seg = currents[start:end]
        v_seg = voltages[start:end]

        i_rms = (sum(x**2 for x in i_seg) / len(i_seg)) ** 0.5
        p_avg = sum(a * b for a, b in zip(i_seg, v_seg)) / len(v_seg)

        color = COLORS.get(status, "#333333")
        ax.plot(v_seg, i_seg, color=color, linewidth=1.0, alpha=0.85)
        ax.fill(v_seg, i_seg, color=color, alpha=0.10)
        ax.set_title(status, fontsize=9, fontweight="bold", color=color,
                     bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, alpha=0.8))
        ax.set_xlabel("전압 (V)", fontsize=7)
        ax.set_ylabel("전류 (A)", fontsize=7)
        ax.tick_params(labelsize=6)
        ax.grid(True, alpha=0.25, linewidth=0.4)
        ax.text(0.02, 0.98, f"RMS {i_rms:.3f}A | {p_avg:.1f}W",
                transform=ax.transAxes, fontsize=6.5, va="top",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="white", alpha=0.7))

    # 빈 subplot 숨기기
    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    plt.tight_layout()
    safe = appliance.replace(" ", "_").replace("/", "_")
    out = os.path.join(OUT_DIR, f"{safe}_IV.png")
    plt.savefig(out, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  저장: {out}")


def main():
    korean = [f.name for f in fm.fontManager.ttflist
              if any(k in f.name for k in ["Apple SD Gothic Neo", "AppleGothic", "Malgun", "NanumGothic"])]
    if korean:
        plt.rcParams["font.family"] = korean[0]
    plt.rcParams["axes.unicode_minus"] = False

    meta = load_meta()
    for appliance in TARGET_APPLIANCES:
        if appliance not in meta:
            print(f"  [{appliance}] 데이터 없음, 스킵")
            continue
        print(f"[{appliance}] 그리는 중...")
        plot_iv_grid(appliance, meta[appliance])

    print(f"\n완료! 저장 위치: {OUT_DIR}/")


if __name__ == "__main__":
    main()
