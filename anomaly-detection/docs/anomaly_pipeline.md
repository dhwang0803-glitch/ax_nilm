# 이상탐지 파이프라인 설계서

---

## 1. 전체 파이프라인 개요

```
[학습 단계]
GCS 서브미터 (가전별 실측 W)
    ↓
pseudo_labeler.py
    ↓
labeled_states.parquet
    ↓
이상탐지 모델 학습
(Transformer + TDA Hybrid)

[서비스 단계]
분전반 집합신호 (30Hz)
    ↓
CNN+TDA 분해 (NILM 엔진)
    ↓
가전별 추정 W
    ↓
state_classifier.py (임계값 기반)
    ↓
이상탐지 모델 추론
    ↓
이상 감지 + 심각도
```

---

## 2. pseudo_labeler → labeled_states.parquet

### 목적
GCS 서브미터(가전별 실측 전력값)에 상태 라벨을 자동 부착하여 이상탐지 모델의 학습 데이터를 생성.

### 입력
- GCS 서브미터 채널 데이터 (house_id, channel, active_power, timestamp)
- `thresholds.yaml` — 22종 가전별 상태 임계값

### 처리 과정
```
서브미터 P(t) 시계열
    ↓
on-period 구간 추출 (W > 5W)
    ↓
윈도우 분할 (최소 1~2초, 30~60 샘플)
    ↓
임계값 적용 → 상태 할당
    예) 에어컨 W=23W → cool_high (≥20.6W)
    ↓
연속 동일 상태 구간 병합
    ↓
labeled_states.parquet 저장
```

### 출력 스키마
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `house_id` | str | 가구 ID |
| `channel` | str | 서브미터 채널 |
| `appliance` | str | 가전명 |
| `state` | str | 상태명 (예: cool_high) |
| `started_at` | datetime | 구간 시작 |
| `ended_at` | datetime | 구간 종료 |
| `mean_w` | float | 구간 평균 전력 |
| `duration_sec` | float | 지속 시간 (초) |

### 커버리지
- EDA/임계값 도출: 10가구 (house_011/015/016/017/033/039/049/054/063/067)
- 학습 데이터 생성: 전체 약 100가구 (pseudo_labeler 전체 실행 시)
- 대상 가전: 22종 (thresholds.yaml 기준)

---

## 3. 이상탐지 모델 설계

### 3-1. 현재 구현 구조

```
가전별 추정 W + 상태
    ↓
    ├── [ANOM-001] statistical.py     전력 크기·사용 시간 이상
    │       Z-score, 평균 이탈 감지
    │       → anomaly_score_stat
    │
    └── [ANOM-002] pattern.py         파형 패턴 이상
            Isolation Forest
            → anomaly_score_pattern
    ↓
[service.py] 결과 합산 → AnomalyEvent (Severity 판정)
    ↓
Database 저장 → Frontend 알림
```

### 3-2. 심각도 결합 규칙 (service.py)

두 모델은 **병렬 실행** — 서로 다른 종류의 이상을 감지.

| statistical.py | pattern.py | 심각도 |
|---------------|-----------|--------|
| 정상 | 정상 | — |
| 이상 | 정상 | 주의 (전력/시간 이상) |
| 정상 | 이상 | 주의 (패턴 변화, 성능 저하 초기) |
| 이상 | 이상 | 경고/위험 (복합 이상) |

> 초기엔 규칙 기반 결합 사용. 이상 케이스 데이터 축적 후 가중합으로 고도화 가능.

### 3-3. 이상 유형별 담당 모델

| 유형 | 담당 | 예시 |
|------|------|------|
| 전력 크기 이상 | statistical.py | 선풍기 high인데 55W (정상 32W) |
| 사용 시간 이상 | statistical.py | 세탁기가 평소 2배 시간 가동 |
| 파형 패턴 변화 | pattern.py | 냉장고 압축기 사이클 형태 변화 |
| 전력 정상이나 패턴 이상 | pattern.py | 성능 저하 초기 (pattern.py만 감지 가능) |

### 3-4. 고도화 방안 (팀원 제안 — 추후 적용)

**Transformer + TDA Hybrid** (pattern.py 대체 또는 병렬 추가)

