# 2026-04-28 오늘 변경 정리

> 이 문서는 nilm-engine 브랜치에서 오늘 작업한 4개 커밋의 핵심 내용을 공부용으로 정리한 것.
> 커밋 순서: 오래된 것 → 최신 순서로 서술.

---

## 1. `feat(dataset)` — event_context 가전별 동적 계산 전환

**커밋**: `1a94b66`  
**파일**: `src/acquisition/dataset.py`, `src/acquisition/gcs_loader.py`, `config/dataset.yaml`

### 배경

기존에는 `event_context`가 YAML에서 읽어온 **단일 정수 값** (예: `event_context: 10`)이었다.
즉, 에어컨이든 전기밥솥이든 관계없이 이벤트 주변 ±10 윈도우를 똑같이 샘플링했다.

문제: 가전마다 **전환점 간격(gap)** 이 크게 다르다.
- 전기밥솥 → gap ≈ 1s (자주 켜고 끔)
- 냉장고(Always-On) → gap = None (거의 꺼지지 않음)
- 에어컨 → gap ≈ 300s (가끔 ON/OFF)

모든 가전에 같은 context를 주면, 희소 가전은 컨텍스트 창이 너무 넓어져 정상 구간이
이벤트 구간으로 오염될 수 있다.

### 해결: `_compute_per_appliance_ctx()`

```python
def _compute_per_appliance_ctx(stride: int, sr: int = 30, cap: int = 30) -> dict[int, int]:
    stride_sec = stride / sr          # 윈도우 1개가 몇 초인지
    ctx: dict[int, int] = {}
    for i, name in enumerate(APPLIANCE_LABELS):
        crit = APPLIANCE_LABELING.get(name)
        if crit is None or crit["gap_seconds"] is None:
            ctx[i] = 3                # Always-On 가전은 최소 3
        else:
            ctx[i] = max(1, min(cap, round(crit["gap_seconds"] / stride_sec / 2)))
    return ctx
```

**공식 이해**:
```
윈도우_수 = gap_seconds / stride_sec / 2
```
- `gap_seconds / stride_sec` = gap이 윈도우 몇 개 분량인지
- `/2` = 전환점 기준 **양쪽(±)** 으로 나눠야 하니까 절반
- `cap=30` 상한, `min=1` 하한으로 클램핑

**예시**:
| 가전 | gap_seconds | stride=30(=1초) | ctx |
|------|-------------|-----------------|-----|
| 전기밥솥 | 1s | 1/1/2=0.5 → 1 | 1 |
| 세탁기 | 10s | 10/1/2=5 | 5 |
| 에어컨 | 300s | 300/1/2=150 → cap | 30 |
| 냉장고(Always-On) | None | — | 3 |

### `_event_window_starts()` 시그니처 변경

```python
# 변경 전
def _event_window_starts(..., event_context: int, ...)

# 변경 후
def _event_window_starts(..., event_context: dict[int, int], ...)
```

내부에서 `ctx = event_context.get(app_idx, 1)` 으로 **가전별** 컨텍스트를 꺼내서 쓴다.

---

## 2. `feat(nilm-engine)` — f1_fix_review 미구현 항목 반영

**커밋**: `d9099e1` (일부)
**파일**: `src/classifier/label_map.py`, `scripts/train_model.py`

> `docs/f1_fix_review.md` 검토 의견을 바탕으로 아래 4가지를 구현함.

### 2-1. per-appliance ON 판정 임계값 교체 (review 0번)

**문제**: 기존에는 가전 type 카테고리(type1~4)에 단일 임계를 부여.

```python
# 기존
_ON_THRESHOLD = { "type1": 30.0, "type2": 20.0, "type3": 50.0, "type4": 5.0 }
```

AI Hub 가이드라인 별첨4 기준과 최대 25배 차이 (에어컨 코드 50W → 실제 2W).
학습 라벨은 ON인데 평가 임계가 훨씬 엄격 → 모델이 잘 예측해도 평가에서 OFF로 뒤집힘.

**수정**: `label_map.py`에 `APPLIANCE_LABELING` dict로 22가전 각각의 threshold_w, 활성 최소 시간, Gap 시간을 정의하고 `get_threshold()`로 조회.

```python
def get_threshold(appliance_name: str) -> float:
    crit = APPLIANCE_LABELING[appliance_name]
    if crit["threshold_kind"] in ("always_on", "relative"):
        return 5.0
    return crit["threshold_w"]

def get_on_thresholds() -> list[float]:
    return [get_threshold(name) for name in APPLIANCE_LABELS]
```

