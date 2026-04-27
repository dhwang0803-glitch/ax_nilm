# Event-based Sampling 설계 계획

## 배경

1주 데이터(30Hz, 8 house) 기준 stride=30 전수 슬라이딩 윈도우 시 약 480만 개 윈도우가 생성된다.
대부분은 가전이 켜져 있는 상태 혹은 꺼져 있는 상태의 반복 구간으로, 인접 윈도우 간 차이가 거의 없다.
정보량이 집중되는 **상태 전환 구간**을 중심으로 샘플링하면 데이터를 대폭 줄이면서 학습 품질을  유지할 수 있다.

---

## 기준 데이터: GCS 라벨 파일

**파일**: `gs://ax-nilm-data-dhwang0803-us/nilm/labels/training.parquet`

관련 코드: `src/acquisition/gcs_loader.py` → `load_all_labels_gcs()` / `src/acquisition/loader.py` → `build_active_mask()`

### 사용 컬럼

| 컬럼 | 타입 | 설명 | 샘플링 활용 방식 |
|------|------|------|----------------|
| `start_ts` | timestamp | 해당 가전이 켜진 시각 | **ON 전환점** → 윈도우 생성 기준 |
| `end_ts` | timestamp | 해당 가전이 꺼진 시각 | **OFF 전환점** → 윈도우 생성 기준 |
| `household_id` | str | house ID | house 필터링 |
| `channel` | str | 채널 ID (ch02 등) | 채널 필터링 |
| `date` | str (YYYYMMDD) | 날짜 파티션 | 날짜 범위 필터링 |

> `build_active_mask()`가 `start_ts`/`end_ts` 구간을 30Hz 타임스탬프 배열에 매핑해 ON/OFF boolean 마스크를 생성한다.
> 이 마스크에서 `np.diff`로 0→1 (켜짐), 1→0 (꺼짐) 전환 인덱스를 추출한다.

---

## 샘플링 전략

### 1단계 — 이벤트 윈도우 (Event Windows)

각 채널의 `on_off_mask`에서 전환점을 검출:

```
on_off: [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0]
diff:   [0, 0, 0, 1, 0, 0, 0, 0, 0,-1, 0, 0]
전환점:                ↑ ON (idx=3)          ↑ OFF (idx=9)
```

#### on_off (이진 마스크)

각 시간 스텝에서 기기가 **켜져 있는지(1) / 꺼져 있는지(0)** 를 나타내는 배열.
`build_active_mask()`가 라벨의 `start_ts`~`end_ts` 구간을 30Hz 타임스탬프에 매핑하여 생성한다.

#### diff (1차 차분)

`on_off[t] - on_off[t-1]` — 직전 스텝과의 변화량.

| diff 값 | 의미 |
|---------|------|
| `+1` | OFF → ON 전환 (기기가 켜짐) |
| `-1` | ON → OFF 전환 (기기가 꺼짐) |
| `0` | 상태 변화 없음 |

`np.where(diff == 1)` / `np.where(diff == -1)` 로 전환점 인덱스를 즉시 추출한다.
NumPy 계산: `np.diff(on_off, prepend=0)` 또는 `on_off[1:] - on_off[:-1]`

전환점 기준 `window_size // 2` 오프셋으로 중심을 맞추고, `±event_context` 개 윈도우를 추가 수집:

```
전환점 t에서:
  center_start = t - window_size // 2
  수집 범위: [center_start - event_context*stride,
              center_start + event_context*stride]
```

**파라미터 기본값**: `event_context = 20` (전환점 앞뒤 각 20초 = ±600 샘플)

이벤트 1건당 윈도우 수: `2 × event_context + 1 = 41개`

### 2단계 — 정상 상태 커버리지 (Steady-state Windows)

이벤트 윈도우만 쓰면 다음 가전이 과소 대표된다:
- **냉장고** (일반/김치): 상시 ON, 전환 드묾
- **공유기/셋톱박스**: 거의 항상 ON
- **에어컨**: 긴 ON 구간 중 소비 패턴 변화

#### 왜 과소 대표 문제가 생기나?

이벤트 윈도우는 **전환점 ±20초**만 커버한다.
냉장고처럼 하루 종일 ON인 기기는 전환이 거의 없으므로 이벤트 윈도우가 거의 생성되지 않는다.
학습 데이터에서 냉장고 샘플이 극소수가 되어 모델이 냉장고를 제대로 학습하지 못한다.

#### 해결: 전체 구간 희소 샘플링

이벤트 윈도우와 **무관하게**, 전체 타임라인에서 `steady_stride` 간격으로 균일하게 윈도우를 추가 수집한다.

