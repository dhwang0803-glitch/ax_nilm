"""가전별 ON 비율 검증 — always_on 고정 대상 확인용.

Colab에서 실행. 환경 설치·GCS 인증·repo 클론은 colab_gcs_train.ipynb 1~3셀 먼저 실행.
"""
import sys, os
import numpy as np
import yaml
import gcsfs
from google.colab import auth

# ── 환경 ──────────────────────────────────────────────────────────────────────
auth.authenticate_user()
gcs = gcsfs.GCSFileSystem()

REPO_DIR = "/content/ax_nilm"
SRC_DIR  = f"{REPO_DIR}/nilm-engine/src"
CFG_DIR  = f"{REPO_DIR}/nilm-engine/config"
for d in [SRC_DIR, f"{REPO_DIR}/nilm-engine/scripts"]:
    if d not in sys.path:
        sys.path.insert(0, d)

BUCKET_PREFIX = "ax-nilm-data-dhwang0803-us/nilm/training_dev10"
LABEL_PATH    = "ax-nilm-data-dhwang0803-us/nilm/labels/training.parquet"

# 검증 대상 — test house (학습에 쓰지 않은 house로 실측 ON 비율 확인)
CHECK_HOUSES = ["house_067"]

with open(f"{CFG_DIR}/dataset.yaml") as f:
    DATASET_CFG = yaml.safe_load(f)

ws = DATASET_CFG["window"]["size"]
st = DATASET_CFG["window"]["stride"]
ec = DATASET_CFG["window"].get("event_context")
ss = DATASET_CFG["window"].get("steady_stride")

# ── 데이터셋 로드 ──────────────────────────────────────────────────────────────
from acquisition.gcs_loader import GCSNILMDataset
from classifier.label_map import APPLIANCE_LABELS, APPLIANCE_LABELING

print(f"window={ws}, stride={st}, houses={CHECK_HOUSES}")
ds = GCSNILMDataset(
    CHECK_HOUSES,
    gcs_fs=gcs,
    bucket_prefix=BUCKET_PREFIX,
    label_path=LABEL_PATH,
    window_size=ws,
    stride=st,
    event_context=ec,
    steady_stride=ss,
    fit_scaler=False,
)

# ── ON 비율 집계 ───────────────────────────────────────────────────────────────
all_on    = np.zeros(len(APPLIANCE_LABELS), dtype=np.int64)
all_total = np.zeros(len(APPLIANCE_LABELS), dtype=np.int64)

for _agg, _tgt, on_mask, _validity in ds._segments:  # on_mask: (N_APP, n_samples) bool
    all_on    += on_mask.sum(axis=1)
    all_total += on_mask.shape[1]

# ── 출력 ───────────────────────────────────────────────────────────────────────
print(f"\n{'가전':<22} {'ON비율':>8}  {'threshold_kind':<14}  비고")
print("-" * 68)
for i, name in enumerate(APPLIANCE_LABELS):
    if all_total[i] == 0:
        continue
    ratio = all_on[i] / all_total[i]
    kind  = APPLIANCE_LABELING.get(name, {}).get("threshold_kind", "?")

    if kind == "always_on":
        note = "항상ON 고정 대상 ✓" if ratio > 0.90 else "⚠ 실측이 낮음 — 재확인 필요"
    elif ratio > 0.90:
        note = "← ON 비율 높음, always_on 고정 아님 (정상)"
    else:
        note = ""

    print(f"{name:<22} {ratio:>8.3f}  {kind:<14}  {note}")
