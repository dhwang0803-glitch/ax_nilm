# 모니터링 엔진 설계서

> 기존 이상탐지 엔진에서 **모니터링 엔진**으로 방향 전환 (2026-05-12)
> LLM 진단(ANOM-003)에 맥락 데이터를 공급하는 것이 핵심 목표.

---

## 1. 전체 목표

가전별 맥락 정보를 만들어 단기/장기 메모리에 저장한다.

```
"에어컨이 cool_high 모드로 1시간 사용해서 3000Wh를 소모했다"  ← 단기 메모리
"에어컨 cool_high 1시간 기준 소비 = 1000Wh"                  ← 장기 메모리 (기준값)
```

LLM 진단은 단기↔장기를 비교해 이상을 판단한다. **진단은 내 담당 아님.**

---

## 2. 단기 vs 장기 메모리

| 구분 | 갱신 주기 | 내용 | 초기화 |
|------|----------|------|--------|
| 단기 | 1시간 누적 업데이트 | 가전별 모드·소비량·대기 이벤트 | 매일 00시 장기로 압축 후 리셋 |
| 장기 | 24시간 1회 업데이트 | 가전별 평균 소비 기준값·패턴 | 누적 (삭제 없음) |

### 저장 방식

**PoC**: JSON 파일 — LLM 진단 쪽에서 파일 직접 읽어 프롬프트에 주입. DB 연결 불필요.

```
memory/
  short_term/
    house_001.json        ← 매시간 업데이트, 00시 리셋
  long_term/
    house_001.json        ← 24h 1회 갱신
  cold_start/
    reference_images.json ← 상태별 TDA 레퍼런스 Persistence Image
    baseline.json         ← 10가구 평균 소비 기준값
```

**프로덕션 전환 시**: 단기 → Redis (TTL 24h), 장기 → TimescaleDB

### 단기 메모리 이벤트 스키마

```json
{
  "appliance": "에어컨",
  "mode": "cool_high",
  "started_at": "2026-05-12T14:00:00",
  "duration_min": 60,
  "energy_wh": 3000.0,
  "avg_w": 3000.0,
  "peak_w": 3200.0,
  "tda_fingerprint": [0.12, 0.03, ...],
  "standby": {
    "duration_min": 30,
    "avg_w": 6.0,
    "energy_wh": 3.0
  }
}
```

### 장기 메모리 기준값 스키마

```json
{
  "에어컨": {
    "cool_high": {
      "avg_energy_wh": 1000.0,
      "avg_duration_min": 90.0,
      "tda_reference": [0.11, 0.02, ...]
    },
    "standby_avg_w": 6.0,
    "standby_avg_duration_min": 20.0
  }
}
```

---

## 3. 파이프라인 구조

```
P(t) 시계열 (NILM 분해 결과)
        ↓
[TDA 레이어] — TDA 적용 가전 (10종)
  P(t) → 시간지연 임베딩 → Persistent Homology → Persistence Image
        ↓
  레퍼런스 이미지와 Wasserstein 거리 비교
        ↓
  모드 판별 + tda_fingerprint 저장

[통계 레이어] — 전체 22종
  energy / duration / peak / 대기전력 수치 집계
        ↓
단기 메모리 이벤트 조립
        ↓ (00시)
장기 메모리 EWM 갱신
```

**역할 분담:**
- TDA → **어떤 모드인지** (레퍼런스와 유사도 비교로 상태 판별) + tda_fingerprint 저장
- 통계 → **얼마나** (energy, duration, peak)
- 모드 판별 없는 가전 (TDA 미적용 12종) → thresholds.yaml W 범위 룩업 유지

---

## 4. TDA 상태 판별 방식

### 레퍼런스 이미지 기반 상태 판별

```
[오프라인 - cold start]
GCS 10가구 P(t) 원본
  + K-Means (thresholds.yaml K값)으로 상태별 구간 추출
    → 각 구간 P(t) / max_w (global 정규화)
    → time-delay embedding (dim=3, lag=10) → Vietoris-Rips H1 → Persistence Image (20×20)
    → 상태별 평균 → 레퍼런스 이미지
    → cold_start/reference_images.json 저장

[실시간]
현재 P(t) → global 정규화 (/ max_w) → Persistence Image (20×20)
  → cosine attention으로 레퍼런스 이미지들과 유사도 계산
  → softmax → entropy 계산
  → entropy ≤ 1.0 → attention 최대 상태 = 현재 모드
  → entropy > 1.0 → W 범위 룩업 fallback
```

### TDA 적용 10종

| idx | 가전 | 상태 수 | 비고 |
|-----|------|--------|------|
| 3 | 의류건조기 | 4 | standby/drum/dry_mid/dry_high |
| 4 | 전기밥솥 | 2 | keep_warm/cook |
| 5 | 식기세척기/건조기 | 3 | rinse/wash/heat_dry |
| 6 | 세탁기 | 2 | wash/spin |
| 11 | 에어컨 | 3 | fan_low/cool_medium/cool_high |
| 13 | 전기장판/담요 | 2 | low/high |
| 14 | 온수매트 | 3 | low/medium/high |
| 15 | 제습기 | 3 | fan_only/dehumid_low/dehumid_high |
| 19 | 일반 냉장고 | 3 | standby/cool/defrost |
| 20 | 김치냉장고 | 3 | fan/cool_low/cool_high |