**효과**: 에어컨(50W→2W), 선풍기(30W→2W), 공기청정기(50W→3W) 등 임계가 실제 데이터 라벨링 기준과 정합 → F1 측정의 신뢰도 확보.

---

### 2-2. sqrt-clamp pos_weight (review 1번)

**문제**: 희귀 가전(ON ratio 0.5%)에 pos_weight ≈ 200이 걸리면 BCE gradient가 200배 부풀어 학습 발산 가능.

**수정**: `train_model.py`의 `compute_pos_weight()`:

```python
# 기존 (원안)
pw = off_counts / on_counts.clip(min=1)

# 수정
pw = torch.sqrt(off_counts / on_counts.clamp(min=10)).clamp(max=20.0)
```

- `sqrt`: 극단 스케일 완화 (200 → √200 ≈ 14)
- `clamp(min=10)`: ON 샘플 10개 미만 채널은 신뢰도 낮음 → floor 처리
- `clamp(max=20)`: 안전망

---

### 2-3. dual head BCE (review 2번)

**문제**: mixture 출력 1개에만 BCE를 걸면 gate가 한쪽(0 또는 1)으로 수렴할 때 한쪽 헤드의 gradient가 끊김 (gate collapse).

**수정**: CNN 헤드와 fusion 헤드 각각에 BCE를 부여.

```python
# 기존
loss = bce(pred_mixture, y) + λ * mse

# 수정
loss = bce(cnn_logit, y, pos_weight=pw) \
     + bce(fusion_logit, y, pos_weight=pw) \
     + λ_mse * mse_loss
```

mixture는 추론 시에만 사용. 학습 중에는 두 헤드 모두 항상 supervision을 받음.

---

### 2-4. target 정규화 미적용 (review 4번)

**문제**: aggregate(ch01) 기준 scaler를 22가전 target에도 그대로 적용하면, 5W 냉장고·50W TV가 같은 스케일로 0 근방에 압축 → 회귀 헤드가 trivial-zero 예측에 빠짐.

**수정**: `PowerScaler.transform_target()`이 raw W를 그대로 반환하도록 유지. aggregate 정규화와 target 정규화를 분리.

```python
def transform_target(self, series: np.ndarray) -> np.ndarray:
    return series.astype(np.float32)   # raw W 그대로
```

BCE 분류가 주 손실이므로 target scale 정규화 없이도 학습 가능.

---

## 3. `feat(nilm-engine)` — denoise ablation 실험 설계 + ON 윈도우 모니터링

**커밋**: `d9099e1`  
**파일**: `src/acquisition/gcs_loader.py`, `src/acquisition/dataset.py`, `scripts/colab_gcs_train.ipynb`, `scripts/colab_gcs_ablation.ipynb`

### 2-1. `denoise` 파라미터 추가 (GCSNILMDataset)

```python
class GCSNILMDataset(Dataset):
    def __init__(self, ..., denoise: bool = True):
        ...
        if denoise:
            agg_power = _wavelet_denoise(agg_power)
```

Wavelet denoising이 F1 개선에 실제로 도움이 되는지 ablation으로 검증하려면
`denoise=False`로 끌 수 있어야 한다.

`_week_key` (house별 npz 캐시 파일명) 에도 `denoise` 값을 포함시켜
**denoise 상태가 다른 캐시가 섞이지 않게** 했다. (이 시점엔 `cache_key`에는 미반영 — 후속 버그픽스에서 수정)

### 2-2. per-class ON 윈도우 수 모니터링

이벤트 샘플링 모드(`event_context` 사용)에서 가전별로 학습에 사용되는 ON 윈도우가
**100개 미만이면 경고**를 출력하도록 추가.

```python
print("  per-class ON 윈도우 (center 기준):")
for i, name in enumerate(APPLIANCE_LABELS):
    flag = " ⚠️ <100" if on_win[i] < 100 else ""
    print(f"    {name}: {on_win[i]:,}{flag}")
```

**이유**: 희소 가전(특정 가전 타입)은 ON 구간 자체가 드물어서 100개도 못 모을 수 있다.
이 상태로 학습하면 해당 가전의 분류 성능이 극도로 낮아진다.

### 2-3. 노트북 분리

| 노트북 | 역할 |
|--------|------|
| `colab_gcs_train.ipynb` | 캐시 빌드 셀 제거 → `run_exp_gcs`가 자동으로 처리 |
| `colab_gcs_ablation.ipynb` (신규) | denoise on/off 두 조건 학습 → F1 비교 → 승자를 EXP1으로 승격 |