```
시계열 윈도우 (30~60 샘플)
    ↓
[Branch A] Transformer Self-Attention   (시계열 흐름)
[Branch B] TDA → Persistence Image      (위상 구조)
    ↓
Cross-Attention (Branch A=Query, Branch B=Key/Value)
    ↓
anomaly_score_tda
```

- **TDA 적용**: 시간지연 임베딩 → Persistent Homology → Persistence Image (고정 벡터)
- **윈도우**: 최소 30샘플(1초) — 위상 포착 최소 단위
- **이벤트 감지**: Wasserstein Distance로 정상 패턴과 현재 패턴 거리 계산 → 연산량 절감
- **데이터**: 약 100가구 확보로 Transformer 학습량 충분

> **30Hz 한계**: I-V 궤적 직접 재구성 불가. 시간지연 임베딩 기반 위상 분석으로 대체.

### 3-5. Isolation Forest vs Transformer+TDA 비교

| 항목 | Isolation Forest (현재) | Transformer+TDA (고도화) |
|------|------------------------|------------------------|
| 감지 대상 | 피처 공간 이상치 | 시계열 패턴 + 위상 변화 |
| 30Hz TDA 효과 | 해당 없음 | 제한적 (I-V 궤적 불가) |
| 학습 데이터 | 불필요 (비지도) | 필요 |
| 연산 비용 | 낮음 | 높음 |
| 구현 복잡도 | 낮음 | 높음 |

**30Hz 환경에서 TDA의 추가 이득이 불확실한 이유**

TDA가 30Hz에서 추가로 잡을 수 있는 것:
- 냉장고 압축기 사이클의 위상 구조 변화
- 세탁기 동작 패턴의 위상적 차이

그러나 Isolation Forest도 피처를 잘 설계하면 (`mean_w`, `std_w`, `duration_sec`) 동일한 이상을 감지할 수 있음.  
TDA의 본래 강점(I-V 궤적 위상 분석)은 6kHz 이상 고주파 데이터에서 발휘되며, 30Hz에서는 효과가 제한적.

**Isolation Forest 채택 근거**

1. **비지도 학습** — 정상/이상 라벨 없이 학습 가능. 실제 고장 가전 데이터가 없는 현 상황에서 유일하게 현실적인 선택.
2. **격리 원리** — 정상 데이터는 트리에서 격리하기 어렵고(깊은 곳), 이상 데이터는 금방 격리됨(얕은 곳). 이상할수록 anomaly score 높아짐.
3. **고차원 피처에 강함** — `mean_w`, `std_w`, `duration_sec`, `hour`, `day_of_week` 등 다중 피처 동시 처리 가능.
4. **낮은 연산 비용** — 실시간 서비스에서 지연 없이 추론 가능.

**권장 전략: 베이스라인 우선**

```
Phase 1: Isolation Forest 베이스라인 성능 측정
    ↓
Phase 2: Transformer+TDA 추가 후 성능 비교
    ↓
Phase 3: 성능 향상이 연산 비용을 정당화하면 교체
```

> TDA 도입은 Isolation Forest 대비 성능 향상이 검증된 후 결정 권장.

---

## 4. 구현 순서

| 단계 | 파일 | 상태 |
|------|------|------|
| Step 1 | `nilm-engine/labeling/thresholds.yaml` | ⏳ 작성 예정 |
| Step 2 | `anomaly-detection/scripts/pseudo_labeler.py` | ⏳ 작성 예정 |
| Step 3 | `anomaly-detection/scripts/state_classifier.py` | ⏳ 작성 예정 |
| Step 4 | 이상탐지 모델 학습 코드 | ⏳ 설계 중 |
| Step 5 | 서비스 파이프라인 연결 | ⏳ 미정 |

---

## 5. 미결 사항 (팀장 검토 요청)

1. ~~**Transformer 데이터 요구량**~~ ✅ 해결 — 전체 약 100가구 데이터 활용 가능, Transformer 학습량 충분
2. **TDA 연산 비용**: 실시간 서비스에서 슬라이딩 윈도우마다 Persistent Homology 계산 시 지연 허용 범위 확인 필요
3. **윈도우 크기 확정**: 1초 vs 2초 — TDA 변별력과 실시간성 트레이드오프
4. **상태 분류기 위치**: state_classifier.py를 NILM 엔진 내부에 포함할지, 이상탐지 모듈에 포함할지
