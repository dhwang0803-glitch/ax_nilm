# EXP 실험 문제 진단 및 수정 계획

> 작성일: 2026-04-29  
> 대상: `colab_gcs_train.ipynb` / `colab_gcs_ablation.ipynb`  
> 현재 실험 상태: EXP1(완료) → EXP2(NameError로 결과 미저장) → EXP3~4(미실행)

---

## 발견된 문제 목록

### 문제 1 — Val 설계 결함 (근본 원인, 수정 완료)

**현상**  
EXP마다 val set이 달랐다. `run_exp_gcs`가 train과 val 모두에 `week=week` 필터를 적용함.

| EXP | train | val |
|-----|-------|-----|
| EXP1 | 8 houses × week 1 | house_049 × week 1 |
| EXP2 | 8 houses × week 2 | house_049 × week 2 |
| EXP3 | 8 houses × week 3 | house_049 × week 3 |

**문제점**  
- EXP1 val_mae와 EXP2 val_mae가 서로 다른 데이터셋 기준 → 비교 자체가 무의미  
- 포화점 자동 중단 로직(`saturation_threshold: 0.05`)이 잘못된 기준으로 판단함  
- `train.yaml`의 `eval: date_range: null` 주석("val은 전체 기간") 과 구현이 불일치  

**수정 내용** (`cell-19`, `run_exp_gcs` 함수)  
`_ds_kwargs`를 train/val로 분리:

```python
_ds_train_kw = dict(**_ds_common, week=week)   # train: 해당 주차만
_ds_val_kw   = dict(**_ds_common, week=None)    # val: 전체 기간 고정
```

`week=None` → `gcs_loader.py` 내부에서 `date_range=None` → `dataset.to_table()` (전체 로드)

**수정 효과**  
- EXP1~4 val이 모두 house_049 전체 기간으로 고정 → 포화점 비교 유효  
- EXP1 val 점수가 낮아지는 것은 정상 (week1 학습 → 4주 전체 평가 → honest reflection)  
- EXP2~4에서 새 가전 학습 효과가 val에 올바르게 반영됨

---

### 문제 2 — NameError: name 'results' is not defined (수정 완료)

**현상**  
EXP2/cnn_tda 학습(677초)은 완료되어 Drive에 저장되었으나, 런타임 리셋 후 cell-23을 단독 실행하면:

```
NameError: name 'results' is not defined
```

**원인**  
cell-23(EXP2~4 루프)이 `results = {}` 초기화 셀(cell-21, EXP1 실행)을 건너뛰고 단독 실행될 때 발생.

**수정 내용** (`cell-23` 상단에 추가)  
```python
import json as _json

if "results" not in globals():
    results = {}
    for _exp in ["EXP1", "EXP2", "EXP3", "EXP4"]:
        for _m in MODELS:
            _p = RESULTS_DIR / f"{_exp}_{_m}_metrics.json"
            if _p.exists():
                results[(_exp, _m)] = _json.load(open(_p))
                print(f"  복원: ({_exp}, {_m})")
```

완료된 실험 스킵 로직도 추가:
```python
if (exp_name, model_name) not in results:
    results[(exp_name, model_name)] = run_exp_gcs(...)
else:
    print(f"  스킵 (Drive 메트릭 로드): {exp_name}/{model_name}")
```

---

### 문제 3 — F1 천장 (0.40 고착, 수정 완료)

**현상**  
```
loss: 1.78 → 1.47  (계속 하강)
F1:   0.37 → 0.40  (ep5 이후 flat)
```

**원인**  
BCE 손실은 확률 보정 방향으로 수렴하지만, 분류 임계값이 0.5로 고정되어 있어 F1에 반영되지 않음.  
임계값 최적화 없이는 loss가 내려가도 F1은 오르지 않음.

**수정 내용** (`train_model.py` `evaluate()`)  
고정 임계값 `logit >= 0.0` 제거. val 데이터의 valid 샘플 기준으로 전역 임계값을 탐색:

