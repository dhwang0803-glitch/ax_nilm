# F1=0.464 원인 진단 및 개선 방안

> 현재 모델: CNN+TDA Hybrid (CNNTDAHybrid)  
> 기준 지표: validation F1 = 0.464  
> 작성일: 2026-04-28

---

## 핵심 요약

F1=0.464의 구조적 원인은 **회귀 손실 + center 1샘플 라벨 + 임계값 binarize** 세 요소가 결합되어 multi-label 분류 작업의 학습 신호가 약화된 것이다.  
TDA 정보 빈곤, 윈도우 커버리지 부족이 이를 증폭시킨다.

---

## 문제점 목록

### 문제 1 — 목적함수 불일치 (심각도: 높음)

**위치:** [scripts/train_model.py:95–107](../scripts/train_model.py), [scripts/train_model.py:165–168](../scripts/train_model.py)

**현상:**
- 학습 손실: `masked_weighted_mse` — 22채널 전력값을 회귀로 맞춤
- 평가 지표: F1 — `pred >= norm_thr` binarize 후 ON/OFF 정확도 측정
- 두 목표가 약하게 연결되어 손실이 낮아도 F1이 높아지지 않는 구조

**심화 요인:**  
`on_off_c` (ON 구간 가중치 기준)도 center 1샘플 기준 ([train_model.py:227](../scripts/train_model.py)). 윈도우 안에 ON 구간이 있어도 center 순간이 OFF면 `on_weight=5` 혜택 없음 → 문제 2와 결합 효과가 큼.

**Confidence gate collapse 위험 ([cnn_tda.py:114–127](../src/models/cnn_tda.py)):**  
`pred = confidence * cnn_pred + (1-confidence) * fusion_pred` 구조에서 gate가 0 또는 1로 편향 수렴하면 나머지 헤드의 gradient가 희박해져 한쪽 헤드가 사실상 학습되지 않음. 현재 gate에 entropy penalty나 정규화 없음 — center 라벨 노이즈가 심할수록 gate 불안정이 커짐.

---

### 문제 2 — center 1샘플 학습/평가 (심각도: 높음)

**위치:** [scripts/train_model.py:132–133](../scripts/train_model.py), [scripts/train_model.py:225–226](../scripts/train_model.py)

**현상:**
- 윈도우 1024 중 center 인덱스(512) 1개 값만 라벨로 사용
- type2(전자레인지, 헤어드라이어 등) 가전은 center가 ON일 확률이 매우 낮음 → 0 예측이 강한 local minimum
- `on_weight=5` 균등 가중이지만 가전별 ON 빈도 차이가 100배 이상 — 냉장고(거의 항상 ON)와 헤어드라이어(거의 항상 OFF)에 같은 5배는 부적절

---

### 문제 3 — TDA 절대 전력 정보 부족 (심각도: 중간)

**위치:** [src/features/tda.py:34–35](../src/features/tda.py)

**현상:**
- H0/H1 persistence features는 0~1 정규화된 신호 기반 → 50W TV와 5000W 인덕션이 같은 모양이면 동일한 위상 특징 생성
- magnitude 정보를 담은 것은 signal_stats 4개(mean, std, range, zcr)뿐
- TDA_DIM=20 중 16차원(H0+H1)이 shape only, 4차원만 magnitude → 22가전 구분에 비율이 부족

**ZCR 품질 문제:**  
원본 신호 기준 ZCR은 고주파 노이즈로 인한 spurious crossing을 포함해 가전 패턴 구분력이 낮았음. **wavelet denoising 적용 후 개선됨** (→ 현황 참고).

**Cross-Attention 관련 오해 정정:**  
`attn_proj(20)` 병목이 아님. 실제 흐름: `TDA(20) → tda_mlp → 64 → 128(_TDA_EMBED)`, Cross-Attention은 128차원 기준 동작. 병목은 128이 아니라 **raw TDA feature가 20차원** 이라는 입력 빈곤.

---

### 문제 4 — 윈도우 커버리지 부족 (심각도: 중간)

**현상:**
- 1024 샘플 @ 30Hz = 34.1초 커버
- 세탁기, 식기세척기, 의류건조기는 동작 사이클이 분~시간 단위 → 34초로는 사이클 단편만 관찰
- 사이클 패턴을 캡처하지 못해 cycle-level 가전 식별 불가

**주의:** 30Hz 자체는 transient 식별에 유리한 샘플링 레이트이므로 다운샘플은 tradeoff가 있음.

---

## 현재 적용된 개선 (2026-04-28)

### 적용됨 — wavelet denoising (문제 3 부분 기여)

**위치:** [src/acquisition/gcs_loader.py:17–26](../src/acquisition/gcs_loader.py)

