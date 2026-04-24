# NILM 데이터 GCS 접근 가이드 (팀원용)

AI Hub 71685 **전기 인프라 지능화를 위한 가전기기 전력 사용량 데이터**를 GCS에서 읽어 NILM 엔진 학습/실험에 사용하기 위한 가이드.

---

## 0. 요약

| 구분 | 용도 | 네트워크 | 로컬 디스크 |
|------|------|----------|-------------|
| **방식 1 — 스트리밍** | EDA, 데이터 탐색, 일회성 실험 | 매번 발생 | 0 GB |
| **방식 2 — 파티션 캐시** | 반복 학습 (권장) | 1회만 | 필요한 부분만 |

결정 기준: **같은 데이터로 에폭 2회 이상 돌릴 거면 방식 2**. EDA만 할 거면 방식 1.

---

## 1. 최초 1회 셋업

### 1.1 GCS 접근에 필요한 정보

| 항목 | 값 |
|------|-----|
| 항목 | 값 |
|------|-----|
| GCP 프로젝트 | `ax-nilm` |
| 버킷 (한국 / 로컬·GCE `asia-northeast3`) | `ax-nilm-data-dhwang0803` |
| 버킷 (Colab / GCE `us-central1`) | `ax-nilm-data-dhwang0803-us` |
| 데이터 경로 | `gs://<본인 런타임 리전에 맞는 버킷>/nilm/training_dev10/` |

> **왜 두 버킷?**: 팀원 Colab 런타임이 `us-central1` 로 고정이고 운영 인프라는 `asia-northeast3` 에 있다. 이 두 리전을 묶는 configurable dual-region 은 GCS 허용 목록에 없어서(ADR-002 기각, ADR-003 확정) **같은 데이터를 두 single-region 버킷에 병렬 보존**한다. 각자 자기 리전에 맞는 버킷을 쓰면 양쪽 모두 in-region read = **$0 egress**. 두 버킷 내용은 rsync 로 동기화 유지 (`Database/docs/gcs_dualregion_migration.md` §7).

> **선행 조건**: 본인의 Google 계정이 버킷에 이미 **IAM 권한**(`roles/storage.objectViewer`)으로 등록돼 있음. 프로젝트 관리자에게 확인.

### 1.2 gcloud CLI 설치

- **Windows**: https://cloud.google.com/sdk/docs/install-sdk#windows 공식 설치 프로그램
- **macOS**: `brew install --cask google-cloud-sdk` 또는 공식 설치 프로그램
- **Linux**: `curl https://sdk.cloud.google.com | bash` 또는 패키지 매니저

설치 확인:
```bash
gcloud --version
```

### 1.3 Google 계정 로그인

```bash
# 1) 기본 인증 (gcloud 명령용)
gcloud auth login

# 2) 애플리케이션 기본 인증 (Python 라이브러리용 — pyarrow 등이 이걸 씀)
gcloud auth application-default login

# 3) 프로젝트 설정
gcloud config set project ax-nilm
```

> **Windows Git Bash에서 `python: not found` 에러가 뜨면**:
> ```bash
> export CLOUDSDK_PYTHON="/c/Users/<본인>/anaconda3/python.exe"
> ```
> 를 `.bashrc`에 추가. 맥/리눅스는 해당 없음.

### 1.4 Python 환경

```bash
# 필수 패키지
pip install pyarrow>=15 pandas numpy

# PyTorch로 학습할 경우
pip install torch
```

### 1.5 접근 검증

```bash
# 버킷 목록 시도 — 성공하면 권한 OK
gcloud storage ls gs://ax-nilm-data-dhwang0803/nilm/training_dev10/ | head -5
```

성공 시 가구별 파티션 경로가 출력됨. `AccessDenied` 나면 IAM 권한을 관리자에게 요청.

---

## 2. 데이터셋 구조 (알아두면 좋음)

### 2.1 10가구 개발 킷 (현재 업로드된 데이터)

- 약 **5,208개 parquet 파일 / 총 61 GB**
- 2023-09-22 ~ 2023-12-17 (약 3개월)
- 30 Hz 샘플링, 단위 W (active power 등 11개 컬럼)

### 2.2 포함 가구 10개 (다양성 최대화로 선정)