```python
lo_v = logit_arr[valid_mask]   # 1-D: valid (sample, class) 쌍
best_thr, best_f = 0.0, -1.0
for _thr in np.arange(-1.5, 1.6, 0.1):
    _p  = lo_v >= _thr
    _tp = float((_p & t_on).sum())
    _fp = float((_p & ~t_on).sum())
    _fn = float((~_p & t_on).sum())
    _f  = 2 * _tp / (2 * _tp + _fp + _fn + 1e-8)
    if _f > best_f:
        best_f, best_thr = _f, float(_thr)
best_cls_threshold = best_thr
pred_on_cls = logit_arr >= best_cls_threshold  # (N, 22) — per-class F1에서 재사용
```

- `best_cls_threshold`를 메트릭 dict에 포함 → JSON 저장, MLflow 로깅
- 에폭 로그: `val_f1_cls=0.xxx(thr=+0.x)` 형태로 임계값 함께 출력
- 탐색 범위: logit 기준 -1.5 ~ +1.5 (sigmoid 0.18 ~ 0.82)

---

### 문제 4 — 0 샘플 클래스 pos_weight=0 (수정 완료)

**현상**  
학습 데이터에서 validity=0인 클래스(train houses에 미등장)는 `compute_pos_weight()`에서  
`on_counts = off_counts = 0` → `sqrt(0 / 10) = 0` → pos_weight=0.00.  
`bce_validity`에서 ON 샘플 loss weight가 0이 되어 해당 클래스를 ON으로 예측하는 학습이 차단됨.

**원인 분석**  
```python
# 기존: off_counts=0이면 sqrt(0/10)=0 → pos_weight=0
pw = torch.sqrt(off_counts / on_counts.clamp(min=10)).clamp(max=20.0)
```
`on_counts.clamp(min=10)`은 분모만 보정하고, 분자 `off_counts=0`은 그대로 → 결과가 0.

**수정 내용** (`train_model.py` `compute_pos_weight()`)  
```python
total_counts = on_counts + off_counts
pw = torch.sqrt(off_counts / on_counts.clamp(min=10)).clamp(max=20.0)
# validity=0 for all windows → off_counts=0 → sqrt(0)=0 → ON 샘플에 weight 0 적용 방지
pw = torch.where(total_counts == 0, torch.ones_like(pw), pw)
```

- `total_counts == 0`: train에 유효 샘플이 전혀 없는 클래스 → pos_weight=1.0 (중립)
- loss 마스킹은 `bce_validity`의 validity 마스크가 별도 처리하므로 이중 처리 없음
- on_counts>0 / off_counts=0인 경우(all-ON 클래스)는 기존 clamp(max=20) 로직 유지

---

### 문제 5 — RMSE/MAE 비율 이상 (분석 필요)

**현상**  
```
EXP2 val: MAE=35.73W, RMSE=107.00W → 비율 3.0x
```

정상 범위는 1.3~1.8x. 3배는 특정 가전에서 간헐적으로 큰 오차가 발생한다는 의미.

**가설**  
세탁기(6,914 샘플), 의류건조기(4,805 샘플)가 week2 val에 등장했는데, EXP1 모델이 이 가전들을  
week1 학습 데이터에서 거의 보지 못해 ON/OFF 구간에서 큰 오차 발생.

**val=None 수정 후 예상 변화**  
EXP1 RMSE는 더 높아질 가능성이 있으나 (honest evaluation), EXP2~4에서 해당 가전 학습 후 개선 여부를  
동일 val 기준으로 추적 가능해짐.

**분석 방향 (미적용)**  
per-appliance RMSE를 별도 로깅해 어느 가전이 outlier인지 특정:

```python
for i, name in enumerate(APPLIANCE_NAMES):
    rmse_i = torch.sqrt(((preds[:, i] - targets[:, i]) ** 2).mean()).item()
    mlflow.log_metric(f"val_rmse_{name}", rmse_i)
```

---

## 수정 완료 / 미수정 요약