### thresholds.yaml W 범위 적용 12종

TDA 레퍼런스 없이 W 범위 룩업으로 모드 분류.
TV, 전기포트, 선풍기, 헤어드라이기, 에어프라이어, 진공청소기, 전자레인지,
인덕션, 전기다리미, 컴퓨터, 공기청정기, 무선공유기/셋톱박스

### 분류기 결정 이력

- L2 거리 → cosine attention + entropy gate로 교체 완료 (2026-05-14)
- Silhouette 검증 결과: 온수매트 0.540, 세탁기 0.750, 에어컨 0.504 (모두 ≥ 0.5 통과)
- EMBED_LAG=10 최적 확인, per-segment silhouette 기준 채택 (W-range GT 불필요)

---

## 5. TDA 레퍼런스 구축 (cold start)

> 상세: [`labeling/state_labeling.md`](../labeling/state_labeling.md)

- **원본 데이터**: GCS 10가구 30Hz P(t) (house_011/015/016/017/033/039/049/054/063/067)
- **상태 경계**: state_labeling.md 골짜기/K-means 임계값 (thresholds.yaml에 확정값 저장)
- **구축 스크립트**: `labeling/scripts/build_tda_references.ipynb` (Colab, 미작성)
- **출력**: `memory/cold_start/reference_images.json`

```json
{
  "에어컨": {
    "fan_low":      [0.01, 0.02, ...],
    "cool_medium":  [0.08, 0.11, ...],
    "cool_high":    [0.15, 0.23, ...]
  },
  ...
}
```

### 주의 사항 (state_labeling.md 기준)

- 에어컨: 신뢰 채널 3개만 사용 (house_015/054/063), 나머지 6채널 품질 미달
- 일반 냉장고: 실루엣 점수 0.61 — 경계 불명확, 레퍼런스 품질 검토 필요
- 세탁기/인덕션: valley 피크 없음, K-Means 결과로 경계 설정

---

## 6. 대기전력 감지

대기전력 신호는 flat → TDA 불필요. threshold 기반으로만 처리.

대기 구간 조건:
```
STANDBY_MIN_W(1W) < power_w < ON_THRESHOLD[appliance]
AND duration > 30분
```

단기 메모리에 측정값만 저장 (판단은 LLM 진단 담당):
- `standby_duration_min` — 지속 시간
- `standby_avg_w` — 평균 W값
- `standby_energy_wh` — 누적 에너지

---

## 7. 구현 현황

| 파일 | 상태 |
|------|------|
| `src/models/schemas.py` | ✅ DisaggregationResult |
| `src/detectors/statistical.py` | ✅ ON_THRESHOLDS, ALWAYS_ON |
| `src/memory/schemas.py` | ✅ ShortTermEvent, ApplianceBaseline |
| `src/memory/store.py` | ✅ JSON read/write |
| `src/memory/builder.py` | ✅ TDA attention 모드 재분류 + global 정규화 + entropy gate + rolling mean + 히스테리시스 + 대기전력 감지 |
| `src/memory/compressor.py` | ✅ EWM 장기 갱신 |
| `src/tda/mode_detector.py` | ✅ ripser H1 → Persistence Image (global 정규화) + `classify_mode_attention()` cosine attention |
| `src/monitoring_service.py` | ✅ public API (`references_path` 파라미터 포함) |
| `tests/` | ✅ builder / compressor / mode_detector (27개) |
| `labeling/scripts/validate_tda_states.ipynb` | ✅ per-segment silhouette 검증 완료 |
| `labeling/scripts/build_tda_references.ipynb` | ✅ 10종 레퍼런스 구축 완료 (K-Means + global 정규화) |
| `memory/cold_start/reference_images.json` | ✅ 10종 완료 (0-vector 없음) |
| `memory/cold_start/baseline.json` | ✅ 10종 완료 |
| `scripts/e2e_monitoring_colab.ipynb` | ✅ global 정규화 + attention 분류기로 업데이트 완료 |

---

## 8. 미결 사항

1. **TDA 연산 비용**: 실시간 ripser 지연 허용 범위 확인
2. **에어컨 레퍼런스 품질**: 하절기 데이터 부족으로 cool_high 클러스터에 이상치 혼입 → 여름 데이터 추가 후 재검증 필요
3. **e2e 검증**: `e2e_monitoring_colab.ipynb` Colab 재실행으로 attention 분류기 통합 확인 필요

--- 

## 9. 설계 결정 로그

### 9-1. 임계값 oscillation 문제 및 rolling mean + 히스테리시스 채택 (2026-05-14)

