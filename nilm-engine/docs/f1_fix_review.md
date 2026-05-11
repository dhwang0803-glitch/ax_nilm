# f1_diagnosis_and_fix.md 검토 의견

> 검토 대상: `f1_diagnosis_and_fix.md` (2026-04-28 작성)
> 검토일: 2026-04-28
> 대상 코드 기준: `nilm-engine/` 브랜치 현재 상태
> 추가 근거 자료: AI Hub 71685 활용가이드라인 v1.0 별첨4 (가전기기별 라벨링 기준)

---

## 종합 평가

진단·우선순위·구현 방향은 합리적. 단 **그대로 적용하면 발산하거나 효과 측정이 불가능해지는 함정**이 몇 군데 있어 보강이 필요함.

추가로 활용가이드라인 별첨4를 확인한 결과, **현재 코드의 ON/OFF 평가 임계값(`_ON_THRESHOLD`)이 데이터셋 라벨링 기준과 정량적으로 크게 어긋남**을 발견. 이는 다른 모든 변경의 효과 측정을 왜곡할 수 있는 **선결 항목**이라 0번으로 우선 추가함.

### 잘 정리된 부분

- 핵심 진단(목적함수 불일치 + center 1샘플 + 임계 binarize 3중 결합) 정확
- Cross-Attention 차원 정정 — 실제 `_CrossAttention(cnn_dim=512, tda_dim=128)`이라 attention은 128차원에서 동작. 병목은 raw `TDA_DIM=20` 입력 빈곤이 맞음
- gate collapse 우려, 캐시 무효화 주의, event_context 가전별 표는 추가 가치 있음
- A 적용 → A+D → A+D+B 순 ablation 설계 합리적

---

## 보강이 필요한 항목

### 0. 평가 임계값이 데이터셋 라벨링 기준과 어긋남 (최우선) 🚨

**위치:** `nilm-engine/src/classifier/label_map.py:40-50`, `scripts/train_model.py:135-139`

**현상:**
현재 코드는 4개 type 카테고리에 단일 임계값을 부여해 모든 가전을 일괄 처리:
```python
_ON_THRESHOLD = { "type1": 30.0, "type2": 20.0, "type3": 50.0, "type4": 5.0 }
```

그러나 AI Hub 가이드라인 별첨4에 따르면 **22가전 각각 서로 다른 대기전력 임계값과 시간 조건**으로 ON/OFF가 라벨링됨:

| # | 가전 | 코드 type | 코드 임계 | **PDF 임계** | 차이 | 활성 최소 시간 | Gap 시간 |
|---|------|---------|---------|--------------|------|--------------|---------|
| 0 | TV | type1 | 30W | **5W** | 6× ↑ | 2분 | 1초 |
| 1 | 전기포트 | type1 | 30W | **15W** | 2× ↑ | 0.5초 | 1초 |
| 2 | 선풍기 | type1 | 30W | **2W** | **15× ↑** | 0.5초 | 1초 |
| 3 | 의류건조기 | type2 | 20W | **5W** | 4× ↑ | 1분 | 1분 |
| 4 | 전기밥솥 | type2 | 20W | **5W** | 4× ↑ | 기준 없음 | 5분 |
| 5 | 식기세척기/건조기 | type2 | 20W | **10W** | 2× ↑ | 1분 | 5분 |
| 6 | 세탁기 | type2 | 20W | **10W** | 2× ↑ | 1분 | 10초 |
| 7 | 헤어드라이기 | type2 | 20W | **15W** | 거의 동일 | 0.5초 | 1초 |
| 8 | 에어프라이어 | type2 | 20W | **10W** | 2× ↑ | 0.5초 | 1초 |
| 9 | 진공청소기(유선) | type2 | 20W | **6W** | 3× ↑ | 0.5초 | 1초 |
| 10 | 전자레인지 | type2 | 20W | **10W** | 2× ↑ | 10초 | 1초 |
| 11 | 에어컨 | type3 | 50W | **2W** | **25× ↑** | 1분 | 5분 |
| 12 | 인덕션(전기레인지) | type3 | 50W | **15W** | 3× ↑ | 0.5초 | 1초 |
| 13 | 전기장판/담요 | type3 | 50W | **5W** | 10× ↑ | 0.5초 | 1초 |
| 14 | 온수매트 | type3 | 50W | **5W** | 10× ↑ | 0.5초 | 1초 |
| 15 | 제습기 | type3 | 50W | **3W** | **17× ↑** | 30초 | 5분 |
| 16 | 컴퓨터 | type3 | 50W | **5W** | 10× ↑ | 10초 | 1분 |
| 17 | 공기청정기 | type3 | 50W | **3W** | **17× ↑** | 1분 | 1분 |
| 18 | 전기다리미 | type3 | 50W | **15W** | 3× ↑ | 기준 없음 | 1초 |
| 19 | 일반 냉장고 | type4 | 5W | Always-On (1시간 봉우리 라벨) | 무관 | — | — |
| 20 | 김치냉장고 | type4 | 5W | 일반 냉장고와 동일 | 무관 | — | — |
| 21 | 무선공유기/셋톱박스 | type4 | 5W | 기본 전력 + **0.5W** 이상 | 절대값 부적합 | 2분 지속 | — |