---

## 4. `refactor(nilm-engine)` — ON 윈도우 로깅 공통 함수 추출 + ablation 중복 제거

**커밋**: `f03c73a`  
**파일**: `src/acquisition/dataset.py`, `src/acquisition/gcs_loader.py`, `scripts/colab_gcs_ablation.ipynb`

### 3-1. `_log_on_window_counts()` 추출

커밋 `d9099e1`에서 `dataset.py`와 `gcs_loader.py` 양쪽에 **동일한 13줄 로직**이 복붙됐다.
이를 `dataset.py`에 함수로 정의하고, `gcs_loader.py`에서 import해서 쓰도록 정리.

```python
# dataset.py에 정의
def _log_on_window_counts(window_index, segments, window_size) -> None: ...

# gcs_loader.py에서 사용
from .dataset import ..., _log_on_window_counts
...
_log_on_window_counts(self._window_index, self._segments, window_size)
```

**DRY 원칙**: 같은 코드가 두 곳에 있으면, 한 곳을 고칠 때 다른 곳을 빠뜨리기 쉽다.

### 3-2. ablation 노트북 중복 제거

`colab_gcs_ablation.ipynb` 안에 `_run_ablation_condition()`이라는 100줄짜리 헬퍼가 있었는데,
이게 `run_exp_gcs()`와 거의 동일한 일을 했다.

```python
# 변경 전: 100줄 _run_ablation_condition() 별도 정의
def _run_ablation_condition(denoise: bool, tag: str):
    # ... run_exp_gcs와 동일한 데이터셋 생성, 학습, 저장 로직 ...

# 변경 후: run_exp_gcs 직접 호출 3줄
run_exp_gcs(cfg, denoise=True,  tag="denoise_on")
run_exp_gcs(cfg, denoise=False, tag="denoise_off")
```

---

## 5. `fix(nilm-engine)` — TDA log NaN + denoise ablation 캐시 오염 버그 수정

**커밋**: `adfe2ad`  
**파일**: `src/features/tda.py`, `src/acquisition/gcs_loader.py`

### 4-1. TDA log NaN 버그 (핵심 버그)

**증상**: 학습 중 `loss=nan`, `f1=0` — 학습이 완전히 붕괴.

**원인**:
```python
# 기존 코드
log_mean = float(np.log10(signal.mean() + 1.0))
log_max  = float(np.log10(signal.max()  + 1.0))
```

`signal`이 z-score 정규화된 값이라 평균이 **0에 가깝고 음수도 된다**.
예: `signal.mean() = -0.8` → `-0.8 + 1.0 = 0.2` (OK)
예: `signal.mean() = -1.5` → `-1.5 + 1.0 = -0.5` → `log10(-0.5) = NaN` ← **문제!**

**수정**:
```python
# 수정 후
log_mean = float(np.log10(max(float(signal.mean()) + 1.0, 1e-6)))
log_max  = float(np.log10(max(float(signal.max())  + 1.0, 1e-6)))
```

`max(..., 1e-6)`으로 최솟값을 보장 → `log10(1e-6) = -6` (NaN 없음).

**왜 이게 학습 붕괴로 이어지나**:
TDA 특징값에 NaN이 하나라도 있으면 → PyTorch 텐서 전체가 NaN → loss = NaN
→ 역전파 시 gradient = NaN → 모든 가중치가 NaN으로 오염 → F1 = 0

### 4-2. ablation 캐시 오염 버그

**증상**: `denoise=True`와 `denoise=False` 실험이 같은 캐시를 쓰고 있어 ablation 결과가 무의미.

**원인**: `cache_key` 계산에서 `denoise` 파라미터가 **누락**됐다.

```python
# 기존 (커밋 d9099e1에서 _week_key에만 denoise 포함, cache_key에는 미포함)
self.cache_key = hashlib.md5(
    f"{sorted(houses)}|{date_range}|{week}|{max_week}|{window_size}|{stride}|{bucket_prefix}|{resample_hz}".encode()
).hexdigest()[:12]

# 수정
self.cache_key = hashlib.md5(
    f"{sorted(houses)}|{date_range}|{week}|{max_week}|{window_size}|{stride}|{bucket_prefix}|{resample_hz}|{denoise}".encode()
).hexdigest()[:12]
```

