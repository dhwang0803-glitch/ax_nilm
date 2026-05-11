# GCS 두 single-region 버킷 설정 Runbook

ADR-007 에 따른 NILM 학습 데이터 cross-region 접근 구성. (ADR-006 의 configurable dual-region 은 GCS 미지원으로 기각 — `docs/context/decisions.md` 참조.)

- **유지**: `gs://ax-nilm-data-dhwang0803` (single `asia-northeast3`, 기존)
- **신규**: `gs://ax-nilm-data-dhwang0803-us` (single `us-central1`)
- **복사량**: ~61 GB (10가구 개발 킷, parquet 5,209 파일)
- **소요 시간**: ~15~30분 (cross-continent GCS-to-GCS, `rsync`)
- **다운타임**: 없음 (원본 무변경)

> 파일명이 `_dualregion_` 인 이유는 원래 ADR-006 기준으로 만들어졌기 때문. 실제 구성은 two-single-region. 필요 시 향후 rename (ADR-007 Follow-up).

---

## 사전 조건

- [ ] 프로젝트 `ax-nilm` 의 `roles/storage.admin`
- [ ] gcloud CLI 최신 (`gcloud components update`)
- [ ] 베이스라인 스냅샷:
  ```bash
  gcloud storage du -sh gs://ax-nilm-data-dhwang0803
  gcloud storage ls -r 'gs://ax-nilm-data-dhwang0803/**' | wc -l
  ```

---

## 1단계 — 신규 버킷 생성

```bash
gcloud storage buckets create gs://ax-nilm-data-dhwang0803-us \
    --project=ax-nilm \
    --location=us-central1 \
    --default-storage-class=STANDARD \
    --uniform-bucket-level-access \
    --public-access-prevention
```

확인:
```bash
gcloud storage buckets describe gs://ax-nilm-data-dhwang0803-us \
    --format="yaml(name,location,locationType,storageClass)"
```
기대: `location: US-CENTRAL1`.

---

## 2단계 — 데이터 복사 (원본 → 신규)

> **주의 (2026-04-24 실제 시행 중 발견한 함정)**: `gcloud storage cp -r "gs://src/**" "gs://dst/"` 는 `/**` 글롭이 디렉토리 구조를 평탄화시켜 **모든 객체가 dst 루트에 같은 파일명으로 덮어씌워짐** (로그에 `Skipping IntraCloudCopyTask ... multiple writes to the same resource`). 5,209 개가 2 개로 줄어드는 대참사. **반드시 `rsync` 를 쓴다.**

```bash
gcloud storage rsync -r --delete-unmatched-destination-objects \
    gs://ax-nilm-data-dhwang0803 \
    gs://ax-nilm-data-dhwang0803-us
```

- `-r`: 재귀
- `--delete-unmatched-destination-objects`: 이전 시도 잔여물 정리해 완전 일치
- cross-continent GCS-to-GCS 는 공용 인터넷 거치지 않고 Google 백본으로 전송되어 빠름 (실측 수십~백 MiB/s 수준)

---

## 3단계 — 정합성 검증

**파일 수**:
```bash
src=$(gcloud storage ls -r 'gs://ax-nilm-data-dhwang0803/**' 2>/dev/null | wc -l)
dst=$(gcloud storage ls -r 'gs://ax-nilm-data-dhwang0803-us/**' 2>/dev/null | wc -l)
echo "src=$src dst=$dst"
[ "$src" = "$dst" ] && echo "COUNT=OK" || echo "COUNT=MISMATCH"
```

**총 용량**:
```bash
gcloud storage du -s gs://ax-nilm-data-dhwang0803 gs://ax-nilm-data-dhwang0803-us
```

**샘플 체크섬** (랜덤 3개 MD5 비교):
```bash
for f in $(gcloud storage ls -r 'gs://ax-nilm-data-dhwang0803/**' | grep '\.parquet$' | shuf -n 3); do
  rel=${f#gs://ax-nilm-data-dhwang0803/}
  s=$(gcloud storage objects describe "$f" --format="value(md5Hash)")
  d=$(gcloud storage objects describe "gs://ax-nilm-data-dhwang0803-us/$rel" --format="value(md5Hash)")
  [ "$s" = "$d" ] && echo "OK  $rel" || echo "FAIL $rel"
done
```

3개 전부 OK 여야 다음 단계로.

---

## 4단계 — IAM 부여

원본 버킷의 `roles/storage.objectViewer` 멤버 목록 확인:
```bash
gcloud storage buckets get-iam-policy gs://ax-nilm-data-dhwang0803 --format=json
```