| # | 문제 | 상태 | 조치 파일 |
|---|------|------|----------|
| 1 | Val 설계 결함 (week 고정 → 전체) | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-19 |
| 2 | NameError (results 미정의) | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-23 |
| 3 | F1 천장 (임계값 최적화 없음) | ✅ 수정 완료 | `train_model.py` `evaluate()` |
| 4 | 0 샘플 클래스 pos_weight=0 | ✅ 수정 완료 | `train_model.py` `compute_pos_weight()` |
| 5 | RMSE/MAE 비율 3x (per-class 분석 없음) | ✅ 수정 완료 | `train_model.py` `main()` |
| 6 | EXP 포화점 자동 중단 로직 | ✅ 제거 완료 | `colab_gcs_train.ipynb` cell-23 |
| 7 | Resume 시 LR 0.001 리셋 | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-19 |

---

### 문제 6 — EXP 포화점 자동 중단 로직 제거 (수정 완료)

**현상**
EXP 간 val MAE 개선율 < 5%이면 학습 중단. 4주치 데이터를 전부 학습하는 구조에서 불필요.
에폭 레벨 `early_stopping_patience=5`가 수렴 시점을 이미 처리하므로 중복.

**수정 내용** (`colab_gcs_train.ipynb` cell-23)
`THR`, 포화점 판단 블록(`if imps: ...`), `break` 전부 제거.

---

### 문제 7 — Resume 시 LR 리셋 (수정 완료)

**현상**
EXP2~4가 이전 EXP 체크포인트를 로드하지만 optimizer는 항상 `lr=0.001`로 새로 생성.
이미 수렴된 모델에 0.001은 너무 커서 기존 가중치를 과하게 덮어쓸 수 있음.

**수정 내용** (`colab_gcs_train.ipynb` cell-19 `run_exp_gcs`)
이전 EXP metrics JSON의 `final_lr`을 읽어 이어받음:

```python
if exp_cfg.get("resume_from"):
    _prev_metrics = RESULTS_DIR / f'{exp_cfg["resume_from"]}_{model_name}_metrics.json'
    if _prev_metrics.exists():
        lr = json.load(open(_prev_metrics)).get("final_lr", lr)
```

학습 종료 시 `optimizer.param_groups[0]["lr"]`를 `final_lr`로 metrics JSON에 저장.

**향후 검토 필요**
ReduceLROnPlateau는 현재 데이터에서 수렴했을 때 LR을 줄임. 다음 EXP는 새로운 주차 데이터가 들어오므로 이전 final_lr이 너무 낮으면 새 패턴 학습이 느려질 수 있음.

| 시나리오 | 특징 |
|---------|------|
| 동적 이어받기 (현재) | 원칙적, 임의 수치 불필요. 단, 새 데이터 학습 속도 저하 가능 |
| 정적 배율 (예: `resume_lr_factor: 0.2`) | 절충안. 배율을 실험으로 튜닝해야 함 |
| 누적 학습 (`week=None`으로 전체 재학습) | 근본 해결책이나 매 EXP마다 학습 시간 증가 |

EXP2~4 재실행 결과로 동적 이어받기 효과 검증 후 필요 시 배율 방식으로 교체.

---

## 다음 실행 순서 (Colab)

1. **EXP1 재실행 필수** — val=None 변경으로 기존 EXP1 메트릭은 다른 기준 (week1 val)
2. **EXP2~4 재실행** — LR 동적 이어받기 적용. EXP1 final_lr → EXP2 초기 LR
3. **미수정 항목 (5)** — EXP 재실행 결과의 per-appliance RMSE 로그 확인 후 outlier 가전 특정
4. **문제 7 검증** — EXP2~4 결과가 이전 실행(0.001 리셋)보다 개선됐는지 확인. 미개선 시 정적 배율 방식 검토

---

## 구조적 문제 가전 분석 (EXP 전반 공통)

> 분석일: 2026-04-29  
> EXP1~4 결과를 관통하는 패턴 — 특정 가전이 모든 EXP에서 지속적으로 높은 RMSE 비율을 보임

### 공통 문제 가전 목록