| house | 채널 수 | 가구원 | 주거형 | 평형 |
|-------|---------|--------|--------|------|
| house_011 | 18 | 2-3인 | 다세대 | 85m² 미만 |
| house_015 | 17 | 1인 | 다세대 | 85m² 미만 |
| house_016 | 12 | 1인 | **단독** | 85m² 미만 |
| house_017 | 19 | 2-3인 | 다세대 | 85m² 이상 |
| house_033 | 14 | 4인 이상 | 다세대 | 85m² 미만 |
| house_039 | 12 | 1인 | 다세대 | 85m² 이상 |
| house_049 | 19 | 4인 이상 | 다세대 | 85m² 이상 |
| house_054 | 19 | 4인 이상 | 다세대 | 85m² 이상 |
| house_063 | 16 | 4인 이상 | **단독** | 85m² 미만 |
| house_067 | 22 | 4인 이상 | 다세대 | 85m² 이상 |

### 2.3 파티션 구조 (Hive 스타일)

```
training_dev10/
  household_id=house_011/
    channel=ch01/
      date=20231004/
        part-0.parquet
      date=20231005/
        part-0.parquet
      ...
    channel=ch02/...
  household_id=house_015/...
```

- **ch01**: 메인 분전반 (집 전체 합)
- **ch02 ~ ch23**: 개별 가전 (TV, 냉장고, 세탁기 등 22종)
- 가전↔채널 매핑은 **가구마다 다름** (한 집의 ch05가 다른 집 ch05와 같은 가전 아님) → 라벨 JSON 메타 참조

### 2.4 CSV 컬럼 (= parquet 컬럼)

| 컬럼 | 타입 | 단위 |
|------|------|------|
| `date_time` | timestamp(ms) | — |
| `active_power` | float32 | W |
| `voltage` | float32 | V |
| `current` | float32 | A |
| `frequency` | float32 | Hz |
| `apparent_power` | float32 | VA |
| `reactive_power` | float32 | var |
| `power_factor` | float32 | 0~1 |
| `phase_difference` | float32 | deg |
| `current_phase` | float32 | deg |
| `voltage_phase` | float32 | deg |

일 파일당 30 Hz × 86,400초 = **2,592,000 행**.

---

## 3. 방식 1 — GCS 직접 스트리밍

**언제 쓸지**: 아직 어떤 가구/가전을 쓸지 결정 안 했거나, 한두 번 돌려볼 실험

> **아래 코드 예시는 기본값으로 `ax-nilm-data-dhwang0803` (asia-northeast3) 를 사용.** Colab 사용자는 경로의 `ax-nilm-data-dhwang0803` 을 모두 `ax-nilm-data-dhwang0803-us` 로 치환하면 in-region 접근이 된다. 두 버킷 내용은 동일.

### 3.1 필수 import

```python
import pyarrow.dataset as ds
from pyarrow import fs

gcs = fs.GcsFileSystem()  # ADC 자동 인식
```

### 3.2 전체 dataset 핸들 생성 (실제 전송 거의 없음)

```python
dataset = ds.dataset(
    "ax-nilm-data-dhwang0803/nilm/training_dev10",
    filesystem=gcs,
    partitioning=["household_id", "channel", "date"],
)
print(dataset.schema)
```

### 3.3 필요 부분만 필터해서 읽기 (파티션 pruning)

```python
# 예: house_011의 ch01(메인) + ch21(냉장고) 특정 날짜
table = dataset.to_table(
    filter=(ds.field("household_id") == "house_011") &
           (ds.field("channel").isin(["ch01", "ch21"])) &
           (ds.field("date") >= "20231101") &
           (ds.field("date") <= "20231107")
)
df = table.to_pandas()
print(df.shape, df.head())
```

→ 해당 파티션 파일만 GCS에서 네트워크로 가져옴. 나머지 수천 개는 건드리지도 않음.

### 3.4 배치 단위 스트리밍 iteration (학습 시)

```python
scanner = dataset.scanner(
    filter=(ds.field("household_id") == "house_017"),
    batch_size=65_536,  # 행 단위
)
for batch in scanner.to_batches():
    # batch는 pyarrow.RecordBatch
    # PyTorch tensor로 변환해 모델에 feed
    ...
```

### 3.5 PyTorch DataLoader 연동

```python
import torch
from torch.utils.data import IterableDataset

class NilmStream(IterableDataset):
    def __init__(self, filter_expr):
        self.filter = filter_expr
    def __iter__(self):
        scanner = dataset.scanner(filter=self.filter, batch_size=4096)
        for batch in scanner.to_batches():
            # 예: (active_power, label) 튜플
            ap = torch.from_numpy(batch["active_power"].to_numpy())
            yield ap

loader = torch.utils.data.DataLoader(
    NilmStream(ds.field("household_id") == "house_011"),
    batch_size=None,  # 이미 배치임
    num_workers=0,   # IterableDataset + GCS는 main-thread 권장
)
```