**발견 경위**: E2E 테스트 (house_054, 20231018, 00~04시) 단기 메모리 분석

| 가전 | 전체 이벤트 | zero-duration | 노이즈% |
|------|------------|--------------|--------|
| 온수매트 | 3,347 | 3,216 | 98.1% |
| 일반 냉장고 | 367 | 298 | 88.3% |
| TV | 127 | 63 | 74.0% |

**근본 원인**: 임계값 경계 설정 오류가 아님. 세 가전 모두 동일한 물리적 패턴:
- 온수매트: 히팅 코일 듀티사이클 → 130.8W(low/medium) 경계 교차
- 일반 냉장고: 컴프레서 ON/OFF 사이클 → 52W(standby/cool) 경계 교차 (ALWAYS_ON이라 on_thr 필터 미적용)
- TV: standby 중 네트워크 폴링 스파이크 → 27.8W(standby/on) 경계 교차

rolling mean 단독으로는 불충분: 듀티사이클 평균이 경계값과 일치할 경우 평균화 후에도 진동 지속.

**기각된 해결책 — `_MIN_EVENT_MIN=0.5` 필터**:
마이크로 세그먼트를 사후 제거하면 해당 시간대 에너지가 누락됨.
가전이 실제로 가동 중인데 "사용 안 함"으로 처리되는 구조적 오류.

**채택된 해결책 — 1초 rolling mean + 히스테리시스**:
현재 모드에서 이탈하려면 경계를 `_HYSTERESIS_W(10W)` 추가로 넘어야 함.

```python
smoothed_w = work["power_w"].rolling("1s", min_periods=1).mean().values
work["mode"] = _classify_with_hysteresis(smoothed_w, states)
# _classify_with_hysteresis: 경계 ±10W dead-band 상태 머신
```
에너지·peak_w 계산은 raw `power_w` 그대로 유지.

### 9-2. `_load_cold_start()` 포맷 불일치 버그 수정 (2026-05-14)

`baseline.json` 실제 포맷: `{가전명: {모드명: {avg_energy_wh, avg_duration_min, sample_count, tda_reference}}}`
기존 코드는 `_baseline_from_dict()`에 전달 시 `{"appliance": ..., "modes": ...}` 구조를 기대해 TypeError 발생.
`store.py`의 `_load_cold_start()`를 직접 파싱하도록 재작성.

### 9-3. E2E 테스트 결과 요약 (2026-05-14)

대상: house_054, 20231018, 00~04시 (4시간), MAX_HOURS=4 제한
```
TDA 이벤트:   210개
W 범위 이벤트: 133개
cold start:   10종 로드
에러:         없음
```
주요 모드 분포 (rolling mean 적용 전 기준):
- 일반 냉장고 standby +0.0%, cool +0.0%
- 전기밥솥 keep_warm, 컴퓨터 active 등 정상 분류 확인

rolling mean + 히스테리시스 적용 후 재실행 결과 (2026-05-14):
```
TDA 이벤트:   201개
W 범위 이벤트: 8개  (133 → 8, TV/에어컨/컴퓨터 micro-segment 제거)
온수매트:     3,347 → 131개 (zero-duration 3,216 → 0)
```
raw 신호 확인 결과 온수매트 131개는 써모스탯 사이클 (ON ~30초 / OFF ~4분) — 정상 동작.

### 9-4. TDA per-segment 정규화 결함 (2026-05-14)

**발견 경위**: E2E 재실행 후 온수매트 TDA 분류 결과 확인
```
[TDA 분류] 온수매트: high 66개, medium 65개
그러나 raw 신호 최대값 < 301.6W (medium/high 경계) — high 분류 불가능
```

**근본 원인**: `compute_fingerprint()` 내 per-segment 정규화
```python
norm = (signal - s_min) / (s_max - s_min)  # 진폭 정보 소실
```
세그먼트별로 0~1 정규화 → 220W 스파이크와 350W 스파이크가 동일한 shape → TDA가 진폭으로 구분 불가.

**영향 범위**: 모드가 전력값으로만 구분되는 가전에서 TDA 오분류 발생 가능.
TDA가 유효한 경우: 같은 전력 범위에서 신호 shape이 다른 모드 (예: 세탁기 wash/spin).

**채택할 해결책 — W-range 검증**:
TDA 결과와 W-range 결과가 다를 경우 W-range 우선 적용.
전력값이 실제로 해당 모드 범위에 없으면 TDA 결과를 신뢰하지 않음.
```python
# _make_event() 안에서
tda_mode = classify_mode(appliance, fingerprint, self._references)
if tda_mode is not None and tda_mode == w_range_mode:
    mode = tda_mode  # TDA와 W-range 일치 → TDA 사용
# 불일치 시 W-range 유지 (기본값)
```

**보류 중인 근본 fix**: per-segment 정규화 → 가전 전체 범위 정규화 (`signal / appliance_max_w`)로 교체.
TDA 레퍼런스 전체 재구축 필요 — 데이터 충분히 확보 후 적용.