| 가전 | RMSE 비율 추이 (EXP1→4) | 특성 |
|------|------------------------|------|
| 전기다리미 | 10.9x → 7.2x → 3.1x | 사용 빈도 극히 낮음, 켤 때 순간 고전력 |
| 전기포트 | 3.5~4.0x (고착) | 수십 초짜리 짧은 ON, 타이밍 예측 실패 |
| 전자레인지 | 2.5x → 3.3x (악화) | 짧고 강한 transient |
| 헤어드라이기 | ~2.5x (고착) | 짧은 사용, pos_weight=14 이미 높음 |
| 인덕션 | 2.2~2.5x | RMSE 절대값 최고(247~325W), 전력이 커서 오차도 큼 |

**공통 원인**: 사용 시간이 짧고 전력이 높은 가전 → 모델이 ON 타이밍을 살짝만 틀려도 RMSE 폭발

### 수정 방향 (적용 완료)

#### 방향 A — pos_weight 캡 상향
- 전기다리미(max 20.0), 전기포트(19.93) 이미 현재 상한에 도달
- `clamp(max=20)` → `clamp(max=30~50)` 상향 검토
- **주의**: 과도하게 올리면 false positive 폭증 (precision 하락 감수 여부 판단 필요)

#### 방향 B — 이벤트 윈도우 밀도 증가
- 문제 가전들의 `event_context` 윈도우 캡을 상향해 ON/OFF 전환점 주변 샘플 더 확보
- 전기다리미·전기포트처럼 희귀 이벤트일수록 효과 기대

#### 방향 C — 인덕션 전용 처리
- 절대 전력이 커서(247~325W RMSE) 데이터 증강 없이는 근본 해결 어려움
- 단기: 인덕션 전용 pos_weight 또는 loss 가중치 별도 스케일링
- 장기: 학습 데이터 확보 (house 수 증가)

### 상태 추적

| # | 가전 | 방향 | 상태 |
|---|------|------|------|
| A | 전기다리미·전기포트·헤어드라이기 | pos_weight 캡 상향 (20→50) | ✅ 적용 완료 — `train.yaml` `pos_weight_max: 50`, `train_model.py` `compute_pos_weight(max_weight)` |
| B | 전기다리미·전기포트·전자레인지 | event_context 캡 증가 (30→60) | ✅ 적용 완료 — `dataset.yaml` `event_context: 60` (window + 전체 그룹) |
| C | 인덕션 | loss 스케일링 ×2.0 | ✅ 적용 완료 — `train.yaml` `appliance_loss_scale`, `train_model.py` `masked_weighted_mse(appliance_scale)` |

---

### 문제 8 — TDA 캐시 크기 불일치 IndexError (수정 완료)

**현상**
```
IndexError: index 431536 is out of bounds for dimension 0 with size 365523
```
`_NILMDatasetWithTDA.__getitem__`에서 `self._tda[idx]` 접근 시 발생.

**원인**
`dataset.py`의 `cache_key` 해시가 `event_context`·`steady_stride`를 의도적으로 제외함.  
→ 문제 구조 B에서 `event_context` cap을 30→60으로 올려 윈도우 수가 365,523→439,902로 변경됐으나,  
TDA 캐시 파일명 해시가 동일 → 낡은 캐시(365,523개)를 새 데이터셋(439,902개)에 그대로 로드.

**수정 내용** (`train_model.py` `_NILMDatasetWithTDA.__init__`)
캐시 로드 후 크기 검증 추가. 불일치 시 낡은 캐시 삭제 후 재계산 트리거:
```python
_loaded = torch.load(str(_tda_cache), weights_only=True)
if len(_loaded) == n:
    self._tda = _loaded
    _need_compute = False
else:
    print(f"  TDA 캐시 크기 불일치 ({len(_loaded):,} != {n:,}) → 재계산")
    _tda_cache.unlink()
```

| # | 문제 | 상태 | 조치 파일 |
|---|------|------|----------|
| 8 | TDA 캐시 크기 불일치 IndexError | ✅ 수정 완료 | `train_model.py` `_NILMDatasetWithTDA.__init__` |

---

### 문제 9 — 체크포인트 선택 기준 약점 (α 합산) (수정 완료)