**특히 심각한 케이스:**
- **에어컨 (25× 차이)**: PDF 2W → 코드 50W. 인버터 에어컨의 미풍/대기 모드(<50W)가 평가에서 전부 OFF로 처리됨. 학습 라벨은 ON인데 평가 시 정답이 OFF로 뒤집히는 구조.
- **선풍기 (15× 차이)**: 1단 동작 ~6W가 코드 30W 기준 OFF. 활성 윈도우 거의 사라짐.
- **공기청정기·제습기 (17× 차이)**: 통상 운전 ~15-30W가 코드 50W 기준 OFF.
- **냉장고/공유기**: 절대 임계가 아닌 "Always-On + 봉우리" 또는 "기준 전력 +0.5W"라 단일 W 임계 자체가 부적합.

**왜 F1 측정에 직접 영향?**

`scripts/train_model.py:138-139`:
```python
norm_thr = (raw_thr - scaler.mean) / scaler.std if scaler is not None else raw_thr
pred_on  = pred_arr >= norm_thr[np.newaxis, :]
```

평가 시 `raw_thr`로 사용되는 것이 위의 부정확한 type별 임계. 결과적으로:
- 학습 라벨(`on_off_mask`)은 PDF 기준으로 정확하게 만들어졌는데
- 모델 출력에 적용되는 평가 임계는 PDF 기준의 6~25배 더 엄격
- 모델이 라벨대로 잘 예측해도 평가 단계에서 OFF로 뒤집혀 false negative ↑
- 다른 모든 변경(A/B/C/D)의 효과가 이 측정 노이즈에 묻힘

**권장 (3단계):**

**0-1) 즉시 적용**: per-appliance threshold로 교체
```python
# nilm-engine/src/classifier/label_map.py
APPLIANCE_ON_THRESHOLD: dict[str, float] = {
    "TV": 5.0, "전기포트": 15.0, "선풍기": 2.0,
    "의류건조기": 5.0, "전기밥솥": 5.0, "식기세척기/건조기": 10.0,
    "세탁기": 10.0, "헤어드라이기": 15.0, "에어프라이어": 10.0,
    "진공청소기(유선)": 6.0, "전자레인지": 10.0,
    "에어컨": 2.0, "인덕션(전기레인지)": 15.0,
    "전기장판/담요": 5.0, "온수매트": 5.0, "제습기": 3.0,
    "컴퓨터": 5.0, "공기청정기": 3.0, "전기다리미": 15.0,
    "일반 냉장고": 5.0,            # Always-On이지만 임계 사용 시 보수적 5W
    "김치냉장고": 5.0,
    "무선공유기/셋톱박스": 5.0,    # 절대값으로는 부정확, 추후 0-3 참조
}

def get_on_thresholds() -> list[float]:
    return [APPLIANCE_ON_THRESHOLD[name] for name in APPLIANCE_LABELS]
```

기존 type 분류는 다른 용도(예: 손실 가중)로 보존 가능, 임계 dict만 가전별로 분리.