동일 멤버를 신규 버킷에 부여 (팀원마다 반복):
```bash
gcloud storage buckets add-iam-policy-binding gs://ax-nilm-data-dhwang0803-us \
    --member="user:<팀원이메일>" \
    --role="roles/storage.objectViewer"
```

확인:
```bash
gcloud storage buckets get-iam-policy gs://ax-nilm-data-dhwang0803-us
```

---

## 5단계 — 팀원 접근 검증 (각자 실행)

**로컬/GCE asia** — 변경 없음, 기존 버킷 그대로 사용.

**Colab 사용자 — 신규 버킷 검증**:
```python
from google.colab import auth
auth.authenticate_user()

import pyarrow.dataset as ds
from pyarrow import fs

gcs = fs.GcsFileSystem()
dataset = ds.dataset(
    "ax-nilm-data-dhwang0803-us/nilm/training_dev10",
    filesystem=gcs,
    partitioning=["household_id", "channel", "date"],
)
print(dataset.schema)
```

또는 CLI:
```bash
gcloud storage ls gs://ax-nilm-data-dhwang0803-us/nilm/training_dev10/ | head -5
```

**체크리스트** (팀원별):
- [ ] `dhwang0803@gmail.com` — asia 버킷 기존 경로 유지 확인
- [ ] `dkswndus6988@gmail.com` — Colab us 버킷 접근 확인
- [ ] `jiminxkey@gmail.com` — Colab us 버킷 접근 확인

---

## 6단계 — 팀 공지

> NILM 학습 데이터는 이제 리전별 전용 버킷에서 읽을 수 있습니다.
> - 한국 운영/로컬: `gs://ax-nilm-data-dhwang0803/` (기존, 변경 없음)
> - **Colab (us-central1 고정)**: `gs://ax-nilm-data-dhwang0803-us/` (신규)
>
> 두 버킷 내용은 동일합니다. Colab 사용자는 노트북 경로의 `ax-nilm-data-dhwang0803` 을 모두 `ax-nilm-data-dhwang0803-us` 로 치환하세요 → 대륙 간 egress 0, 속도 ↑. 가이드: `Database/docs/nilm_gcs_access_guide.md`.

---

## 7단계 — 신규 데이터 업로드 시 양쪽 반영

**버킷 레이아웃 규칙** (`Database/docs/nilm_gcs_access_guide.md` §7):
- `nilm/<subset>/` — parquet 만
- `nilm/_manifests/<subset>.json` — ETL sidecar

향후 새 subset(validation, training_full 등) 추가 시 두 버킷 모두에 반영:

```bash
SUBSET=validation  # 예시

# 1) 원본(asia) 에 parquet 업로드
gcloud storage cp -r <local_path>/ gs://ax-nilm-data-dhwang0803/nilm/${SUBSET}/

# 2) 원본(asia) 에 manifest 업로드 (ETL 스크립트가 생성)
gcloud storage cp <local_manifest>.json gs://ax-nilm-data-dhwang0803/nilm/_manifests/${SUBSET}.json

# 3) us 버킷에 두 트리 모두 rsync 반영
gcloud storage rsync -r \
    gs://ax-nilm-data-dhwang0803/nilm/${SUBSET}/ \
    gs://ax-nilm-data-dhwang0803-us/nilm/${SUBSET}/

gcloud storage rsync -r \
    gs://ax-nilm-data-dhwang0803/nilm/_manifests/ \
    gs://ax-nilm-data-dhwang0803-us/nilm/_manifests/
```

ETL 파이프라인에는 이 세 단계를 묶는 헬퍼 스크립트를 추가한다 — ADR-007 Follow-up (`Database/scripts/sync_buckets.sh` 가칭).

---

## 롤백

- 2단계 중 문제 발견: 신규 버킷 비우기/삭제로 즉시 원복 (원본 무변경이라 서비스 영향 없음).
  ```bash
  gcloud storage rm -r gs://ax-nilm-data-dhwang0803-us/**
  gcloud storage buckets delete gs://ax-nilm-data-dhwang0803-us
  ```
- 6단계 이후 rollback 필요하면 공지 철회 후 기존 asia 경로로 회귀. 신규 버킷은 유지해도 비용(월 ~$1.4) 외 부작용 없음.

---

## 완료 조건

- [ ] 1~5단계 전부 OK
- [ ] 팀원 검증 100%
- [ ] ADR-007 Follow-up 의 sync helper 스크립트 main 반영
- [ ] 7단계 절차를 ETL 파이프라인에 내재화
