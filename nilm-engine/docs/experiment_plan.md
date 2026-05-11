# NILM 모델 비교 실험 계획

## 목적

CNN+TDA 모델이 기존 NILM 모델 대비 우수한 성능을 가짐을 실험으로 증명한다.

---

## 비교 모델

| 모델 | 설명 | 비교 목적 |
|------|------|-----------|
| **Seq2Point** | aggregate 윈도우 → 중심점 전력값 예측. NILM 분야 표준 베이스라인 | 기본 베이스라인 |
| **BERT4NILM** | BERT 마스킹 방식 적용 NILM. 현재 SOTA급 | 강력한 경쟁 모델 |
| **CNN+TDA** (제안) | CNN + Persistent Homology 위상 특징 결합 | 제안 모델 |

---

## 데이터셋

### 원천 데이터

- 수집 기관: 한국 가정 전력 데이터
- 샘플링 주파수: 30Hz
- 측정 채널: ch01(메인 분전반 aggregate) + ch02~ch22(개별 가전)
- 데이터 형식: CSV (date_time, active_power, voltage, current, frequency, apparent_power, reactive_power, power_factor, phase_difference, current_phase, voltage_phase)

### 가전 구성 (22종)

| 인덱스 | 가전 | Type |
|--------|------|------|
| 0 | TV | Type1 |
| 1 | 전기포트 | Type1 |
| 2 | 선풍기 | Type1 |
| 3 | 의류건조기 | Type2 |
| 4 | 전기밥솥 | Type2 |
| 5 | 식기세척기/건조기 | Type2 |
| 6 | 세탁기 | Type2 |
| 7 | 헤어드라이기 | Type2 |
| 8 | 에어프라이어 | Type2 |
| 9 | 진공청소기(유선) | Type2 |
| 10 | 전자레인지 | Type2 |
| 11 | 에어컨 | Type3 |
| 12 | 인덕션(전기레인지) | Type3 |
| 13 | 전기장판/담요 | Type3 |
| 14 | 온수매트 | Type3 |
| 15 | 제습기 | Type3 |
| 16 | 컴퓨터 | Type3 |
| 17 | 공기청정기 | Type3 |
| 18 | 전기다리미 | Type3 |
| 19 | 일반 냉장고 | Type4 |
| 20 | 김치냉장고 | Type4 |
| 21 | 무선공유기/셋톱박스 | Type4 |

### 가구 구성

전체 110가구 중 Type 비율을 유지하여 10가구 선정.

| 역할 | 가구 |
|------|------|
| Train (8가구) | house_067, house_004, house_024, house_036, house_042, house_045, house_068, house_109 |
| Val (1가구) | house_011 |
| Test (1가구) | house_007 |

---

## 실험 조건 (전 모델 동일 적용)

| 항목 | 값 | 비고 |
|------|----|------|
| 입력 | ch01 active_power | aggregate 유효전력만 사용 |
| 윈도우 크기 | 1024 samples | 34초 @ 30Hz |
| stride | 30 samples | 1초 이동 |
| 출력 | (22, 1024) | 22종 가전 동시 예측 |
| validity mask | 적용 | 미보유 가전 채널 loss 제외 |
| 정규화 | house별 z-score | aggregate 기준 |
| optimizer | Adam | lr=1e-3 |
| batch size | 32 | |
| epochs | 50 | early stopping patience=10 |
| loss | MSE + BCE | 전력 회귀 + ON/OFF 분류 |

---

## 모델별 입출력 구조

### Seq2Point

```
입력: (batch, 1, 1024)          ← aggregate 윈도우
출력: (batch, 22)               ← 윈도우 중심점 각 가전 전력값
```

### BERT4NILM

```
입력: (batch, 1024, 1)          ← aggregate 시퀀스
출력: (batch, 1024, 22)         ← 전체 시퀀스 각 가전 전력값
```

### CNN+TDA (제안)

```
입력 A: (batch, 1, 1024)        ← aggregate 윈도우 (CNN 입력)
입력 B: (batch, tda_dim)        ← 위상 특징 벡터 (TDA 입력)
    - H0/H1 Persistence Diagram에서 추출
    - active_power 신호 기반 Sublevel Set Filtration
    - (voltage, current) 2D point cloud Rips Complex
출력: (batch, 22, 1024)         ← 전체 시퀀스 각 가전 전력값
```

---

## 평가 지표

| 지표 | 수식 | 의미 |
|------|------|------|
| **MAE** | mean(\|pred - true\|) | 평균 절대 오차 (W) |
| **RMSE** | sqrt(mean((pred - true)²)) | 피크 오차에 민감 |
| **SAE** | \|sum(pred) - sum(true)\| / sum(true) | 총 에너지 오차율 (NILM 표준) |
| **F1** | 2PR/(P+R) | ON/OFF 분류 정확도 |