```python
def _wavelet_denoise(signal, wavelet="db4", level=1):
    coeffs = pywt.wavedec(signal, wavelet, level=level)
    sigma = np.median(np.abs(coeffs[-1])) / 0.6745  # MAD 추정
    threshold = sigma * np.sqrt(2 * np.log(max(len(signal), 2)))
    coeffs[1:] = [pywt.threshold(c, threshold, mode="soft") for c in coeffs[1:]]
    denoised = pywt.waverec(coeffs, wavelet)
    return np.clip(denoised[:len(signal)], 0, None).astype(np.float32)
```

- `agg_power`에만 적용, `target_power` 라벨은 그대로
- level=1: 최고주파수 성분만 제거 → transient 보존
- H0/H1 persistence feature 품질 개선, ZCR 노이즈 제거
- 결과 보고 후 효과 있으면 level=2 검토

**⚠️ 주의:** 기존 TDA 캐시(`tda_*.pt`)가 있으면 denoising 이전 신호로 만들어진 캐시를 로드하므로 효과 없음. 캐시 삭제 후 재계산 필요.

```bash
find <cache_dir> -name "tda_*.pt" -delete
```

---

## 개선 방안 (우선순위순)

### A. dual head — 분류 분기 추가 ★ 최우선

**목표 문제:** 문제 1 (목적함수 불일치)  
**예상 효과:** F1과 손실 정합 → 학습 신호가 ON/OFF 분류로 명확해짐. 가장 큰 F1 향상 기대.

**구현 방향:**
1. 기존 `cnn_head` / `fusion_head` 출력에 **BCE loss를 추가** (MSE는 에너지 추정 보조 loss로 weight 축소)
2. 채널별 `pos_weight = neg_count / pos_count` 적용 — 균등 5배 대신 실제 불균형 비율로 보정

```python
# 채널별 pos_weight 계산 (train set 기준)
on_counts  = on_off_train.sum(axis=0)          # (22,)
off_counts = len(on_off_train) - on_counts
pos_weight = torch.tensor(off_counts / on_counts.clip(min=1), dtype=torch.float32)

bce_loss = F.binary_cross_entropy_with_logits(
    logits, labels, pos_weight=pos_weight.to(device)
)
total_loss = bce_loss + 0.1 * mse_loss  # MSE는 보조
```

3. 평가 F1도 BCE logits 기준 binarize로 전환 (임계값 고정 또는 채널별 최적화)

**구현 시 주의:**
- 기존 confidence-gated soft mixture 구조는 유지. 헤드 출력에 loss만 추가하는 방식이 이식 비용 최소화.
- `pos_weight` 계산은 현재 center 1샘플 ON 비율 기준 — center가 OFF인 비율이 높은 가전은 pos_weight가 과대 추정됨. **D 방안(윈도우 합의 라벨)과 세트로 적용하면 pos_weight 정확도도 함께 개선됨.**
- `bce_loss + 0.1 * mse_loss`에서 `0.1`은 초기 추정값. on_weight sweep(검증 4번)과 함께 0.05~0.2 범위로 조정.
- Gate collapse 방지를 위해 BCE 도입 후 gate 분포(평균/분산)를 에폭마다 로깅해 편향 수렴 여부 모니터링 권장.

---

### B. 이벤트 기반 샘플링 (A 이후)

**목표 문제:** 문제 2 (center 1샘플) 간접 완화  
**전제 조건:** A 적용 후 진행 권장. A 없이 B만 하면 희귀 이벤트 center sample이 늘어날 뿐, 회귀 손실이 ON 신호를 충분히 캡처하지 못하는 구조는 그대로.

**구현 방향:**
- 이벤트(transient) 감지 → 이벤트 중심으로 윈도우 정렬
- ON 상태 윈도우 비율 증가 → trivial-zero local minimum 탈출

**효과 측정:** A 적용 → A+B 순으로 ablation 측정.

#### event_context 값 결정

현재 `event_context=20` (전환점 앞뒤 각 20초). 결정 근거 문서 없음 — 22종 가전 중 가장 느린 transient를 가진 에어컨 기동 시간(~20초)을 커버하려고 보수적으로 잡은 것으로 추정.

**±20초가 과다한 이유:**

| 가전 | 실제 transient | ±20s 윈도우 내 비율 |
|------|--------------|-------------------|
| 전기포트, 헤어드라이어 | 0.5~3초 | 대부분이 steady-state |
| 세탁기, 에어프라이어 | 5~15초 | 적당 |
| 에어컨, 냉장고 | 15~30초 | 필요 |

빠른 가전일수록 ±20s 윈도우 대부분이 transient가 아닌 평탄 구간이라, 모델 입장에서 "이 가전이 켜질 때 패턴"이 전체 윈도우 안에서 희석됨.

**결정된 튜닝 순서:**

1. **EXP4까지 현재(event_context=20) 결과 확인** — F1/SAE 추세 보고
2. **event_context=10으로 변경 후 재실행** — `config/dataset.yaml`에서 수정
   ```yaml
   window:
     event_context: 10   # 20 → 10 (전환점 ±10초)
   ```
3. **캐시 무효화** — npz(raw segments)는 재사용 가능하지만 window 구성이 달라지므로 TDA 캐시는 전부 삭제 후 재계산
   ```bash
   find <cache_dir> -name "tda_*.pt" -delete
   ```