**현상**
체크포인트 선택 기준이 `val_mae` 단독이었음.
리뷰에서 `val_mae - α * val_f1_cls` 합산 방식이 제안됐으나 두 지표의 스케일 차이로 실질적으로 무의미:
- `val_mae` 스케일: 30~150 W (절대값 큼)
- `val_f1_cls` 스케일: 0~1
- α=10이어도 MAE 5W 변동 = f1_cls 0.5 등가 → MAE 변동성에 묻혀버림

**원인**
단위가 다른 두 지표를 α 가중합으로 묶으면 α마다 새 하이퍼파라미터가 생기고 직관도 안 잡힘.

**수정 내용** (`train_model.py` 학습 루프)
α 합산 대신 튜플 우선순위 비교로 교체:

```python
# 변경 전
if val_mae < best_val_mae - 1e-4:
    best_val_mae = val_mae
    best_state   = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    no_improve   = 0

# 변경 후
_f1_cls = val_metrics.get("f1_cls") or 0.0
_score  = (_f1_cls, -val_mae)
if _score > best_score or best_state is None:
    best_score         = _score
    best_val_mae       = val_mae
    best_cls_threshold = val_metrics["best_cls_threshold"]
    best_state         = {k: v.cpu().clone() for k, v in model.state_dict().items()}
    no_improve         = 0
```

- cnn_tda: f1_cls 우선, MAE는 동점 결선 — α 튜닝 불필요
- seq2point / bert4nilm: f1_cls=0.0 고정 → 기존과 동일하게 MAE 기준으로 판정

---

### 문제 10 — evaluate() 임계값 탐색 누설 (수정 완료)

**현상**
`evaluate()` 내부에서 매번 현재 데이터로 `best_cls_threshold`를 탐색함:

```python
for _thr in np.arange(-1.5, 1.6, 0.1):
    ...
    if _f > best_f: best_f, best_thr = _f, _thr
```

- **Val 루프에서**: 에폭마다 val 데이터로 탐색 → `val_f1_cls`가 약간 낙관적 (모델 간 비교는 가능)
- **Final eval에서**: 학습 종료 후 `evaluate(model, val_loader, ...)` 재호출 시 임계값을 다시 탐색 → 이미 best_state로 복원된 모델에 새 임계값이 적용되어 수치가 훈련 중 기록과 달라질 수 있음
- **Test에서 사용 시**: test 데이터 자체로 best_thr를 탐색하면 진짜 누설 — test F1이 1~3% 부풀려짐

**수정 내용** (`train_model.py` `evaluate()`)
`cls_threshold: float | None = None` 인자 추가:

```python
def evaluate(model, loader, model_name, device, cls_threshold: float | None = None):
    ...
    if cls_threshold is None:
        # 현재 데이터에서 탐색 (val loop 전용)
        best_thr, best_f = 0.0, -1.0
        for _thr in np.arange(-1.5, 1.6, 0.1):
            ...
        best_cls_threshold = best_thr
    else:
        # val에서 구한 임계값을 freeze (test/final eval 누설 방지)
        best_cls_threshold = cls_threshold
```

학습 루프에서 `best_cls_threshold`를 보관 후 final eval에 freeze 전달:

```python
final_metrics = evaluate(model, val_loader, args.model, device,
                         cls_threshold=best_cls_threshold)
```

체크포인트에도 함께 저장해 외부 evaluate.py에서 참조 가능하게 함:

```python
torch.save({"model_state": model.state_dict(), "best_cls_threshold": best_cls_threshold}, ckpt_path)
```

---

### 문제 11 — f1_cls / best_cls_threshold 정보 손실 (수정 완료)

**현상**
`val_f1_cls`와 `best_cls_threshold`가 에폭 로그에는 출력되지만 아래 경로에서 누락:
- `_fill_md_row()` → MD 보고서에 `f1_cls` 컬럼 없음
- MLflow 최종 요약 (`mlflow.log_metrics`) 에 `best_val_f1_cls` / `best_cls_threshold` 없음
- 완료 출력 `[완료]` 라인에 f1_cls 미포함
- metrics JSON에는 저장되나 MD·MLflow에서 EXP 간 비교 불가

**수정 내용** (`train_model.py`)

