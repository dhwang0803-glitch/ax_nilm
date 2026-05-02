# nilm-engine 파일 맵

> 마지막 업데이트: 2026-04-23

---

## 전체 구조

```
nilm-engine/
├── config/          설정 파일
├── datasets/        원천·라벨 데이터 (gitignore)
├── checkpoints/     학습된 모델 가중치 + scaler (gitignore)
├── scripts/         실행 진입점
├── src/             모듈 소스
│   ├── acquisition/ 데이터 수집·전처리
│   ├── features/    특징 추출
│   ├── models/      모델 정의
│   ├── classifier/  22종 가전 레이블
│   └── disaggregator.py  public API
├── docs/            설계 문서·실험 결과
└── agents/          Claude 에이전트 역할 문서
```

---

## config/

| 파일 | 역할 |
|------|------|
| `dataset.yaml` | 본 실험용 설정. 데이터 경로, house split(train/val/test), 윈도우 파라미터, 22종 가전 목록 |
| `dataset_trial.yaml` | 시범 실험 전용. val 없이 train/test만 구성 (house 3개 기준) |
| `train.yaml` | 학습 하이퍼파라미터(epochs, batch, lr 등), EXP1~4 주차별 실험 정의, 스케줄러 설정 |

---

## scripts/

| 파일 | 역할 |
|------|------|
| `train_trial.py` | **시범 실험 전용** 학습 스크립트. val 없이 train → test 평가. `dataset_trial.yaml` 사용 |
| `train_model.py` | 본 실험 학습 스크립트. val 기반 early stopping, MLflow 로깅, EXP 체크포인트 연결 |
| `run_disaggregate.py` | 학습된 모델로 실시간 분해 실행. `.npy` 입력 → JSON 출력 |
| `run_experiment.py` | EXP1~4 순차 실행 자동화 |
| `evaluate.py` | 체크포인트 로드 후 지표(MAE/RMSE/SAE/R²/F1) 재계산 |

---

## src/acquisition/

데이터 수집·로딩·전처리 담당. 외부에서 직접 실행하지 않고 import 전용.

| 파일 | 역할 |
|------|------|
| `loader.py` | parquet 읽기, 날짜 필터, 라벨 파싱, active_inactive 마스크 생성. house 시작일 계산(`get_house_start_date`) |
| `preprocessor.py` | `PowerScaler` — aggregate 전력 기준 StandardScaler. fit/transform/inverse_transform/save/load |
| `dataset.py` | `NILMDataset` — 슬라이딩 윈도우 PyTorch Dataset. week 파라미터로 house별 시작일 기준 자동 날짜 계산. `fit_scaler=True`로 scaler 학습 후 `scaler=` 인자로 test에 재사용 |
| `__init__.py` | 공개 API 정리 |

### 데이터 흐름

```
parquet (원천데이터/{channel}.parquet)
  └─ load_channel_data()   날짜 필터
      └─ NILMDataset        merge(agg + 가전), 슬라이딩 윈도우
          └─ PowerScaler    정규화 (train 기준 fit → test 동일 적용)
```

### datasets/ 디렉토리 구조

```
datasets/
└── house_{id}/
    ├── 원천데이터/
    │   └── ch{N}.parquet   30Hz 전력 시계열 (date_time, active_power, voltage, ...)
    └── 라벨데이터/
        └── ch{N}.parquet   일별 메타·라벨 (name, type, active_inactive 구간)
```

---

## src/features/

| 파일 | 역할 |
|------|------|
| `tda.py` | GUDHI 기반 TDA 특징 추출. `compute_tda_features(window)` → persistence diagram 벡터. `TDA_DIM` 상수 정의 |

---

## src/models/

모두 `(batch, 1, window_size)` 입력 → `(batch, N_APPLIANCES)` 출력.

| 파일 | 역할 |
|------|------|
| `seq2point.py` | Seq2Point (Zhang et al. 2018) 멀티 출력 확장. Conv1d 5층 + FC. 가장 가볍고 빠름 |
| `bert4nilm.py` | BERT4NILM Transformer 기반. 셀프 어텐션으로 장거리 의존성 학습. 가장 무거움 |
| `cnn_tda.py` | **핵심 모델.** CNN + TDA Cross-Attention Hybrid. Confidence Gate로 추론 시 TDA 계산 선택적 수행 (fast/slow path) |

---

## src/classifier/

| 파일 | 역할 |
|------|------|
| `label_map.py` | 22종 가전 레이블 단일 진실 공급원. `APPLIANCE_LABELS`, `N_APPLIANCES`, `get_on_thresholds()` |

---

## src/disaggregator.py

`NILMDisaggregator` public API. 학습된 CNNTDAHybrid 체크포인트 로드 후 슬라이딩 윈도우 추론. Confidence Gate로 TDA 계산 여부 자동 판단.

```python
result = NILMDisaggregator("checkpoints/EXP1_cnn_tda.pt").disaggregate(power_array)
# result: {"전기밥솥": np.ndarray, ...}
```

---

## checkpoints/ (런타임 생성)

| 파일 | 생성 시점 |
|------|----------|
| `{EXP}_{model}.pt` | 학습 완료 시 |
| `{EXP}_{model}_scaler.json` | 학습 완료 시 (train 기준 mean/std 저장) |

---

## 현재 실험 상태

| split | houses | 날짜 기준 |
|-------|--------|----------|
| train | house_011, 015, 016, 017, 033, 039, 054, 063 | EXP별 week N (house 시작일 기준 7일) |
| val | house_049 | 전체 기간 |
| test | house_067 | 전체 기간 |
