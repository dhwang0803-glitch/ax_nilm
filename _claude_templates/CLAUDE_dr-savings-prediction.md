# dr-savings-prediction — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 관련 문서

- 전체 아키텍처: [`docs/context/architecture.md`](../docs/context/architecture.md)
- 설계 결정: [`docs/context/decisions.md`](../docs/context/decisions.md)
- 파일 맵: [`docs/context/MAP.md`](../docs/context/MAP.md)
- 요구사항: REQ-003 (DR 의사결정)

## 모듈 역할

**DR 절감 예측 레이어** — 단일 분전반 계량 데이터와 NILM 분해 결과를 입력받아
수요반응(DR) 이벤트 시 절감 잠재량을 예측하고, 경제성 분석·시나리오 비교·맞춤형 권고까지 제공한다.

핵심 목표:
1. **절감 잠재량 예측** — 단기 예측 (30분~24시간), 다중 모델 비교 후 최적 선택
2. **경제성 분석** — 전력단가, 피크 요금, DR 인센티브를 반영한 절감액 산출
3. **시나리오 비교** — 기기별 차단·감축 조합별 절감량/쾌적도 트레이드오프
4. **맞춤형 권고** — 과거 DR 참여 이력 + 예측값 기반 개인화 권고 생성

## 예측 파이프라인 흐름

```
가구 일간 소비 패턴 군집화 (KMeans)
  ↓
cluster_id → 범주형 피처로 변환 (src/features/cluster_features.py)
  ↓
전체 피처 결합 (NILM 분해 결과 + 시간 피처 + cluster_id)
  ↓
단일 예측 모델 학습 (전체 데이터, TimeSeriesSplit)
  ↓
모델 비교 (XGBoost, LightGBM, RandomForest) → 최적 모델 선택
```

**군집화 설계 원칙**:
- 단위: 가구 × 하루 (house × day)
- 군집화 입력: 시간대별 전력 소비 패턴 (비지도)
- 가구 특성(주거형태·가구원수)·요일은 군집화 입력이 아닌 **사후 해석용**
- 군집별 별도 모델 금지 — 데이터 부족 시 과적합 위험, cluster_id 피처로 대체

## 파일 위치 규칙 (MANDATORY)