`_fill_md_row`:
```python
_f1_cls_str = f"{metrics['f1_cls']:.3f}" if metrics.get("f1_cls") is not None else "—"
replacement = (
    f"| {model} | {metrics['mae']:.2f} | {metrics['rmse']:.2f} "
    f"| {metrics['sae']:.4f} | {metrics['f1']:.3f} | {_f1_cls_str} | ✅ |"
)
```

MLflow 최종 요약:
```python
_mlflow_final = {"best_val_mae": ..., "best_val_f1": ...}
if final_metrics.get("f1_cls") is not None:
    _mlflow_final["best_val_f1_cls"]   = final_metrics["f1_cls"]
    _mlflow_final["best_cls_threshold"] = final_metrics["best_cls_threshold"]
mlflow.log_metrics(_mlflow_final)
```

완료 출력:
```
[완료] EXP1/cnn_tda  MAE=...  F1=...  F1_cls=0.523(thr=-0.3)
```

---

### 문제 12 — final_lr 미저장으로 Resume LR 이어받기 불가 (수정 완료)

**현상**
문제 7에서 노트북 side (cell-19)는 이전 EXP의 `final_lr`을 metrics JSON에서 읽어 Resume 초기 LR로 사용하도록 수정됐으나, `train_model.py`가 `final_lr`을 metrics JSON에 저장하지 않음.
→ 노트북이 읽으려는 키가 없어 항상 기본값 `lr=0.001`로 리셋됨.

**수정 내용** (`train_model.py` `main()`)
```python
final_metrics["final_lr"] = optimizer.param_groups[0]["lr"]   # EXP resume 시 이어받기용
```

학습 종료 시점의 LR(ReduceLROnPlateau가 조정한 값)을 JSON에 저장 → EXP2~4 resume 시 노트북이 올바르게 읽어감.

---

## 수정 완료 / 미수정 요약 (전체)

| # | 문제 | 상태 | 조치 파일 |
|---|------|------|----------|
| 1 | Val 설계 결함 (week 고정 → 전체) | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-19 |
| 2 | NameError (results 미정의) | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-23 |
| 3 | F1 천장 (임계값 최적화 없음) | ✅ 수정 완료 | `train_model.py` `evaluate()` |
| 4 | 0 샘플 클래스 pos_weight=0 | ✅ 수정 완료 | `train_model.py` `compute_pos_weight()` |
| 5 | RMSE/MAE 비율 3x (per-class 분석 없음) | ✅ 수정 완료 | `train_model.py` `main()` |
| 6 | EXP 포화점 자동 중단 로직 | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-23 |
| 7 | Resume 시 LR 0.001 리셋 (노트북 side) | ✅ 수정 완료 | `colab_gcs_train.ipynb` cell-19 |
| 8 | TDA 캐시 크기 불일치 IndexError | ✅ 수정 완료 | `train_model.py` `_NILMDatasetWithTDA.__init__` |
| 9 | 체크포인트 선택 기준 약점 (MAE 단독) | ✅ 수정 완료 | `train_model.py` 학습 루프 |
| 10 | evaluate() 임계값 탐색 누설 | ✅ 수정 완료 | `train_model.py` `evaluate()` |
| 11 | f1_cls / best_cls_threshold 정보 손실 | ✅ 수정 완료 | `train_model.py` `_fill_md_row` / MLflow |
| 12 | final_lr 미저장 (Resume LR 실제 미동작) | ✅ 수정 완료 | `train_model.py` `main()` |

## 미적용 (P2 — 다음 PR)

| # | 내용 | 기대 효과 |
|---|------|-----------|
| P2-a | per-class 임계값 탐색 (22종 독립 임계) | F1_cls +0.05~0.15 |
| P2-b | 탐색 범위 확장 `[-1.5, +1.5]` → `[-3, +3]` | 희귀 가전 임계 커버 개선 |

> P1(9~12)만 머지해도 보고 honesty는 확보되지만 F1 절대값 자체는 ±0.02 수준.
> 0.4 → 0.55+ 목표는 P2(per-class 임계) 적용 후 가능.