**0-2) 다음 단계**: 활성 최소 시간 / Gap 분리 시간을 평가 후처리에 적용
- 현재 평가는 center 1샘플 binarize → 시간 조건 적용 불가 (D 방안 적용 후 가능)
- D 방안(윈도우 합의)에서 합의 폭을 가전별 "활성 최소 시간"과 정렬:
  - 0.5초 가전(헤어드라이기·전기포트 등): center 15샘플(≈0.5s @ 30Hz) 합의
  - 1분 가전(에어컨·세탁기): 1분 윈도우 = 1800샘플 — 현재 1024 윈도우로는 부족 → 다운샘플+긴 윈도우 또는 별도 평가 윈도우 필요
- 시퀀스 평가 도입 시 짧은 ON spike (가전별 최소 시간 미만)를 후처리로 제거하면 PDF 라벨링과 정합

**0-3) 냉장고·공유기 특수 처리**:
- 냉장고는 "Always-On + 1시간 단위 봉우리" → 별도 회귀 채널로만 다루고 ON/OFF 분류 자체에서 제외(또는 항상 ON으로 고정)
- 공유기는 "기본 전력 + 0.5W" → 가구별 baseline 학습이 필요 → 1차 적용은 5W 절대 임계로 하되, 정확도 한계 명시

**예상 효과:**
- 0-1만으로 F1 점수가 가시적으로 개선될 가능성이 매우 높음 (기존이 라벨-임계 불일치로 기본 손실)
- A/B/C/D 효과 측정의 노이즈 제거 → ablation 결론 신뢰도 ↑
- **반드시 다른 변경 적용 전에 baseline 재측정** (현재 F1=0.464는 잘못된 임계 위에서 나온 수치)

---

### 1. A 방안 — pos_weight 발산 위험 (높음)

**문서 원안:**
```python
pos_weight = off_counts / on_counts.clip(min=1)
```

**문제:** type2 가전(전자레인지·헤어드라이어 등) ON ratio 0.5%면 `pos_weight ≈ 200`. BCE 초반에 logit gradient가 200배 부풀어 학습 발산 가능.

**권장 수정:**
```python
pos_weight = torch.sqrt(off_counts / on_counts.clip(min=10)).clamp(max=20)
```
- sqrt scaling으로 극단 스케일 완화
- 분모 floor=10 (ON 카운트 10개 미만 채널은 어차피 신뢰도 낮음)
- clamp(max=20)로 안전망

**ON 카운트 0인 채널 처리:** train set에 한 번도 ON이 없는 가전은 BCE에서 마스크 처리(validity 패턴 그대로 재사용).

---

### 2. A 방안 — confidence-gated mixture에 BCE 단일 부여 시 gate collapse 가속 (높음)

**문제:** 현재 `pred = c * cnn_pred + (1-c) * fusion_pred` 1개 출력에만 loss가 걸려 있음 (`cnn_tda.py:127`). BCE 도입해도 c→0 또는 c→1 수렴하면 한쪽 헤드 gradient 끊기는 구조 유지.

**권장:** mixture가 아닌 **두 헤드에 각각 BCE** 부여.

```python
loss = (
    bce(cnn_logits,    y, pos_weight=pw)
  + bce(fusion_logits, y, pos_weight=pw)
  + λ_mse * mse_loss
)
```

- mixture는 추론 시점에서만 사용
- 양쪽 supervision이 항상 살아있어 gate 수렴이 한쪽으로 편향돼도 헤드 학습은 유지됨
- gate에 별도 entropy regularization 안 걸어도 안정 — 다만 문서의 "gate 분포 로깅"은 그대로 유지 권장

---

### 3. C 방안 1 — P95 정규화는 H1 Rips와 충돌 가능 (중간)

**문서 원안:**
```python
p95 = np.percentile(sig_sub, 95)
sig_norm = sig_sub / (p95 + 1e-6)
```

**문제:** P95 외부 outlier가 정규화 후에도 1.5~2.x로 살아남아 phase-space 거리 분포를 끌어올림. `tda.py:139` `max_edge_length`가 90% × 2로 자동 계산되긴 하나, outlier가 max_edge를 부풀려 H1 lifetime 분포 자체가 흔들릴 위험.