```
dr-savings-prediction/
├── src/
│   ├── features/         ← 특징 추출 (import 전용)
│   │   ├── extractor.py          ← NILM 출력 → 예측 피처 변환
│   │   ├── time_features.py      ← 시간대·계절·DR 이벤트 플래그
│   │   └── cluster_features.py   ← 군집화 실행 + cluster_id 피처 생성
│   ├── models/           ← 예측 모델 (import 전용)
│   │   ├── xgboost_regressor.py  ← XGBoost 절감 잠재량 예측
│   │   ├── lgbm_regressor.py     ← LightGBM 절감 잠재량 예측
│   │   ├── rf_regressor.py       ← RandomForest 절감 잠재량 예측
│   │   ├── model_selector.py     ← 다중 모델 학습·비교·최적 선택
│   │   ├── scenario_evaluator.py ← 기기 조합 시나리오 평가
│   │   └── recommender.py        ← 맞춤형 권고 생성
│   ├── economics/        ← 경제성 계산 (import 전용)
│   │   ├── tariff.py         ← 전력단가·시간대별 요금 계산
│   │   └── dr_incentive.py   ← DR 인센티브 정산 계산
│   ├── analysis.py       ← 군집화 사후 분석 (클러스터 특성·교차분석) → CSV 저장
│   ├── visualization.py  ← 파이프라인 결과 시각화 → PNG 저장 (scripts/train.py 호출)
│   └── pipeline.py       ← 전체 예측 파이프라인 조합 (import 전용)
├── scripts/
│   ├── train.py              ← 모델 학습 실행 (python scripts/train.py)
│   ├── predict.py            ← 단일 예측 실행 (python scripts/predict.py)
│   └── evaluate.py           ← 모델 성능 평가 실행
├── tests/
│   ├── test_features.py
│   ├── test_models.py
│   ├── test_economics.py
│   └── test_pipeline.py
├── config/
│   ├── model_params.yaml     ← XGBoost 하이퍼파라미터
│   ├── tariff.yaml           ← 전력요금 설정
│   └── .env.example          ← 필요 환경변수 목록
└── docs/
    ├── feature_spec.md       ← 피처 명세
    └── model_card.md         ← 모델 카드 (성능 지표, 제약)
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 피처 추출 모듈 | `src/features/` |
| 예측·평가 모델 | `src/models/` |
| 경제성 계산 | `src/economics/` |
| 군집 사후 분석 (CSV 출력) | `src/analysis.py` |
| 시각화 (PNG 출력) | `src/visualization.py` |
| 전체 파이프라인 진입점 | `src/pipeline.py` |
| `python scripts/xxx.py`로 실행 | `scripts/` |
| pytest | `tests/` |
| `.yaml`, `.env.example` | `config/` |
| 문서, 모델 카드 | `docs/` |

**`dr-savings-prediction/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import xgboost as xgb
import lightgbm as lgb
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
import pandas as pd
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error
import mlflow                      # 실험 추적
import joblib                      # 모델 직렬화
from dotenv import load_dotenv
import os
```

## import 규칙

```python
# scripts/ 에서 src/ 모듈 import 방법
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # dr-savings-prediction/ 루트
_SRC = ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from features.extractor import FeatureExtractor
from features.cluster_features import ClusterFeaturizer
from models.model_selector import ModelSelector
```

## 인터페이스

- **업스트림**:
  - NILM 분해 엔진 (REQ-001) — 기기별 전력 분해 결과 (TimescaleDB)
  - 전력거래소 (REQ-005) — DR 이벤트 신호 (이벤트 시각, 감축 요청량)
- **다운스트림**:
  - Database (REQ-004) — 예측 결과·권고·경제성 분석 저장
  - UI (REQ-006) — DR 분석 대시보드에 표시할 예측·권고 데이터
  - 전력거래소 (REQ-005) — 감축 실적 산출 결과 전송

## 모델 운영 규칙

- **학습 데이터**: 시계열 분할은 `TimeSeriesSplit` 사용 (미래 데이터 누수 방지)
- **군집화**: `cluster_id`는 `src/features/cluster_features.py`에서 생성, 학습·추론 모두 동일 KMeans 모델 사용
- **모델 비교**: XGBoost·LightGBM·RandomForest를 동일 split으로 학습 후 MAE 기준 최적 선택
- **실험 추적**: 모든 학습 실행은 `mlflow.start_run()` 래핑 후 파라미터·메트릭 기록
- **모델 저장**: `mlflow.log_model()` + `joblib.dump()` 로컬 백업
- **성능 기준**: MAE ≤ 5% (절감량 대비), 예측 지연 ≤ 500ms (REQ-008)
- **모델 파일 Git 커밋 금지** — `.gitignore`에 `*.pkl`, `*.joblib`, `mlruns/` 등록

## 보안 주의사항

- DB 접속 정보는 `os.getenv()`로만 참조 (하드코딩 금지)
- 전력 소비 데이터는 개인정보에 해당 — 로그에 raw 값 출력 금지
- DR 인센티브 정산 계산 시 요금 설정은 `config/tariff.yaml`에서만 로드

## 토큰 절감 규칙 (MANDATORY)

### 파일 읽기 전략
- 작업 시작 시 대상 파일의 전체 크기를 먼저 확인한다 (wc -l 또는 limit=1)
- 500줄 이하 파일은 전체 읽기 허용
- 500줄 초과 파일은 목차/헤더를 먼저 읽고(limit=30), 작업에 필요한 구간을 특정한 뒤 해당 구간만 읽는다
- 판단이 불확실하면 "이 구간만 읽어도 되는지" 사용자에게 확인 후 진행한다

### 출력 간결화
- 파일 Write 후 변경 내용을 반복 설명하지 않는다 (diff를 보면 알 수 있는 내용은 생략)
- 단, 설계 판단이 들어간 경우는 한 줄로 근거를 남긴다
- 탐색 중간 결과를 전부 나열하지 않고, 최종 결론만 보고한다

### 세션 관리
- 단일 세션에서 서로 독립적인 작업을 연속 수행하지 않는다 — 작업 단위별로 세션을 분리한다
- 컨텍스트가 커졌다고 느끼면 /compact 실행을 사용자에게 권고한다
