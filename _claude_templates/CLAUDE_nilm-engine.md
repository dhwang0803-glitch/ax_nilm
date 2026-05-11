# nilm-engine — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.
> 담당 요구사항: **REQ-001** (NILM 분해 엔진)

## 관련 문서

- 전체 아키텍처: [`docs/context/architecture.md`](../docs/context/architecture.md)
- 설계 결정: [`docs/context/decisions.md`](../docs/context/decisions.md)
- 파일 맵: [`docs/context/MAP.md`](../docs/context/MAP.md)
- 하류 의존: `feature/anomaly-detection` (이상 탐지), Database 모듈

## 모듈 역할

**NILM 분해 엔진** — 단일 분전반의 30Hz 전력 시계열 데이터로부터 개별 가전 22종의 전력 소비를 분해(Disaggregation)한다.

핵심 알고리즘: **CNN**(시계열 패턴) + **TDA**(위상적 특징, persistent homology) 하이브리드 식별

## 파일 위치 규칙 (MANDATORY)

```
nilm-engine/
├── src/
│   ├── acquisition/      ← 30Hz 데이터 수집 & 전처리 (import 전용)
│   │   ├── sampler.py        ← 윈도우 분할 (청크 단위)
│   │   └── preprocessor.py   ← 노이즈 제거, 정규화
│   ├── features/         ← 특징 추출 (import 전용)
│   │   ├── wavelet.py        ← PyWavelets 에너지 계수 추출
│   │   ├── tda.py            ← GUDHI persistent homology 특징
│   │   └── extractor.py      ← wavelet + TDA 통합 추출기
│   ├── models/           ← 하이브리드 모델 정의 (import 전용)
│   │   ├── cnn_encoder.py    ← 시계열 CNN 인코더 (PyTorch)
│   │   ├── tda_encoder.py    ← 위상 특징 MLP 인코더
│   │   └── hybrid.py         ← CNN + TDA 결합 모델
│   ├── classifier/       ← 22종 가전 분류 헤드 (import 전용)
│   │   ├── appliance_clf.py  ← 분류 레이어
│   │   └── label_map.py      ← 22종 가전 레이블 정의 (단일 진실 공급원)
│   └── disaggregator.py  ← 분해 파이프라인 public API
├── scripts/
│   ├── run_disaggregate.py   ← 실시간 분해 실행
│   └── train_model.py        ← 모델 학습 실행
├── tests/                ← pytest (단위 + 통합)
├── config/
│   ├── model.yaml            ← CNN/TDA 하이퍼파라미터
│   └── .env.example
└── docs/
    └── model_design.md
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 수집/전처리 모듈 | `src/acquisition/` |
| 특징 추출 모듈 | `src/features/` |
| 모델 정의 (PyTorch nn.Module) | `src/models/` |
| 22종 분류 헤드 & 레이블 | `src/classifier/` |
| 분해 파이프라인 public API | `src/disaggregator.py` |
| 직접 실행 스크립트 | `scripts/` |
| pytest | `tests/` |
| yaml, .env.example | `config/` |
| 설계 문서 | `docs/` |

**`nilm-engine/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import torch
import torch.nn as nn
import pywt                          # PyWavelets — 웨이블릿 특징
import gudhi                         # TDA — Vietoris-Rips 복단체 / persistence
from sklearn.preprocessing import StandardScaler
import numpy as np
import pandas as pd
import mlflow                        # 실험 추적
from dotenv import load_dotenv
```

## import 규칙

```python
# scripts/ 에서 src/ 모듈 import
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]   # scripts/는 parents[2]가 루트
_SRC = ROOT / "nilm-engine" / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from disaggregator import NILMDisaggregator
```

## 핵심 설계 원칙

### 30Hz 데이터 처리
- 샘플링 간격: 33.3ms (1/30Hz)
- 윈도우: 슬라이딩 윈도우 (기본 2초 = 60 샘플), 오버랩 50%
- 과도 상태(transient) 감지 후 윈도우 기준 정렬 필수

### CNN 인코더
- 입력: `(batch, 1, window_size)` — P(유효전력) 또는 [P, Q, I, V] 다변량
- Conv1d → BatchNorm → ReLU → MaxPool 반복 구조
- 출력: 시계열 임베딩 벡터

### TDA 인코더
- GUDHI `RipsComplex`로 point cloud 구성 → persistence diagram 생성
- persistence 이미지(PersistenceImage)를 벡터로 변환 후 MLP 통과
- 위상적 노이즈 불변 특징 추출

### 22종 가전 레이블
`src/classifier/label_map.py` 가 단일 진실 공급원 — 새 가전 추가는 반드시 이 파일만 수정.

## 인터페이스

- **업스트림**: `Database` 모듈 — TimescaleDB에서 30Hz raw 전력 시계열 조회
- **다운스트림**:
  - `Database` — 분해 결과(기기별 전력량) 저장
  - `feature/anomaly-detection` — 기기별 소비 패턴 전달
  - `API_Server` — 분해 결과 REST 응답

```python
# public API 시그니처 (src/disaggregator.py)
class NILMDisaggregator:
    def disaggregate(
        self,
        power_series: np.ndarray,   # shape: (N,) or (N, 4) — P 또는 [P,Q,I,V]
        sample_rate: int = 30,       # Hz
    ) -> dict[str, np.ndarray]:      # {"appliance_label": power_array, ...}
        ...
```

## MLflow 실험 추적 규칙

```python
import mlflow

with mlflow.start_run(run_name="nilm_hybrid_v{version}"):
    mlflow.log_params({
        "window_size": cfg["window_size"],
        "cnn_layers": cfg["cnn_layers"],
        "tda_max_dim": cfg["tda_max_dim"],
    })
    mlflow.log_metric("val_accuracy", val_acc)
    mlflow.pytorch.log_model(model, "nilm_model")
```

## 구현 완료 후 자가 점검

- [ ] 하드코딩 IP/키/비밀번호 없음
- [ ] `.env` 로드는 `load_dotenv()` + `os.environ[...]` (기본값 없음)
- [ ] 30Hz 윈도우 처리 시 메모리 누수 없음 (제너레이터 사용 권장)
- [ ] `label_map.py` 외 하드코딩 레이블 없음
- [ ] MLflow 실험명/파라미터 로깅 포함
- [ ] tests/ 에 `test_disaggregator.py` 최소 1개 존재

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