**권장:**
- 정규화 변경은 보류, **방안 2(magnitude bin)에 집중**
- 4-bin one-hot 대신 부드러운 형태 권장:
  ```python
  log_mean = np.log10(signal.mean() + 1.0)
  log_max  = np.log10(signal.max()  + 1.0)
  # 2dim 추가 → TDA_DIM = 22
  ```
- 4-bin 그대로 가려면 `bins=[100, 500, 2000]`이 train 분포에 적절한지 히스토그램으로 먼저 확인

---

### 4. 누락 항목 — PowerScaler 채널 정규화 쏠림 (높음)

**위치:** `dataset.py:163-176`

**문제:** aggregate(ch01) 기준 (mean, std)으로 fit한 단일 PowerScaler를 22가전 target에도 그대로 적용.
- aggregate 분포는 수백 W 스케일 → fit된 mean/std는 그 영역에 맞춰짐
- 5W 냉장고·50W TV 채널을 같은 scaler로 통과시키면 거의 0 근방으로 압축
- 회귀 출력도 0 근방에 갇힘 → **trivial-zero 함정을 강화하는 부가 원인**

**권장 (둘 중 택1):**
1. **per-channel scaler**: 22채널 각자 fit. validity=False 채널은 스킵.
2. **aggregate만 정규화**: target은 raw W 그대로 두고 BCE 분류로 ON/OFF 학습이 메인이 되면 scale 불균형 영향 줄어듦.

문서에 항목 추가 권장 — A·D 효과 측정에 직접 영향.

---

### 5. 누락 항목 — wavelet denoising ablation 없음 (높음)

**문제:** 문서에 "적용 완료"로 표기됐지만 단독 효과 측정 없음. A/B/C와 합쳐지면 각 변경의 기여도 분리 불가능.

**권장:**
- 검증 표 맨 위에 행 추가: `denoising on/off 비교`
- `agg_power`만 denoise하고 `target_power`는 raw → 가전 합 ≠ aggregate 갭이 회귀 손실에 노이즈로 들어감 (작은 효과). 문서에 명시 권장.

---

### 6. D 방안 — 회귀/분류 라벨 정의 불일치 (중간)

**문서 원안:**
```python
target_c = target[:, :, s:e].mean(dim=-1)              # 평균 W
on_off_c = (on_off[:, :, s:e].float().mean(dim=-1) >= 0.5)  # 다수결
```

**문제:** 같은 윈도우에서 `target_c=80W`인데 `on_off_c=False`(평균 ON 비율 40%)인 케이스 발생 가능. 회귀는 "ON이 일부 있는 평균"을, 분류는 "OFF"를 ground truth로 사용 → 두 헤드가 서로 다른 라벨을 봄.

**권장 (둘 중 택1):**
- 통일된 룰 채택: `on_off_c = target_c >= channel_threshold`
- 또는 두 라벨 정의 차이를 의도된 것으로 명시(회귀=평균 power, 분류=majority ON)하고 문서에 사유 기록

---

### 7. B 방안 — event_context=10 사이드 이펙트 (낮음)

**계산:** ±10초 × stride=30 = 21 윈도우/이벤트. 1주 8house 기준 ≈ 49,200개 (현재 98,400 대비 절반).

발산 가능성 낮으나 batch_size=32 기준 epoch 당 1,500 step 정도. **첫 실행 시 반드시 로그로 출력:**
- 실제 윈도우 수
- per-class ON 윈도우 수 (22 채널 각각)

type2 가전이 윈도우 100개 미만이면 epoch 안에 거의 등장 안 함 → epoch 늘리거나 oversampling 필요.

---

### 8. 줄 번호 어긋남 (사소)

| 문서 표기 | 실제 위치 |
|---|---|
| `train_model.py:95–107` masked_weighted_mse | 82-94 |
| `train_model.py:132–133` center | 119-120 |
| `train_model.py:227` on_off_c | 219 |

파일 수정 시 라인 갱신.

---

### 9. 검증 단계 — EXP4까지 대기는 비용 큼 (낮음)

문서의 검증 5번 "EXP4까지 현재 결과 확인" — 4주 학습 다 돌리려면 시간 큼.

**권장:** EXP1만 돌려 baseline 확정 → A 진입. 포화점 확인은 A 적용 이후 EXP1→4 진행이 사이클 타임 짧음.

---

## 권장 적용 순서 (조정안)