### 3.6 주의 — 반복 에폭 시 비용

- 매 에폭마다 GCS에서 **같은 바이트를 재전송**
- Egress $0.12/GB × (데이터 크기 × 에폭 수)
- 예: 1 GB 데이터 30에폭 = 30 GB 전송 = **$3.60**
- 학습 루프 몇 번 돌릴 예정이면 **방식 2**로 전환

---

## 4. 방식 2 — 필요 파티션 로컬 캐시 + 로컬 학습 (권장)

**언제 쓸지**: 여러 에폭 / 여러 실험 반복. 사실상 실제 학습 대부분이 여기에 해당.

### 4.1 파티션 단위 다운로드 (gcloud CLI)

```bash
# 예: house_011, house_017의 냉장고(ch21) 3개월치 전체
mkdir -p ~/nilm_cache

gcloud storage cp -r \
  gs://ax-nilm-data-dhwang0803/nilm/training_dev10/household_id=house_011/channel=ch21 \
  ~/nilm_cache/household_id=house_011/channel=ch21

gcloud storage cp -r \
  gs://ax-nilm-data-dhwang0803/nilm/training_dev10/household_id=house_017/channel=ch21 \
  ~/nilm_cache/household_id=house_017/channel=ch21
```

- 이미 있는 파일은 **MD5 체크로 자동 skip** (두 번 받아도 과금 0)
- 재개 가능

### 4.2 Python에서 파티션 전체 받기 (스크립트화)

```python
import pyarrow.dataset as ds
from pyarrow import fs
from pathlib import Path

gcs = fs.GcsFileSystem()
cache = Path.home() / "nilm_cache"
cache.mkdir(exist_ok=True)

src = ds.dataset(
    "ax-nilm-data-dhwang0803/nilm/training_dev10",
    filesystem=gcs,
    partitioning=["household_id", "channel", "date"],
)

# 받고 싶은 필터
flt = (ds.field("household_id").isin(["house_011", "house_017"])) & \
      (ds.field("channel").isin(["ch01", "ch21"]))   # 메인 + 냉장고

# 필터된 결과를 로컬에 같은 파티션 구조로 저장
ds.write_dataset(
    src.scanner(filter=flt).to_reader(),
    base_dir=str(cache),
    partitioning=["household_id", "channel", "date"],
    format="parquet",
    existing_data_behavior="overwrite_or_ignore",
)
```

### 4.3 로컬에서 학습 (네트워크 0, 빠름)

```python
import pyarrow.dataset as ds
local = ds.dataset(
    "~/nilm_cache",
    partitioning=["household_id", "channel", "date"],
)
# 이후는 3.3 / 3.4 / 3.5 와 완전 동일. gcs 파라미터만 빠짐
```

### 4.4 캐시 관리

- 사용 안 하는 가구는 지워도 OK (`rm -rf ~/nilm_cache/household_id=house_XYZ`)
- 필요 시 다시 `gcloud storage cp`로 받음 (Egress 다시 1회)

---

## 5. 비용 감각 (참고)

원본: `ax-nilm-data-dhwang0803` (`asia-northeast3`). 복사본: `ax-nilm-data-dhwang0803-us` (`us-central1`). **사용 주체가 자기 리전에 맞는 버킷에서 읽으면 egress $0**.

| 읽는 주체 | 사용 버킷 | Egress |
|-----------|-----------|--------|
| GCE VM (`asia-northeast3`) | `…-dhwang0803` | **$0** (in-region) |
| 한국 로컬 머신 | `…-dhwang0803` | $0.12/GB (인터넷) |
| **Colab 무료·기본 티어** (`us-central1` 고정) | `…-dhwang0803-us` | **$0** (in-region) ✅ ADR-003 목적 |
| GCE VM (`us-central1`) | `…-dhwang0803-us` | **$0** (in-region) |

| 작업 | Egress | 비용 |
|------|--------|------|
| 로컬 머신으로 10가구(60 GB) 다운 | 60 GB (인터넷) | **$7.20** |
| 로컬 머신으로 1가구 1가전(≈0.3 GB) 다운 | 0.3 GB (인터넷) | **$0.04** |
| Colab(us-central1) 에서 매 에폭 스트리밍 | — (in-region) | **$0** |
| 로컬 방식 1 스트리밍 × 30에폭 × 1 GB | 30 GB (인터넷) | **$3.60** |

단가: **인터넷 egress $0.12/GB, 같은 리전 GCP 내부 $0**.

