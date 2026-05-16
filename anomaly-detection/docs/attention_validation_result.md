# Attention Phase 1 검증 결과

> 작성일: 2026-05-14  
> 검증 노트북: [`scripts/validate_attention.ipynb`](../scripts/validate_attention.ipynb)  
> 데이터: `house_054 / 20231018` 단기 메모리 (총 201개 TDA fingerprint 이벤트)

---

## 결과 요약

| 지표 | 값 |
|------|-----|
| L2 vs Attention 일치율 | 67.2% |
| Fallback 비율 (entropy > 1.0) | **98.0%** |
| 가전별 평균 entropy | ln(n_states)에 수렴 |

### 가전별 상세

| 가전 | 이벤트 수 | L2 일치율 | 평균 entropy | n_states |
|------|-----------|-----------|--------------|----------|
| 전기밥솥 | 4 | 100% | 0.693 | 2 |
| 김치냉장고 | 4 | 100% | 1.099 | 3 |
| 일반 냉장고 | 62 | 100% | 1.099 | 3 |
| 온수매트 | 131 | 49.6% | 1.099 | 3 |

---

## 분석

### entropy가 ln(n_states)에 수렴하는 이유

entropy = ln(n_states)는 **완전 균등 분포**를 의미한다.  
즉 attention weight가 모든 레퍼런스에 동일하게 분산되어 상태 구별을 못하고 있다.

**원인**: Scaled Dot-Product Attention은 L2 정규화된 벡터 간 내적(코사인 유사도)을 본다.  
현재 Persistence Image 벡터들은 상태 간 **방향이 비슷하고 크기만 다르다.**  
→ 정규화하면 방향 차이가 사라져 dot product가 균등해짐.

L2는 절대 거리를 보기 때문에 크기 차이를 구별할 수 있지만,  
Attention(코사인 기반)은 이 데이터 구조에서 변별력이 없다.

### L2 vs Attention 불일치 33%의 의미

불일치 구간에서 어느 쪽이 맞는지 ground truth(실제 상태 라벨)가 없어 검증 불가.  
→ 우열 판단 자체가 불가능.

---

## 결론

**Phase 1 Non-parametric Attention은 현재 TDA fingerprint에 적합하지 않다.**

이는 사전에 예상됐던 리스크("TDA 변별력 불확실 문제")가 실제로 발생한 케이스다.  
Persistence Image가 방향보다 크기로 상태를 구분하는 구조이기 때문에  
코사인 유사도 기반 attention은 이 용도에 맞지 않는다.

---

## 향후 선택지

| 방향 | 내용 | 난이도 |
|------|------|--------|
| **현행 유지** | L2 distance 유지, attention 도입 보류 | - |
| **거리 기반 attention** | `softmax(-L2_dist / τ)` — 방향 아닌 거리를 attention으로 변환 | 낮음 |
| **Phase 2 parametric** | W_Q/W_K 학습으로 방향 차이를 만드는 임베딩 공간 학습 — **데이터 충분, 시간 확보 후 구현 예정** | 높음 |

### 거리 기반 attention (가장 현실적인 대안)

코사인 유사도 대신 L2 거리를 음수 변환해 softmax 적용:

```python
# scores = (fp_norm @ K.T) / sqrt(d)  ← 기존 (코사인)
dists = np.array([np.linalg.norm(fp - ref) for ref in ref_vecs])
scores = -dists / tau   # tau: temperature (작을수록 sharp)
weights = softmax(scores)
```

- L2의 절대 거리 정보를 유지하면서 entropy(확신도)를 계산 가능
- 추가 학습 불필요
- attention 구조를 유지하므로 포폴 설명 가능
