# NILM 모델 ↔ DB 인터페이스 스펙

> **대상 독자**: CNN+TDA 하이브리드 NILM 모델 개발 팀 (Execution Engine)
> **관련 요구사항**: REQ-001 (NILM 엔진), REQ-002 (이상 탐지)
> **관련 스키마**: `Database/schemas/004_nilm_inference_tables.sql` (예정)
> **상위 결정**: `Database/docs/schema_design.md` §4 라벨 정책

## 1. 배경

AI Hub 71685 데이터셋은 가전별 30Hz 전력값을 **이미 분리해서 제공**하고 ON 구간 라벨(`active_inactive`)도 첨부되어 있다. 이는 Seq2Point 계열 지도학습의 정답(ground truth)으로 사용된다.

본 프로젝트는 **CNN + TDA(Topological Data Analysis) 하이브리드** 구조로 NILM을 구현하므로 출력이 단순 ON/OFF 라벨을 넘어 **상세한 가전 상태 분류**가 가능하다. 예:

| 가전 유형 (루트 CLAUDE.md) | 예상 상태 세트 |
|---------------------------|---------------|
| Type 1 단일 ON/OFF (토스터, 전기밥솥 등) | `off`, `active` |
| Type 2 다중상태 (세탁기, 건조기, 식기세척기) | `idle`, `wash`, `rinse`, `spin`, `dry` ... |
| Type 3 무한상태 (조명 디머, 인버터 에어컨) | `off`, `low`, `mid`, `high` 또는 연속 가변의 양자화 bucket |
| Type 4 영구소비 (냉장고, 인터넷 모뎀) | `compressor_off`, `compressor_on`, `defrost` |

이 상세 상태를 **이상 탐지 feature** 로 직결 활용한다 (상태 시퀀스 이상, 지속시간 이상, 시간대 패턴 이상).

## 2. 출력 형식 — 구간 기반 (interval-based)

모델 출력은 **행 단위가 아니라 구간 단위**. 각 구간 = 한 상태가 유지되는 시간 범위.

- **상태가 바뀌지 않은 시간 구간은 새 행을 발행하지 않는다** — 동일 상태가 1시간 유지되면 해당 구간은 단 1행.
- **상태 전환 시각이 곧 이벤트 타임스탬프** — 이 INSERT 시점이 프론트엔드 알림 / SMTP 메일 트리거의 원천.
- **진행 중 구간은 `end_ts = NULL`** 로 표현한다. 다음 전환 발생 시 기존 행을 UPDATE 하여 `end_ts` 를 채우고 새 행을 INSERT.

### 스키마 (확정안)

```sql
CREATE TABLE appliance_status_intervals (
    id             BIGSERIAL   PRIMARY KEY,
    household_id   TEXT        NOT NULL,
    channel_num    SMALLINT    NOT NULL,
    start_ts       TIMESTAMPTZ NOT NULL,   -- 상태 전환 발생 시각 (= 이벤트 타임스탬프)
    end_ts         TIMESTAMPTZ,            -- NULL = 현재 진행 중. 다음 전환 시 UPDATE
    status_code    SMALLINT    NOT NULL,   -- appliance_status_codes 참조
    confidence     REAL,                   -- [0.0, 1.0] — 0.6 미만은 이상탐지 집계 제외
    model_version  TEXT        NOT NULL,   -- 'cnn_tda_v1' 등
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (end_ts IS NULL OR start_ts < end_ts),
    FOREIGN KEY (household_id, channel_num)
        REFERENCES household_channels(household_id, channel_num) ON DELETE CASCADE,
    -- 동일 (가구·채널·모델버전) 에서 시간 구간 겹침 차단
    EXCLUDE USING gist (
        household_id  WITH =,
        channel_num   WITH =,
        model_version WITH =,
        tstzrange(start_ts, COALESCE(end_ts, 'infinity'), '[)') WITH &&
    )
);

-- 현재 진행 중 구간 = "지금 상태" O(log N) 조회
CREATE INDEX idx_status_open
    ON appliance_status_intervals (household_id, channel_num, model_version)
    WHERE end_ts IS NULL;

-- 전환 히스토리 / 시간대별 패턴 조회
CREATE INDEX idx_status_history
    ON appliance_status_intervals (household_id, channel_num, start_ts DESC);


CREATE TABLE appliance_status_codes (
    status_code    SMALLINT    PRIMARY KEY,
    label_en       TEXT        NOT NULL,
    label_ko       TEXT,
    appliance_code TEXT        REFERENCES appliance_types(appliance_code),
    description    TEXT
);
```