**Storage 비용**: single-region Standard 각 ~$0.023/GB/월. 두 버킷 합산 ~$0.046/GB/월 ≈ 61 GB 기준 월 ~$2.8 (단일 asia 운영 대비 $1.4 증액). Colab 팀의 반복 학습 egress 절감분으로 빠르게 상쇄.

- GCE VM 또는 Colab (in-region) 이 실전 권장
- 로컬 머신에서 여러 에폭 돌릴 계획이면 여전히 **방식 2 + 필요한 가구만** 권장

---

## 6. 트러블슈팅

**`pyarrow.lib.ArrowIOError: AccessDenied`**
→ IAM 권한 미부여. 관리자에게 본인 Google 이메일 주소 전달, 버킷에 `roles/storage.objectViewer` 등록 필요.

**`google.auth.exceptions.DefaultCredentialsError`**
→ `gcloud auth application-default login`을 실행 안 했거나 만료됨. 재실행.

**`CLOUDSDK_PYTHON` / `python: not found` (Windows Git Bash)**
→ `export CLOUDSDK_PYTHON="/c/Users/<본인>/anaconda3/python.exe"` 를 `~/.bashrc`에 추가. 새 터미널 열어 반영.

**파티션 필터가 느리거나 전부 전송됨**
→ `ds.dataset(...)`에 `partitioning=["household_id","channel","date"]`가 지정됐는지 확인. 누락 시 pyarrow가 모든 파일 스캔.

**`ArrowInvalid: Could not open Parquet input source '.../*.json'` 등**
→ pyarrow `ds.dataset()` 은 지정된 root 하위의 모든 파일을 parquet 으로 열려고 시도함. dataset root 에 parquet 이 아닌 파일이 섞여 있으면 실패.
→ **이 버킷의 레이아웃 규칙**: dataset subset 경로 (`nilm/<subset>/`) 에는 parquet 만 둔다. ETL sidecar (manifest 등) 는 **`nilm/_manifests/<subset>.json`** 에 격리함. 본 버킷의 `training_dev10` ingestion log 는 `gs://…/nilm/_manifests/training_dev10.json` 에 있음 (§7 레이아웃 참조).

**Egress 비용이 예상보다 큼**
→ 같은 데이터로 여러 에폭이면 방식 2로 전환. GCS Billing 콘솔에서 일별 사용량 확인 가능.

---

## 7. 버킷 레이아웃 · Validation / 전체 Training 확장

### 레이아웃 규칙 (MANDATORY)

```
gs://<bucket>/
└── nilm/
    ├── training_dev10/        ← parquet만 (dataset root)
    │   └── household_id=…/channel=…/date=…/part-0.parquet
    ├── validation/            ← 향후, parquet만
    ├── training_full/         ← 향후, parquet만
    └── _manifests/            ← ETL sidecar 격리 (parquet 아닌 모든 메타)
        ├── training_dev10.json
        ├── validation.json   (예정)
        └── training_full.json (예정)
```

- **Subset root (`nilm/<subset>/`) 에는 parquet 만 둔다.** 비-parquet 파일(JSON 매니페스트, README 등) 은 pyarrow dataset scan 을 깨뜨리므로 `nilm/_manifests/` 로 분리.
- `_manifests/` 는 `_` prefix 로 시작 → 누가 `nilm/` 레벨에서 dataset 잡아도 이중 방어.
- ETL 스크립트는 **`nilm/_manifests/<subset>.json`** 경로를 사용한다 (기존 `nilm/<subset>/manifest.json` 위치는 더 이상 사용하지 않음).

### 현재 업로드 상태

- `nilm/training_dev10/` — 10가구 개발 킷 (parquet 5,208개, 두 버킷 동일)
- `nilm/_manifests/training_dev10.json` — ETL ingestion log (resume 용)

### 향후 확장 (두 버킷 모두에 반영 — ADR-003)

- `gs://ax-nilm-data-dhwang0803{,-us}/nilm/validation/` (16가구, Validation — 예정)
- `gs://ax-nilm-data-dhwang0803{,-us}/nilm/training_full/` (79가구 전체 Training — 예정)
- 대응 manifest: `gs://ax-nilm-data-dhwang0803{,-us}/nilm/_manifests/<subset>.json`

변경/추가 시 본 문서 재공지.

---

## 8. 문의

- IAM / GCP 권한 문제: 프로젝트 관리자
- 데이터 스키마 / 파티션 구조: 본 문서 2절 참조
- `convert_nilm.py` (원본 → parquet 변환기) 코드 문의: 레포 `Database` 브랜치