`cache_key`는 외부에서 TDA 캐시 파일명 등에 참조되는 키다.
`|{denoise}`를 뒤에 붙여서 `denoise=True`와 `denoise=False`가 **다른 캐시를 쓰도록** 분리했다.

---

## 흐름 요약 (공부 포인트)

```
[1] event_context 고정값 → 가전별 동적 값
        gap_seconds / stride_sec / 2 공식으로 계산

[2] f1_fix_review 항목 구현
        per-appliance threshold → 라벨링 기준(PDF 별첨4)과 정합
        sqrt-clamp pos_weight → 희귀 가전 gradient 발산 방지
        dual head BCE → gate collapse 방지, 두 헤드 모두 학습
        target 정규화 분리 → trivial-zero 예측 방지

[3] denoise ablation 준비
        GCSNILMDataset에 denoise 파라미터 추가
        캐시 키에 포함 (오염 방지)
        전용 ablation 노트북 신규 작성

[4] 코드 정리 (DRY)
        중복 13줄 로깅 → _log_on_window_counts() 공통 함수
        100줄 ablation 헬퍼 → run_exp_gcs 직접 3줄 호출

[5] 버그 2개 수정
        ① TDA log NaN: max(..., 1e-6)으로 음수 도메인 방어
        ② ablation 캐시 오염: cache_key에 denoise 추가 (누락됐던 것)
```

### 핵심 교훈