## 3. 적재 트랜잭션 (모델/ETL 쪽 구현)

상태 전환 발생 시 단일 트랜잭션으로 다음 2개 문장을 수행한다.

```sql
BEGIN;
-- 1) 이전 열린 구간 종료
UPDATE appliance_status_intervals
   SET end_ts = :transition_ts
 WHERE household_id = :h
   AND channel_num = :c
   AND model_version = :v
   AND end_ts IS NULL;

-- 2) 새 구간 시작 (INSERT = 전환 이벤트 발행)
INSERT INTO appliance_status_intervals
  (household_id, channel_num, start_ts, status_code, confidence, model_version)
VALUES
  (:h, :c, :transition_ts, :new_status, :conf, :v);
COMMIT;
```

Repository 구현체 `NILMInferenceRepository.record_transition(...)` 가 이 트랜잭션을 감싼다.

## 4. 실시간 알림 경로

```
CNN+TDA 추론 → INSERT → AFTER INSERT TRIGGER → pg_notify('status_change', json)
                                                       ↓
                                          LISTEN 하는 백엔드 워커
                                                       ↓
                 ┌─────────────────────────────────────┼─────────────────────────────────────┐
                 ↓                                     ↓                                     ↓
       이상탐지 판정 로직                      프론트 WebSocket push                    SMTP 메일
       → anomaly_events INSERT                (error / warning 태그)                  (심각도 HIGH)
```

- 초기 단계는 **Postgres `pg_notify`/`LISTEN`** 으로 시작 (경량, 인프라 추가 없음).
- 부하 가시화 시 Kafka / Redis Streams 로 전환 (루트 CLAUDE.md 기술 스택에 Kafka 포함).

`appliance_status_intervals` 는 **모든 상태 전환** 을 기록하고, 그 중 이상 판정된 건만 `anomaly_events` 로 승격된다 (피드백 ③).

## 5. 모델 팀 확정 요청 사항

아래 항목은 **초기 모델 돌려본 뒤** 확정 가능. 확정 전까지는 스키마를 유지한 채로 진행하고, 확정 후 마이그레이션으로 반영한다.

### 5.1 상태 코드 세트 (`appliance_status_codes` seed)

가전 유형별로 사용할 `status_code` 정수 값과 의미를 제안 바랍니다. 초기 제안 범위:

| status_code 범위 | 가전 유형 / 용도 |
|------------------|-------------------|
| 0–9 | 범용 (off, standby, active, peak 등) |
| 10–19 | Type 2 가전 상세 (wash/rinse/spin/dry ...) |
| 20–29 | Type 4 주기성 (compressor_on/off, defrost ...) |
| 30–99 | 예약 |

**제안 예시** (데이터 베이스 확정 전 placeholder):
```
0  off              — 전원 OFF / 소비량 거의 0
1  standby          — 대기전력 수준
2  active           — 일반 동작
3  peak             — 피크 구간

10 wash             — 세탁기/식기세척기 세척
11 rinse            — 헹굼
12 spin             — 탈수
13 dry              — 건조

20 compressor_off   — 냉장고/에어컨 compressor OFF (내부 순환 중)
21 compressor_on    — compressor ON
22 defrost          — 성에 제거
```

### 5.2 확정 필요 파라미터

1. **추론 주기 / 전환 판정 지연**
   - 모델이 몇 초 단위로 판정하는가? → `start_ts` 시간 정밀도 / "짧은 전환 노이즈" 제거 임계
2. **`confidence` 정의**
   - Softmax 최댓값? / TDA persistence 기반 별도 지표? / 앙상블 불일치도?
   - 0.6 미만 제외 (피드백) 기준이 적절한지 초기 분포로 재검증
