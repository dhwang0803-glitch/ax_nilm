# classify_mode Cross-Attention 교체 계획

> 작성일: 2026-05-14  
> 목적: TDA mode 분류기에서 L2 distance → Cross-Attention으로 교체하여 포폴용 검증 가능한 개선 확보  
> 스코프: `e2e_monitoring_colab.ipynb`의 `classify_mode()` 함수 한정 (이상탐지 전체 파이프라인 개편 아님)

---

## 0. 현재 구현 요약

### 전체 흐름

```
전력 신호(30Hz)
    └─ time-delay embedding          # 1D 신호 → 2D 위상 공간 점군
         └─ Ripser (H1 persistent homology)   # 위상 구조 추출
              └─ Persistence Image (flat vector, d차원)   # 위상 → 이미지 벡터화
                   └─ classify_mode()          # 레퍼런스와 비교 → 모드 레이블
                        └─ ShortTermEvent.mode 저장
```

### TDA 적용 가전 (`TDA_APPLIANCES`)

모든 가전에 TDA를 적용하지 않고, 전력 파형의 위상 구조가 상태 간에 구별되는 가전만 선별 적용.

### `_make_event()`의 TDA 채택 조건

TDA가 분류한 모드라도 무조건 쓰지 않음. 아래 두 조건을 모두 통과해야 채택:

1. `classify_mode()`가 `None`이 아닌 결과를 반환
2. 해당 구간의 `avg_w`가 TDA 분류 모드의 W 범위(`thresholds.yaml`) 안에 있을 것

→ 둘 중 하나라도 실패하면 hysteresis 기반 통계 모드로 폴백.

### 현재 `classify_mode()`의 한계

L2 distance는 Persistence Image의 모든 픽셀을 동등하게 취급한다.  
그러나 PI에서 대각선에서 먼 픽셀(persistence 높은 위상 특징)이 가까운 픽셀보다 변별력이 높다.  
→ 중요도가 다른 차원을 동등하게 보는 것이 분류 품질의 병목.

---

## 1. 현재 구현 코드 (Baseline)

```python
def classify_mode(appliance, fingerprint, references):
    fp = np.array(fingerprint, dtype=np.float32)         # shape: [d]
    best_state, best_dist = None, float('inf')
    for state_name, ref_vec in app_refs.items():
        ref = np.array(ref_vec, dtype=np.float32)
        dist = float(np.linalg.norm(fp - ref))           # L2 distance
        if dist < best_dist:
            best_state = state_name
    return best_state
```

**문제:** L2 distance는 벡터 공간의 전체 성분을 동등하게 취급한다.  
Persistence Image는 생성 위치(birth/death값)에 따라 변별력 차이가 존재하는데, L2는 이를 반영 못함.

---

## 2. 설계

### 핵심 아이디어

```
Query  = 현재 fingerprint          [d]
Keys   = 가전별 상태 레퍼런스 행렬  [n_states, d]
Values = Keys와 동일 (self-retrieval)

attention_score = softmax(Q · Kᵀ / √d)    shape: [n_states]
→ argmax → 최종 상태 레이블
→ entropy(attention_score) → 분류 확신도
```

### Phase 1: Non-parametric (학습 불필요)

내적 기반 유사도를 softmax로 정규화 → 학습 없이 즉시 적용 가능.  
기존 레퍼런스 JSON 그대로 사용.

```python
def classify_mode_attention(appliance, fingerprint, references):
    app_refs = references.get(appliance)
    if not app_refs or fingerprint is None:
        return None, None

    fp = np.array(fingerprint, dtype=np.float32)         # [d]
    fp_norm = fp / (np.linalg.norm(fp) + 1e-8)          # L2 정규화

    state_names, ref_matrix = [], []
    for state_name, ref_vec in app_refs.items():
        ref = np.array(ref_vec, dtype=np.float32)
        if not np.any(ref):
            continue
        ref_norm = ref / (np.linalg.norm(ref) + 1e-8)
        state_names.append(state_name)
        ref_matrix.append(ref_norm)

    K = np.stack(ref_matrix, axis=0)                     # [n_states, d]
    d = K.shape[1]

    # Scaled dot-product attention
    scores = (fp_norm @ K.T) / np.sqrt(d)                # [n_states]
    weights = _softmax(scores)                            # [n_states]

    best_idx = int(np.argmax(weights))
    entropy = float(-np.sum(weights * np.log(weights + 1e-8)))

    return state_names[best_idx], {
        'weights': dict(zip(state_names, weights.tolist())),
        'entropy': entropy,                               # 낮을수록 확신도 높음
    }

def _softmax(x):
    e = np.exp(x - x.max())
    return e / e.sum()
```

