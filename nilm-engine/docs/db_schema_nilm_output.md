# NILM 엔진 출력 DB 스키마 설계서

> **수신**: Database 모듈 담당자  
> **발신**: NILM 엔진 팀  
> **목적**: NILM 분해 결과를 DB에 저장하기 위한 테이블 구조 정의  
> **연관 요구사항**: REQ-001 (NILM 분해), REQ-002 (이상 탐지), REQ-004 (데이터 관리)

---

## 1. NILM 엔진이 생산하는 데이터

`NILMDisaggregator.disaggregate()` 호출 결과:

```python
# 입력: 단일 분전반 30Hz 전력 시계열 (N 샘플)
power_series: np.ndarray  # shape (N,), 단위: W

# 출력: 가전 22종 × N 샘플 추정 전력
{
    "에어컨":           np.ndarray,  # shape (N,), 단위: W
    "세탁기":           np.ndarray,
    "일반 냉장고":      np.ndarray,
    # ... 총 22종
}
```

ON/OFF 판정은 가전 타입별 고정 임계값으로 결정:

| 타입 | 해당 가전 | ON 임계값 |
|------|---------|---------|
| type1 | TV, 전기포트, 선풍기 | 30 W |
| type2 | 세탁기, 에어프라이어, 전자레인지 등 8종 | 20 W |
| type3 | 에어컨, 인덕션, 컴퓨터 등 9종 | 50 W |
| type4 | 냉장고, 김치냉장고, 공유기/셋톱박스 | 5 W |

---

## 2. 테이블 구조

### 테이블 1 — `nilm_power_ts` (원시 시계열)

TimescaleDB hypertable. `time` 기준 파티션 권장 (1일 단위).

```sql
CREATE TABLE nilm_power_ts (
    time            TIMESTAMPTZ     NOT NULL,
    household_id    TEXT            NOT NULL,
    appliance_id    SMALLINT        NOT NULL,  -- 0~21 고정 인덱스 (아래 매핑표 참고)
    power_w         REAL            NOT NULL,  -- 예측 전력 [W], 음수 불가 (클리핑 처리 후 저장)
    is_on           BOOLEAN         NOT NULL,  -- power_w >= ON 임계값
    confidence      REAL            NOT NULL   -- NILM 모델 신뢰도 0.0~1.0
);

SELECT create_hypertable('nilm_power_ts', 'time');
CREATE INDEX ON nilm_power_ts (household_id, appliance_id, time DESC);
```

**각 컬럼 설명**

| 컬럼 | 필요한 이유 |
|------|-----------|
| `time` | 30Hz → 초당 30행. 시계열 쿼리·집계의 파티션 키 |
| `household_id` | 다가구 분리 |
| `appliance_id` | 22종 중 어떤 가전인지. TEXT 대신 SMALLINT로 저장 크기 절약 |
| `power_w` | 이상 탐지: 평소 대비 소비 전력 비교 기준 |
| `is_on` | 이상 탐지: 가전이 켜진 시간대 분석, 세션 추출 기준 |
| `confidence` | **이상 탐지 필터링 필수** — 낮은 신뢰도(< 0.4) 예측은 알람 발생 제외 |

> **confidence 저장이 중요한 이유**  
> NILM 모델은 두 경로로 예측한다:  
> - `confidence ≥ 0.5` → CNN 단독 예측 (빠르지만 단순 패턴에 특화)  
> - `confidence < 0.5` → CNN + TDA fusion 예측 (복잡한 패턴)  
>
> 신뢰도 낮은 예측(0.3 이하)이 이상 탐지 알람을 발생시키면 오탐률이 높아진다.
> 이상 탐지 로직에서 `confidence < 0.4` 구간은 분석 대상에서 제외하거나 별도 처리 권장.

---

### 테이블 2 — `nilm_sessions` (가전 작동 세션)

NILM 엔진이 `is_on` 전환 감지 시 삽입/갱신. 이상 탐지의 **핵심 테이블**.

```sql
CREATE TABLE nilm_sessions (
    session_id      BIGSERIAL       PRIMARY KEY,
    household_id    TEXT            NOT NULL,
    appliance_id    SMALLINT        NOT NULL,
    started_at      TIMESTAMPTZ     NOT NULL,  -- ON 전환 시각
    ended_at        TIMESTAMPTZ,               -- OFF 전환 시각 (진행 중이면 NULL)
    duration_s      INTEGER,                   -- 세션 길이 [초] (ended_at 확정 후 계산)
    energy_wh       REAL,                      -- 세션 누적 전력량 [Wh]
    avg_power_w     REAL,                      -- 세션 평균 전력 [W]
    peak_power_w    REAL,                      -- 세션 최대 전력 [W]
    avg_confidence  REAL                       -- 세션 평균 신뢰도
);

CREATE INDEX ON nilm_sessions (household_id, appliance_id, started_at DESC);
CREATE INDEX ON nilm_sessions (ended_at) WHERE ended_at IS NULL;  -- 진행 중 세션 조회
```

**각 컬럼 설명**

| 컬럼 | 이상 탐지 활용 예 |
|------|----------------|
| `started_at` | 비정상 시간대 작동 감지 (새벽 3시 에어컨 ON 등) |
| `ended_at` | 진행 중 세션 감지 (세탁기 3시간째 작동 중) |
| `duration_s` | 평균 작동 시간 대비 이상 감지 ("세탁기 평균 45분인데 오늘 3시간") |
| `energy_wh` | 평균 에너지 대비 이상 감지 ("냉장고 오늘 평소 2배 소비") |
| `avg_power_w` | 성능 저하 감지 ("에어컨 평균 소비가 지난달 대비 30% 증가") |
| `peak_power_w` | 급격한 부하 이상 감지 |
| `avg_confidence` | 신뢰도 낮은 세션 전체 필터링용 |