3. **Type 3 가전 (무한상태) 양자화 방식**
   - 연속 가변 출력(예: 조명 디머)을 몇 개 bucket 으로 양자화? 또는 별도 연속값 컬럼 필요?
4. **Type 4 가전 주기성 처리**
   - 냉장고 compressor 의 on/off 주기를 그대로 상태 전환으로 적재? → 하루 100+ 전환 행이 정상. DB 볼륨 예측에 반영 필요
5. **`model_version` 갱신 주기 / 네이밍 규칙**
   - 예: `cnn_tda_v1.0.0`, `cnn_tda_v1.1.0-tuned` 등 semver? 또는 실험 ID?
6. **재추론 정책**
   - 과거 구간 재추론 결과를 같은 `model_version` 으로 덮어쓸지, 새 `model_version` 으로 공존할지?

### 5.3 테스트 데이터 교환 포맷

초기 통합 테스트는 **Parquet 또는 JSONL** 로 파일 전달:

```json
{"household_id": "H001", "channel_num": 4, "start_ts": "2024-07-12T08:23:45+09:00", "end_ts": "2024-07-12T08:47:12+09:00", "status_code": 11, "confidence": 0.87, "model_version": "cnn_tda_v0.1.0"}
```

DB 팀이 제공하는 로더: `scripts/load_nilm_inference.py` (예정).

## 6. 현재 적재 정책 요약 (초기 세팅)

- **본 PR 에는 스키마만 포함**. 실제 데이터 적재는 CNN+TDA 모델이 동작한 뒤.
- 초기 모델 출력 1 주일치가 나온 시점에 5.1 / 5.2 를 확정하여 다음 PR 에서:
  - `appliance_status_codes` seed 적재
  - `confidence` 분포에 따른 집계 필터 임계값 확정
  - 필요 시 컬럼 추가 (feature 메타 등)

## 7. 확장 시나리오와 리스크

| 확장 유형 | 예상 변경 | 리스크 |
|----------|----------|--------|
| 새 `status_code` 추가 | `appliance_status_codes` INSERT | 낮음 |
| 컬럼 추가 (TDA feature 벡터 메타 등) | `ALTER TABLE ADD COLUMN` (NULL 허용) | 낮음 |
| `model_version` A/B 병존 | 신규 행만 INSERT | 낮음 |
| 구간 → 1분 샘플 해상도 전환 | 테이블 재설계 | **중간** — 초기 모델 결과 확인 전까지는 구간 방식 고수 |
| 재추론 대량 백필 | `model_version` 신규 적재 후 기존 정리 | 낮음 (단, 저장 용량 2× 고려) |

## 8. 의존 관계

- 업스트림: `household_channels` (FK), `appliance_status_codes` (코드 정의)
- 다운스트림: `anomaly_events` (상태 전환 중 이상 판정 결과 승격)
- 평가 비교 대상: `activity_intervals` (AI Hub 라벨 — ground truth)

동일 (가구, 채널, 기간) 에 대해 `activity_intervals` ↔ `appliance_status_intervals` 를 JOIN 하여 IoU / precision / recall / F1 평가.

```sql
-- ground truth vs 모델 출력 비교 (예시)
SELECT
    gt.household_id, gt.channel_num,
    gt.start_ts AS gt_start, gt.end_ts AS gt_end,
    m.start_ts  AS pred_start, m.end_ts AS pred_end, m.status_code, m.confidence
FROM activity_intervals gt
LEFT JOIN appliance_status_intervals m
  ON  gt.household_id = m.household_id
 AND gt.channel_num  = m.channel_num
 AND m.model_version = 'cnn_tda_v1'
 AND tstzrange(gt.start_ts, gt.end_ts, '[]') && tstzrange(m.start_ts, COALESCE(m.end_ts, 'infinity'), '[)')
WHERE gt.household_id = 'H001' AND gt.channel_num = 4;
```

---

**피드백 / 확정 요청**: 본 문서의 §5.1, §5.2 항목을 모델 팀에서 채워 회신 부탁드립니다. 초기 모델이 돌면서 나오는 실제 출력값 분포에 맞춰 반복 조정하는 방식으로 진행하면 됩니다.
