# TDA 모드 분류 구조적 문제 및 개선 방향

> 작성일: 2026-05-14  
> 발견 경위: attention 검증 실험 중 TDA가 W-range를 한 번도 override하지 않음을 확인

---

## 1. 문제

### 현재 구조

```
W-range(valley/K-Means)로 상태 경계 정의
    → 상태별 TDA 레퍼런스(PI 벡터) 생성
    → classify_mode()로 TDA 분류 시도
    → W-range 검증: TDA 결과가 avg_w 범위 안에 있어야 채택
```

### 왜 작동하지 않는가

모든 상태 경계가 **non-overlapping W-range**로 정의되어 있다.  
avg_w가 A 범위에 있으면 TDA가 B를 제안해도 B의 W 범위를 벗어남 → 검증 실패.  
결과적으로 TDA가 W-range를 override한 케이스: **0건** (house_054 201개 이벤트 검증).

TDA는 W-range가 맞춘 76건에서 "동의"만 하고 있을 뿐, 실질적 역할이 없다.

### 근본 원인

> W-range로 상태를 정의하고 TDA로 분류하는 것은 구조적으로 모순이다.  
> TDA가 분류 가치를 갖는 것은 **"같은 W 범위 안에서 신호 모양이 다른 상태"** 가 있을 때뿐이다.

valley/K-Means 기반 라벨링은 설계 자체가 W-range non-overlapping을 만들기 때문에  
TDA 개입 여지가 없다.

---

## 2. 추가 발견: Attention Phase 1 실패 원인

cosine 기반 attention(Phase 1) 검증 결과:

- entropy ≈ ln(n_states) 수렴 → attention weight 완전 균등 분포
- PI 벡터들이 방향은 비슷하고 크기만 다름 → L2 normalization 후 cosine 유사도 차이 소멸
- L2 distance는 상태 간 차이가 존재하나, 이는 W-range 검증에 막혀 결과에 반영 안 됨

→ [`attention_validation_result.md`](attention_validation_result.md) 참조

---

## 3. 개선 방향: TDA 기반 라벨링

### 아이디어

상태를 W-range로 먼저 정의하지 않고, **PI 벡터 클러스터링으로 상태 자체를 발견**한다.

```
P(t) 세그먼트 수집
    → compute_fingerprint() → PI 벡터
    → 비지도 클러스터링 (K-Means / DBSCAN)
    → 클러스터 = 상태 정의
    → 클러스터 중심 = TDA 레퍼런스
```

TDA가 상태를 정의했으므로 TDA로 분류하는 것이 일관된다.  
W-range 검증 제거 가능 (또는 soft constraint로 변경).

### 기대 가능한 가전

| 가전 | 근거 |
|------|------|
| 세탁기 | wash(불규칙 진동) vs spin(고주파 주기) — P(t) 위상 구조 차이 가능 |
| 에어컨 | 압축기 on(복잡 진동) vs fan only(단순 주기) — 명확히 다른 패턴 |
| 냉장고 | 압축기 사이클링 패턴이 상태마다 다를 수 있음 |

### 기대 어려운 가전

| 가전 | 근거 |
|------|------|
| 선풍기 | 30kHz PLAID에서도 high/medium 구별 불가 확인 |
| 전자레인지 | PLAID 분석에서 전 상태 유사 패턴 |

### 선행 검증 필요

TDA 기반 라벨링 전, PI 벡터가 클러스터링에 충분한 변별력을 갖는지 먼저 확인:

```
1. 가전별 P(t) 세그먼트 100~200개 수집
2. PI 벡터 계산 후 실루엣 점수 기반 최적 K 탐색
3. K-Means 클러스터가 물리적으로 의미 있는지 수작업 검토
   (예: 클러스터 A = 압축기 on 구간인가?)
4. 변별력 있으면 → 클러스터 중심을 레퍼런스로 교체
   변별력 없으면 → TDA mode 분류 포기, 이상 감지 용도로 전환
```

---

## 4. 작업 규모

Phase 2(parametric attention)보다 더 큰 작업:

| 항목 | 내용 |
|------|------|
| PI 벡터 대량 계산 | 전 학습 데이터 대상 compute_fingerprint() |
| 클러스터링 실험 | 가전별 K 탐색 + 실루엣 검증 |
| 수작업 검토 | 클러스터 물리적 의미 확인 |
| 파이프라인 수정 | W-range 검증 제거 또는 soft constraint 변경 |

**시간 확보 후 진행 예정.**