가전 Type별로 지표를 분리해서 보고한다 (Type1~4 각각).

---

## 점진적 학습 스케줄

데이터를 주차별로 늘려가며 성능이 충분히 수렴하면 그 시점에서 중단한다.

| 라운드 | 학습 기간 | date_range 예시 | 판단 기준 |
|--------|-----------|-----------------|-----------|
| R1 | 1주 (7일) | `("2023-09-22", "2023-09-28")` | Val MAE가 기대 수준 미달이면 R2 진행 |
| R2 | 2주 (14일) | `("2023-09-22", "2023-10-05")` | R1 대비 Val MAE 개선 < 5% 면 중단 |
| R3 | 3주 (21일) | `("2023-09-22", "2023-10-12")` | R2 대비 Val MAE 개선 < 5% 면 중단 |
| R4 | 4주 (28일) | `("2023-09-22", "2023-10-19")` | 이후 추가 개선 없으면 최종 채택 |

- 모든 라운드에서 Val(house_011), Test(house_007)의 날짜는 고정 — 학습 기간과 무관하게 동일 구간 평가
- 세 모델 모두 동일 라운드 조건으로 학습 (공정 비교)
- 최종 채택된 라운드 기준으로 EXP-01~04 진행

```python
# 사용 예
train_ds = NILMDataset(
    houses=["house_067", ...],
    data_root="/path/to/data",
    date_range=("2023-09-22", "2023-09-28"),  # R1: 1주차
)
```

---

## 실험 시나리오

### EXP-01: 전체 성능 비교 (메인)

- 조건: 위 실험 조건 그대로
- 목적: 전 가전 22종 평균 성능에서 CNN+TDA가 우위임을 증명

### EXP-02: Type별 성능 분석

- 조건: EXP-01과 동일, 결과를 Type1~4로 분리
- 목적: CNN+TDA가 특히 어떤 가전 Type에서 강한지 분석
- 예상: Type2(모터류), Type4(냉장고, 압축기 사이클)에서 TDA 효과 극대화

### EXP-03: TDA Ablation

- 조건: CNN+TDA에서 TDA 입력 제거 → CNN only
- 목적: TDA 위상 특징이 실제로 성능에 기여하는지 직접 증명
- 비교: CNN only vs CNN+TDA

### EXP-04: Cross-house 일반화

- 조건: Train house를 4가구로 줄여 재학습
- 목적: 적은 데이터에서도 CNN+TDA 일반화 성능이 유지되는지 확인

---

## 결과 기록 양식

실험 완료 후 아래 표를 채운다.

### 점진적 학습 결과 (라운드별 Val MAE)

| 라운드 | 학습일수 | Seq2Point | BERT4NILM | CNN+TDA | 채택 여부 |
|--------|---------|-----------|-----------|---------|-----------|
| R1 | 7일 | - | - | - | |
| R2 | 14일 | - | - | - | |
| R3 | 21일 | - | - | - | |
| R4 | 28일 | - | - | - | |

### 전체 평균 (EXP-01)

| 모델 | MAE (W) | RMSE (W) | SAE | F1 |
|------|---------|----------|-----|----|
| Seq2Point | - | - | - | - |
| BERT4NILM | - | - | - | - |
| CNN+TDA | - | - | - | - |

### Type별 MAE (EXP-02)

| 모델 | Type1 | Type2 | Type3 | Type4 |
|------|-------|-------|-------|-------|
| Seq2Point | - | - | - | - |
| BERT4NILM | - | - | - | - |
| CNN+TDA | - | - | - | - |

### Ablation (EXP-03)

| 모델 | MAE (W) | F1 | TDA 기여도 |
|------|---------|-----|-----------|
| CNN only | - | - | baseline |
| CNN+TDA | - | - | +?% |

---

## 파일 구조

```
nilm-engine/
├── config/
│   └── dataset.yaml
├── src/
│   ├── acquisition/
│   │   ├── dataset.py       # NILMDataset (multi-output)
│   │   └── loader.py        # CSV/JSON 로딩 유틸
│   ├── features/
│   │   └── tda.py           # TDA 위상 특징 추출 (예정)
│   └── models/
│       ├── seq2point.py     # 베이스라인 (예정)
│       ├── bert4nilm.py     # 베이스라인 (예정)
│       └── cnn_tda.py       # 제안 모델 (예정)
└── docs/
    └── experiment_plan.md   # 이 파일
```