```
타임라인 (냉장고 — 하루 종일 ON):

|←────────────────── 24시간 ──────────────────→|
 [w]     [w]     [w]     [w]     [w]     [w]
  ↑       ↑       ↑       ↑       ↑       ↑
  20초 간격으로 균일하게 수집 (steady_stride=600)
```

이때 ON 구간이든 OFF 구간이든 stride마다 무조건 뽑는다.
이벤트 윈도우가 이미 커버한 구간과 겹쳐도 중복 수집한다 (학습 다양성 확보).

---

## 예상 데이터 감소량

1주(8 house) 기준:

| 항목 | 수치 |
|------|------|
| 총 원천 샘플 | 30Hz × 604,800초 × 8 = 약 1.45억 개 |
| 현재 윈도우 수 (stride=30) | 약 480만 개 |
| 이벤트 윈도우 (집당 약 300 전환 × 41) | 약 98,400개 |
| 정상 구간 윈도우 (18M / 600 × 8) | 약 240,000개 |
| **이벤트 기반 합계** | **약 340,000개 (약 14배 감소)** |

> 실제 전환 횟수는 house·주차마다 다르므로 첫 실행 시 로그로 확인한다.

---

## 구현 위치

### 추가할 함수

`src/acquisition/dataset.py` 및 `src/acquisition/gcs_loader.py` 공통:

```python
def _event_window_starts(
    on_off_mask: np.ndarray,   # (N_APPLIANCES, n_samples) bool
    validity: np.ndarray,       # (N_APPLIANCES,) bool
    n_samples: int,
    window_size: int,
    stride: int,
    event_context: int,         # 전환점 기준 ±N 윈도우
    steady_stride: int,         # 정상 구간 커버리지 stride
) -> list[int]:
```

### 수정할 파라미터

`NILMDataset.__init__` / `GCSNILMDataset.__init__`에 추가:
- `event_context: int | None = None` — None이면 기존 전수 슬라이딩 동작 유지
- `steady_stride: int | None = None` — None이면 `stride × 20` 자동 설정

### 설정 파일

`config/dataset.yaml` `window` 섹션에 추가:

```yaml
window:
  size: 1024
  stride: 30
  sampling_rate: 30
  event_context: 20     # 전환점 ±20 윈도우 (≈ ±20초)
  steady_stride: 600    # 정상 구간 20초마다 1개
```

### 캐시 설계 변경

- 캐시에는 `_segments`(raw numpy 배열)만 저장 — `window_index`는 저장하지 않음
- `window_index`는 캐시 로드 후 항상 새로 생성 (수십 ms 소요)
- 샘플링 파라미터가 바뀌어도 캐시 재생성 불필요

---

## 윈도우 비율 모니터링 및 불균형 대응

### 실행 시 자동 출력되는 로그

`NILMDataset` / `GCSNILMDataset` 빌드 완료 시 아래 형식으로 실제 수치를 출력한다.

```
[GCSNILMDataset] event_context=20  steady_stride=600  전환점=2,341
  이벤트 윈도우=87,432 / 정상 전용=198,600  → 비율 1:2.3
  총 286,032 windows
```

- **이벤트 윈도우**: 전환점 ±event_context 구간에서 생성된 윈도우 수
- **정상 전용**: steady_stride 샘플링 중 이벤트 윈도우와 겹치지 않는 것

> 이론치(이벤트 ~98,400 / 정상 ~240,000)는 추정값이다. 실제 비율은 house·주차마다 다르므로 로그로 확인한 뒤 대응 전략을 결정한다.

### 불균형 대응 기준

| 실제 비율 | 권장 대응 |
|-----------|-----------|
| 1:3 미만 | 별도 처리 불필요 |
| 1:3 ~ 1:5 | `pos_weight` 또는 `class_weight` 조정 (Weighted Loss) |
| 1:5 이상 | Weighted Loss + 정상 구간 Undersampling 병행 검토 |

**Weighted Loss 적용 예시** (`pos_weight = 실제 비율값`):

```python
# BCE 계열 loss
criterion = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([ratio]))

# CrossEntropy 계열
criterion = nn.CrossEntropyLoss(weight=torch.tensor([1.0, ratio]))
```

> SMOTE는 지양한다 — 시계열 윈도우에 적용 시 물리적으로 불가능한 패턴이 생성될 위험이 있다.

---

## 주의사항 및 검증 계획

1. **냉장고 F1 지표 모니터링**: 전환이 드문 가전의 성능 저하 여부를 `per_appliance` 메트릭으로 확인
2. **event_context 민감도**: 10 / 20 / 30 세 가지로 실험해 최적값 결정
3. **기존 EXP1 결과와 비교**: MAE·F1 지표가 10% 이내 차이면 샘플링 전략 채택 확정
4. **첫 실행 시 전환 횟수 로그 출력**: 예상치(집당 200~400)와 실제 수를 비교

---