---

### 가전 ID 매핑 (`appliance_id` 0~21)

| ID | 가전 | 타입 | ON 임계값 |
|----|------|------|---------|
| 0 | TV | type1 | 30 W |
| 1 | 전기포트 | type1 | 30 W |
| 2 | 선풍기 | type1 | 30 W |
| 3 | 의류건조기 | type2 | 20 W |
| 4 | 전기밥솥 | type2 | 20 W |
| 5 | 식기세척기/건조기 | type2 | 20 W |
| 6 | 세탁기 | type2 | 20 W |
| 7 | 헤어드라이기 | type2 | 20 W |
| 8 | 에어프라이어 | type2 | 20 W |
| 9 | 진공청소기(유선) | type2 | 20 W |
| 10 | 전자레인지 | type2 | 20 W |
| 11 | 에어컨 | type3 | 50 W |
| 12 | 인덕션(전기레인지) | type3 | 50 W |
| 13 | 전기장판/담요 | type3 | 50 W |
| 14 | 온수매트 | type3 | 50 W |
| 15 | 제습기 | type3 | 50 W |
| 16 | 컴퓨터 | type3 | 50 W |
| 17 | 공기청정기 | type3 | 50 W |
| 18 | 전기다리미 | type3 | 50 W |
| 19 | 일반 냉장고 | type4 | 5 W |
| 20 | 김치냉장고 | type4 | 5 W |
| 21 | 무선공유기/셋톱박스 | type4 | 5 W |

---

## 3. 이상 탐지 쿼리 예시

이상 탐지 모듈이 아래와 같이 `nilm_sessions`를 조회한다고 가정한다.

```sql
-- 예시 1: 세탁기가 평균보다 2배 이상 오래 작동한 세션
SELECT session_id, household_id, started_at, duration_s
FROM nilm_sessions
WHERE appliance_id = 6          -- 세탁기
  AND duration_s > (
      SELECT AVG(duration_s) * 2
      FROM nilm_sessions
      WHERE appliance_id = 6
        AND household_id = nilm_sessions.household_id
        AND ended_at IS NOT NULL
  )
  AND avg_confidence >= 0.4;    -- 신뢰도 필터

-- 예시 2: 냉장고 일별 세션 수 이상 감지 (평균 대비 2배 초과)
SELECT DATE(started_at), COUNT(*) as session_count
FROM nilm_sessions
WHERE appliance_id IN (19, 20)  -- 냉장고 2종
  AND household_id = 'house_011'
GROUP BY DATE(started_at)
HAVING COUNT(*) > 30;           -- 임계값은 이상 탐지 모듈에서 동적 계산
```

---

## 4. 데이터 볼륨 추정

| 항목 | 수치 |
|------|------|
| 샘플링 주기 | 30Hz (33ms) |
| 가전 수 | 22종 |
| `nilm_power_ts` 행/초/가구 | 30 × 22 = **660 행/초** |
| `nilm_power_ts` 행/일/가구 | 약 **5,700만 행** |
| `nilm_power_ts` 용량/일/가구 | 약 **1.5 GB** (비압축 기준) |
| TimescaleDB 압축 후 | 약 **150~300 MB** |
| `nilm_sessions` 행/일/가구 | 약 **50~200 행** (가전 활동에 따라 상이) |

> **권장**: `nilm_power_ts`는 최근 30일만 원본 보관, 이후 시간 집계(1분 평균)로 다운샘플링.  
> 이상 탐지에 필요한 원시 파형이 필요하면 `started_at ± 5분` 구간만 조회.

---

## 5. NILM 엔진 → DB 쓰기 인터페이스 (협의 필요)

NILM 엔진이 DB에 쓸 때 아래 두 가지 중 어느 방식을 쓸지 협의 필요:

| 방식 | 장점 | 단점 |
|------|------|------|
| **A. 엔진이 직접 INSERT** | 단순 | DB 커넥션 관리를 엔진이 담당 |
| **B. Kafka 토픽 경유** | 백압력 처리, DB 모듈 독립 | Kafka 인프라 필요 (REQ-004 기준 이미 포함) |

REQ-004에 Kafka가 명시되어 있으므로 **B 방식(Kafka → ETL → DB)** 을 권장한다.  
NILM 엔진은 결과를 `nilm.disaggregation` 토픽에 발행하고, DB 모듈의 consumer가 적재한다.

**Kafka 메시지 스키마 (JSON)**

```json
{
  "household_id": "house_011",
  "timestamp":    "2024-03-01T14:32:00.033Z",
  "predictions": [
    { "appliance_id": 11, "power_w": 1240.5, "is_on": true,  "confidence": 0.82 },
    { "appliance_id": 19, "power_w": 85.3,   "is_on": true,  "confidence": 0.91 },
    { "appliance_id": 6,  "power_w": 0.0,    "is_on": false, "confidence": 0.76 }
  ]
}
```

> `is_on = false`인 가전은 `nilm_power_ts` 저장 생략 가능 (용량 절감).  
> 단, `is_on` 전환 시점(OFF→ON, ON→OFF)은 반드시 저장해야 `nilm_sessions` 생성 가능.

---

## 6. 미결 사항 (DB 팀 확인 요청)

- [ ] TimescaleDB 압축 정책 — retention 기간 및 다운샘플링 집계 단위 결정 필요
- [ ] `nilm_sessions.ended_at IS NULL` 세션의 타임아웃 처리 — 엔진 재시작 시 미종료 세션 어떻게 처리할지
- [ ] `confidence` 필터 임계값 — 이상 탐지 팀과 0.4 기준 적절성 협의 필요
- [ ] Kafka 토픽명 및 파티션 전략 — `household_id` 기준 파티셔닝 권장