**출력 추가값:**
| 키 | 설명 | 활용 |
|----|------|------|
| `weights` | 각 상태별 attention weight | 해석 가능성(어느 레퍼런스와 얼마나 유사한지) |
| `entropy` | 분류 불확실성 | entropy가 높으면 TDA 입력 신뢰도 낮음 → 통계 기반 분류로 폴백 |

### Phase 2: Parametric (선택적, 학습 필요)

레퍼런스 수집 데이터가 충분할 때 Q/K projection 레이어를 추가로 학습.

```
fp → Linear(d, d_attn) → Q    (학습됨)
K  → Linear(d, d_attn) → K'   (학습됨)
→ 이후 Phase 1과 동일
```

Phase 1 성능이 충분하면 생략해도 무방. **포폴 목적이라면 Phase 1만으로도 설명 가능.**

---

## 3. 구현 단계

| 단계 | 작업 | 비고 |
|------|------|------|
| **Step 1** | 노트북에 `classify_mode_attention()` 추가 | 기존 `classify_mode()`는 삭제하지 않고 병렬 유지 |
| **Step 2** | `ShortTermEvent`에 `mode_confidence: float` 필드 추가 | entropy 값 저장 → JSON에 결과가 visible해야 포폴 설명 가능 |
| **Step 3** | `ShortTermBuilder._make_event()`에서 두 함수 모두 호출해 결과 비교 컬럼 추가 | `tda_mode_l2` vs `tda_mode_attn` |
| **Step 4** | Ablation: house_054 데이터로 두 방식 mode 분류 결과 비교 출력 | 일치율, entropy 분포 확인 |
| **Step 5** | entropy 기반 fallback 로직 연결 | entropy > 임계값이면 L2 결과 사용 |
| **Step 6** | (선택) Phase 2 parametric 구현 | 레이블 데이터 충분 시 |

> **주의:** `mode_confidence` 추가 시 하류(LLM 진단 쪽)에서 JSON을 파싱하는 부분이 있으면 영향 확인 필요.

---

## 4. 검증 방법

### 정량 비교 (Ablation)

```python
# 비교 출력 예시 (Step 2 결과)
appliance  | mode_l2     | mode_attn   | attn_entropy | 일치
-----------+-------------+-------------+--------------+------
에어컨      | cool_medium | cool_medium | 0.41         | ✓
에어컨      | cool_high   | fan_low     | 1.89         | ✗  ← entropy 높음 → 신뢰도 낮은 구간
김치냉장고  | cool_low    | cool_low    | 0.28         | ✓
```

**기대 결과:**
- entropy 낮은 구간: L2와 일치율 높음 (attention이 확신하는 경우)
- entropy 높은 구간: L2와 불일치 발생, 이 구간이 실제로 경계 구간인지 시각화로 확인

### 시각화

attention weight를 상태별 bar chart로 출력 → "왜 cool_medium으로 분류했는지" 설명 가능.

---

## 5. 포폴 스토리 (면접 설명 포인트)

```
"Persistence Image(TDA 결과 벡터)를 레퍼런스와 비교할 때
단순 L2 distance 대신 Scaled Dot-Product Attention을 사용했습니다.

이유:
Persistence Image는 birth/death 위치에 따라 변별력이 다른데,
L2는 이를 균등하게 취급합니다.
Attention은 내적 기반으로 방향적 유사도를 보기 때문에
이 구조에 더 적합합니다.

추가로 Softmax entropy를 분류 확신도 지표로 활용해,
불확실한 구간은 통계 기반 분류로 폴백하는 하이브리드 구조를 만들었습니다."
```

**차별화 포인트:**
- TDA(Persistent Homology) + Attention 조합: 논문에서도 드문 조합
- Non-parametric이라 학습 데이터 없이도 즉시 적용 가능
- entropy 기반 폴백으로 실서비스 수준의 신뢰도 관리 구조