4. **결과 비교** — F1 올라가고 SAE 내려가면 10초가 더 적합한 값으로 확정

---

### C. TDA feature 확충 및 정규화 변경

**목표 문제:** 문제 3 (TDA 정보 빈곤)

**방안 1 — 정규화 변경:**
```python
# 현재
sig_norm = (sig_sub - sig_sub.min()) / sig_range

# 변경안: P95 기반 robust scale → 절대 magnitude 보존
p95 = np.percentile(sig_sub, 95)
sig_norm = sig_sub / (p95 + 1e-6)
```

**방안 2 — magnitude 정보 보강:**
```python
# magnitude 4분위 one-hot (4dim) 추가
# TDA_DIM = 20 → 24
magnitude_bucket = np.digitize(signal.mean(), bins=[100, 500, 2000])
magnitude_onehot = np.eye(4)[magnitude_bucket]  # (4,)
feat = np.concatenate([h0_feat, h1_feat, sig_feat, magnitude_onehot])
```

**방안 3 — feature 수 확대:**
- `_persistence_stats`의 `top_k` 5 → 10 으로 늘려 H0(13) + H1(13) + signal_stats(4) = 30차원
- `TDA_DIM` 상수 업데이트 (`tda.py`와 `cnn_tda.py` 동시 수정)

**⚠️ 주의:** TDA_DIM 변경 시 기존 TDA 캐시 전체 재계산 필요.

---

### D. 평가/학습 라벨 — 윈도우 합의 기반으로 변경 (A와 세트 권장)

**목표 문제:** 문제 2 (center 1샘플), 평가 노이즈 감소

**방향:**  
center 1점 binarize 대신 윈도우 중앙 N% 구간 평균 ON 비율로 라벨 결정.

```python
# 현재
target_c = target[:, :, center]      # 1점
on_off_c = on_off[:, :, center]

# 변경안: 중앙 25% 구간 평균
half = window_size // 4
s, e = center - half, center + half
target_c = target[:, :, s:e].mean(dim=-1)
on_off_c = (on_off[:, :, s:e].float().mean(dim=-1) >= 0.5)
```

**주의:** 학습 타깃(`target_c`)과 평가 라벨(`t_on`) 두 곳 모두 변경해야 train-eval 불일치 방지.  
A와 함께 적용하면 pos_weight 계산 기준도 합의 구간 ON 비율로 일치시킬 수 있어 시너지 있음.

---

### E. 멀티스케일 입력 (자원 여유 시)

**목표 문제:** 문제 4 (윈도우 커버리지)

**방향:**
- Stream 1: 30Hz 1024 (34초, transient 캡처)
- Stream 2: 30Hz에서 subsample → 1Hz 1024 (17분 윈도우, cycle 캡처)
- 두 stream의 CNN embedding을 concat 후 공유 head

**우선순위 낮은 이유:** 아키텍처 변경 범위가 크고, A~D 효과 측정 후 판단해도 늦지 않음.

---

## 검증 단계 (권장 순서)

| 순서 | 검증 항목 | 목적 |
|------|----------|------|
| 1 | CNN only (TDA 제거) 학습 → F1 비교 | TDA 기여량 측정. 차이 없으면 C 작업 가치 올라감 |
| 2 | 채널별 ON ratio 출력 (train set center 기준) | type2 가전이 1% 미만이면 trivial-zero 함정 확정 |
| 3 | 모델 예측값 채널별 평균/표준편차 출력 | 0 근방으로 몰려 있으면 local minimum 확정 |
| 4 | `on_weight` sweep: 1, 5, 20, 50 → F1 변화 | A 도입 전 sanity check, pos_weight 스케일 감 파악 |
| 5 | EXP4까지 현재 결과 확인 (event_context=20) | F1/SAE 추세 파악 후 B 튜닝 기준 수립 |
| 6 | A+D 적용 후 F1 측정 | baseline 대비 개선 폭 확인. gate 분포 로깅 병행 |
| 7 | A+D+B (event_context=20) F1 측정 | B 단독 기여 분리 |
| 8 | event_context=10으로 변경 후 F1 측정 | 빠른 가전 transient 희석 완화 효과 확인 |

---

## 파일별 수정 예상 범위

| 파일 | 변경 항목 | 해당 방안 |
|------|----------|----------|
| `scripts/train_model.py` | BCE loss 추가, pos_weight 계산, 라벨 합의 로직, gate 분포 로깅 | A, D |
| `src/features/tda.py` | 정규화 변경, top_k 확대, TDA_DIM 상수 | C |
| `src/models/cnn_tda.py` | (구조 변경 없음, TDA_DIM import만) | C |
| `src/acquisition/gcs_loader.py` | ~~_wavelet_denoise~~ (적용 완료) | — |
| `src/acquisition/dataset.py` | 이벤트 기반 샘플링 로직 | B |
| `config/dataset.yaml` | `event_context: 20 → 10` | B |