| # | 단계 | 목적 |
|---|------|------|
| **0** | **per-appliance threshold 교체 → baseline 재측정** | **현재 F1=0.464는 잘못된 임계 위 수치. 본 검토 0번 (가장 우선)** |
| 1 | 검증 1~3 (CNN only F1, ON ratio, 예측 분포) | A 진입 전 sanity. 가설 정량 확정 (재측정된 baseline 기준) |
| 2 | wavelet denoising 단독 ablation | 단독 효과 분리 측정 |
| 3 | **PowerScaler 채널 분리 + dual head BCE 양쪽 부여 + sqrt-clamp pos_weight** 묶음 적용 → EXP1 측정 | 본 검토의 1·2·4번 통합 적용 |
| 4 | D 방안 적용 (라벨 정의 통일 + 가전별 활성 최소 시간 정렬) → EXP1 재측정 | center 1샘플 노이즈 제거 + PDF 시간 조건 정합 |
| 5 | C 방안 2 (magnitude bin 또는 log_mean/log_max 추가) | TDA 절대 magnitude 보강. C-1(P95) / C-3(top_k)은 차이 미미하면 보류 |
| 6 | B (event_context 20→10 sweep) | 빠른 가전 transient 희석 완화 |
| 7 | EXP1→EXP4 본 학습 (포화점 측정) | |
| 8 | E (멀티스케일) | 효과 측정 후 판단 |

---

## 핵심 메시지 (팀원 전달용)

문서 자체는 좋음. 단 다음 세 항목이 빠져 있어 그대로 적용하면 효과 측정이 망가짐 — 반드시 반영:

1. **per-appliance threshold 교체 (본 검토 0번)** 🚨 — 현재 평가 임계가 데이터셋 라벨링 기준(PDF 별첨4)과 6~25배 어긋남. 에어컨·선풍기·공기청정기·제습기는 사실상 "정답이 OFF"로 뒤집혀 평가됨. **이걸 안 고치면 다른 변경 전부 측정 노이즈에 묻힘**. baseline 재측정 필수.
2. **PowerScaler 채널 분리** (항목 4) — aggregate 기준 scaler를 22채널에 공유하면 회귀 출력이 0 근방에 갇혀 BCE 도입 효과를 측정 못 함
3. **dual head를 mixture가 아닌 두 헤드 각각에 BCE 부여** (항목 2) — gate collapse 정면 대응

추가로 pos_weight는 sqrt+clamp(20)로 안전하게(항목 1), wavelet denoising은 단독 ablation 행 추가(항목 5)해서 기여도 분리.

---

## 부록: AI Hub 가이드라인 별첨4 라벨링 기준 요약

데이터셋 라벨이 만들어진 정확한 룰. 평가 임계와 학습 손실 설계에 그대로 적용되어야 함.

**공통**:
- ON/OFF 판정은 가전별 대기전력 임계값 + 활성 최소 시간 + Gap 분리 시간의 **세 조건 조합**
- 1차 오토라벨링 → 크라우드 워커가 가전별 가이드 참조하여 활성/비활성 구간 라벨링
- 두 명의 작업자가 동일 데이터에 대해 교차 검수
- 22가전을 4개 라벨링 패턴 그룹으로 분류:
  - **TYPE 전열 기기** (1~7): 헤어드라이기, 전기포트, 전기장판/담요, 온수매트, 인덕션, 전기다리미, 에어프라이어
  - **TYPE 비교적 계단형 패턴** (8~12): 선풍기, 진공청소기, TV, 전자레인지, 컴퓨터
  - **TYPE 동작 코스가 다양한 가전** (13~17): 전기밥솥, 세탁기, 의류건조기, 식기세척기, 에어컨
  - **TYPE 상대적으로 오래 켜두는 가전** (18~22): 공기청정기, 제습기, 일반 냉장고, 김치냉장고, 무선공유기/셋톱박스

**현재 코드 type 분류와 PDF 라벨링 그룹은 일치하지 않음** — 현재 코드의 type1~4는 임계값 묶음용, PDF type은 라벨링 패턴 그룹용. 임계값을 가전별로 분리하면 코드 type 카테고리는 손실 가중 등 다른 용도로만 유지 가능.