1. **평가 임계는 학습 라벨 기준과 반드시 정합**: 임계 불일치는 모든 ablation 결과를 무의미하게 만든다.
2. **pos_weight 극단값 방어**: 희귀 클래스에 무제한 가중치 → gradient 폭발. sqrt + clamp로 안전하게.
3. **gate collapse 대응**: mixture 출력에만 loss를 걸면 한쪽 헤드가 죽음 → 두 헤드 각각에 supervision.
4. **z-score 정규화 후 log 변환 주의**: 정규화된 신호는 음수 포함 → `+1.0` 오프셋만으로 부족.
5. **캐시 키는 모든 영향 인자를 포함해야**: 파라미터 하나가 빠지면 전혀 다른 데이터가 같은 캐시를 공유.
6. **DRY(Don't Repeat Yourself)**: 복붙 코드는 한쪽만 수정될 때 버그 발생 → 함수로 추출.
7. **ablation 실험 설계**: 비교 조건 간 단 하나의 변수만 달라야 결과를 신뢰할 수 있다.

---

# 2026-04-29 추가 수정

> 4주 연속 학습(EXP1~4) 재실행 전 발견한 설계 결함 및 버그 수정.
> 상세 진단: `docs/2026-04-29_exp_issues_and_fix_plan.md`

---

## 6. Val 설계 결함 수정 — `run_exp_gcs` val week 고정

**파일**: `scripts/colab_gcs_train.ipynb` cell-19

### 문제

`run_exp_gcs`가 train과 val 모두에 `week=week`를 적용했다.

| EXP | train | val (버그) |
|-----|-------|----------|
| EXP1 | 8 houses × week 1 | house_049 × week 1 |
| EXP2 | 8 houses × week 2 | house_049 × week 2 |

EXP1 val과 EXP2 val이 서로 다른 기간 → 포화점 비교 자체가 무의미.

### 수정

```python
# 변경 전
_ds_kwargs = dict(..., week=week)   # train/val 동일

# 변경 후 — train/val 분리
_ds_train_kw = dict(**_ds_common, week=week)   # train: 해당 주차만
_ds_val_kw   = dict(**_ds_common, week=None)   # val: 전체 기간 고정
```

`week=None` → GCSNILMDataset 내부에서 `date_range=None` → 전체 기간 로드.  
**EXP1~4 val이 모두 house_049 전체 기간으로 고정** → 포화점 비교 유효.

---

## 7. NameError 방어 — results 미정의 시 Drive 복원

**파일**: `scripts/colab_gcs_train.ipynb` cell-23

### 문제

런타임 재시작 후 cell-23(EXP2~4 루프)을 단독 실행하면 `results = {}` 초기화 셀(cell-21)을 건너뛰어 `NameError: name 'results' is not defined`.

### 수정

cell-23 상단에 복원 로직 추가:

```python
if "results" not in globals():
    results = {}
    for _exp in ["EXP1", "EXP2", "EXP3", "EXP4"]:
        for _m in MODELS:
            _p = RESULTS_DIR / f"{_exp}_{_m}_metrics.json"
            if _p.exists():
                results[(_exp, _m)] = _json.load(open(_p))
```

완료된 실험 스킵 로직도 추가 → 재시작 후 중간부터 안전하게 재개 가능.

---

## 8. F1 천장 수정 — val 기준 임계값 탐색

**파일**: `scripts/train_model.py` `evaluate()`

### 문제

BCE loss는 계속 하강하는데 F1이 ep5 이후 0.40 근처에서 flat. 분류 임계값이 `logit >= 0.0`으로 고정되어 있어 loss가 내려가도 F1에 반영되지 않음.

### 수정

고정 임계값 제거 → val 데이터 기준 전역 임계값 탐색:

```python
for _thr in np.arange(-1.5, 1.6, 0.1):
    _p  = lo_v >= _thr
    _tp = float((_p & t_on).sum())
    _f  = 2 * _tp / (2 * _tp + _fp + _fn + 1e-8)
    if _f > best_f:
        best_f, best_thr = _f, float(_thr)
```

- 탐색 범위: logit −1.5 ~ +1.5 (sigmoid 0.18 ~ 0.82)
- `best_cls_threshold`를 metrics dict / MLflow에 함께 저장
- 에폭 로그: `val_f1_cls=0.xxx(thr=+0.x)` 형태로 출력

---

## 9. 0 샘플 클래스 pos_weight=0 수정

**파일**: `scripts/train_model.py` `compute_pos_weight()`

### 문제

train 데이터에 한 번도 등장하지 않는 가전(validity=0)은 `on_counts = off_counts = 0` → `sqrt(0/10) = 0` → `pos_weight=0`. BCE에서 ON 샘플 loss weight가 0이 되어 해당 가전을 ON으로 예측하는 학습이 차단됨.

### 수정

```python
total_counts = on_counts + off_counts
pw = torch.sqrt(off_counts / on_counts.clamp(min=10)).clamp(max=20.0)
# train에 유효 샘플이 전혀 없는 클래스 → pos_weight=1.0 (중립)
pw = torch.where(total_counts == 0, torch.ones_like(pw), pw)
```

`total_counts == 0`인 클래스는 pos_weight=1.0으로 중립 처리. loss 마스킹은 `bce_validity`가 별도 처리하므로 이중 처리 없음.

---

## 10. per-appliance RMSE 분석 셀 추가

**파일**: `scripts/colab_gcs_train.ipynb` cell-26, 27 (신규)

RMSE/MAE 비율 ≥ 2.5x인 가전 = 간헐적 대형 오차 발생 가전.  
`evaluate()`가 이미 `per_appliance` dict를 metrics JSON에 저장하므로 별도 학습 코드 수정 없이 JSON 로드만으로 분석 가능.

```python
def show_appliance_rmse(exp_name, model_name, results_dir=None):
    pa = m.get('per_appliance', {})
    rows.sort(key=lambda x: x[1] / x[2], reverse=True)  # 비율 내림차순
    for name, r, a in rows:
        flag = ' ⚠️' if r / a >= 2.5 else ''
        print(f"  {name:<22} {r:>8.1f} {a:>8.1f} {r/a:>6.2f}x{flag}")
```

EXP1~4 재실행 후 이 셀을 실행해 outlier 가전 특정.

---

## 11. 캐시 빌드 셀 수정

**파일**: `scripts/colab_gcs_train.ipynb` cell-18, 21

### 문제

cell-18(캐시 빌드)이 `denoise=True`(기본값)로 빌드하고, val에도 `week=week`를 적용 → 실제 학습에서 사용하는 캐시(denoise=False, val week=None)와 달라 매번 GCS 재다운로드 발생.  
cell-21(EXP1 실행)도 `denoise` 미지정 → ablation 결과(denoise=OFF 승)를 무시하고 denoise=True로 재학습.

### 수정

**cell-18**: train/val을 `(split_name, houses, split_week)` 튜플로 분리, `denoise=False` 명시:

```python
for split_name, houses, split_week in [
    ("train", SPLIT["train"], week),
    ("val",   SPLIT["val"],   None),   # val은 전체 기간 고정
]:
    base = GCSNILMDataset(..., week=split_week, denoise=False, ...)
```

**cell-21**: `run_exp_gcs("EXP1", model_name, denoise=False)` 명시.

### 교훈

캐시 빌드 파라미터와 학습 파라미터가 하나라도 다르면 캐시 히트가 발생하지 않아 GCS 재다운로드가 일어난다. 두 곳을 항상 같은 기준으로 맞춰야 한다.
