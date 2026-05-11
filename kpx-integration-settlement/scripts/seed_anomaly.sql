-- ============================================================
-- Anomaly Mock Seed
-- appliance_status_codes (신규 테이블) + appliance_status_intervals 시드 데이터
--
-- 목적: NILM 엔진 실데이터 생성 전 임시 목업으로 이상탐지 기능 개발/테스트
-- 대상: power_1hour 실데이터 보유 10개 가구
--       H011 H015 H016 H017 H033 H039 H049 H054 H063 H067
--
-- 교체 방법: NILM 엔진 운영 후 아래 쿼리로 목업 행 삭제
--   DELETE FROM appliance_status_intervals WHERE model_version = 'nilm-v2.1-mock';
-- ============================================================

BEGIN;

-- ── 1. appliance_status_codes 테이블 생성 ──────────────────────────────────────
--  appliance_status_intervals.status_code 의 FK 대상.
--  confidence >= 0.85 → severity=warning, < 0.85 → info (data_tools.py 기준).

CREATE TABLE IF NOT EXISTS appliance_status_codes (
    status_code TEXT PRIMARY KEY,
    label_ko    TEXT NOT NULL,
    description TEXT
);

INSERT INTO appliance_status_codes (status_code, label_ko, description) VALUES
    ('ABNORMAL_CONSUMPTION', '비정상 소비 패턴', '평시 대비 30% 이상 높은 소비량 지속'),
    ('HIGH_STANDBY',         '대기전력 과다',   '비활성 시간대 평소 대비 높은 대기전력 감지'),
    ('LONG_HIGH_POWER',      '장시간 고출력',   '일반 가동 시간 초과 고출력 가동 지속'),
    ('VOLTAGE_SPIKE',        '이상 전압 급등',  '순간 전력 급등 후 자동 차단 또는 재가동 감지'),
    ('DOOR_OPEN_PATTERN',    '도어 개방 패턴',  '냉장·냉동고 도어 장시간 개방 의심 패턴'),
    ('FILTER_DEGRADATION',   '필터 성능 저하',  '에어컨·공기청정기 필터 오염으로 인한 효율 저하')
ON CONFLICT (status_code) DO NOTHING;

-- ── 2. appliance_status_intervals 시드 데이터 ──────────────────────────────────
-- channel_num: household_channels 서브쿼리로 참조 (하드코딩 방지).
-- channel_num > 1 조건: ch01은 전체 전력, ch02+ 가 개별 가전.
-- 해당 가구에 channel_num 데이터가 없으면 0 rows → INSERT 무시.
--
-- 분포 설계:
--   활성(end_ts IS NULL) : H011 H015 H039 H049 H054 H067  → anomaly_diagnoses 비어있지 않음
--   해결됨(end_ts 있음)  : H016 H017 H049(2번째) H067(3번째) → 로그에는 나타남
--   이상 없음            : H033 H063                          → anomaly_diagnoses 빈 배열

-- H011 ─ 활성 경고: 비정상 소비 패턴 (confidence 0.89 ≥ 0.85 → warning)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H011', channel_num, 'ABNORMAL_CONSUMPTION', 0.89, 'nilm-v2.1-mock',
       NOW() - INTERVAL '4 days', NULL, NOW() - INTERVAL '4 days'
FROM household_channels
WHERE household_id = 'H011' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H011 ─ 해결됨: 필터 성능 저하 (이력 로그용)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H011', channel_num, 'FILTER_DEGRADATION', 0.76, 'nilm-v2.1-mock',
       NOW() - INTERVAL '20 days',
       NOW() - INTERVAL '18 days',
       NOW() - INTERVAL '20 days'
FROM household_channels
WHERE household_id = 'H011' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H015 ─ 활성 정보: 대기전력 과다 (confidence 0.71 < 0.85 → info)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H015', channel_num, 'HIGH_STANDBY', 0.71, 'nilm-v2.1-mock',
       NOW() - INTERVAL '2 days', NULL, NOW() - INTERVAL '2 days'
FROM household_channels
WHERE household_id = 'H015' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H016 ─ 해결됨: 장시간 고출력 (활성 이벤트 없음 → anomaly_diagnoses 빈 배열)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H016', channel_num, 'LONG_HIGH_POWER', 0.83, 'nilm-v2.1-mock',
       NOW() - INTERVAL '10 days',
       NOW() - INTERVAL '9 days',
       NOW() - INTERVAL '10 days'
FROM household_channels
WHERE household_id = 'H016' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H017 ─ 해결됨: 이상 전압 급등 (활성 이벤트 없음)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H017', channel_num, 'VOLTAGE_SPIKE', 0.94, 'nilm-v2.1-mock',
       NOW() - INTERVAL '7 days',
       NOW() - INTERVAL '7 days' + INTERVAL '30 minutes',
       NOW() - INTERVAL '7 days'
FROM household_channels
WHERE household_id = 'H017' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H033 ─ 이상 없음 (INSERT 없음)

-- H039 ─ 활성 경고: 이상 전압 급등 (confidence 0.92 ≥ 0.85 → warning)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H039', channel_num, 'VOLTAGE_SPIKE', 0.92, 'nilm-v2.1-mock',
       NOW() - INTERVAL '1 day', NULL, NOW() - INTERVAL '1 day'
FROM household_channels
WHERE household_id = 'H039' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H049 ─ 활성 정보: 대기전력 과다 (confidence 0.68 < 0.85 → info)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H049', channel_num, 'HIGH_STANDBY', 0.68, 'nilm-v2.1-mock',
       NOW() - INTERVAL '3 days', NULL, NOW() - INTERVAL '3 days'
FROM household_channels
WHERE household_id = 'H049' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H049 ─ 해결됨: 비정상 소비 패턴 (두 번째 채널 사용)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H049', channel_num, 'ABNORMAL_CONSUMPTION', 0.86, 'nilm-v2.1-mock',
       NOW() - INTERVAL '14 days',
       NOW() - INTERVAL '13 days',
       NOW() - INTERVAL '14 days'
FROM (
    SELECT channel_num
    FROM household_channels
    WHERE household_id = 'H049' AND channel_num > 1
    ORDER BY channel_num
    LIMIT 2
) t
ORDER BY channel_num DESC
LIMIT 1;

-- H054 ─ 활성 정보: 장시간 고출력 (confidence 0.77 < 0.85 → info)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H054', channel_num, 'LONG_HIGH_POWER', 0.77, 'nilm-v2.1-mock',
       NOW() - INTERVAL '5 days', NULL, NOW() - INTERVAL '5 days'
FROM household_channels
WHERE household_id = 'H054' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H063 ─ 이상 없음 (INSERT 없음)

-- H067 ─ 활성 경고: 비정상 소비 패턴 (첫 번째 채널, confidence 0.88 ≥ 0.85 → warning)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H067', channel_num, 'ABNORMAL_CONSUMPTION', 0.88, 'nilm-v2.1-mock',
       NOW() - INTERVAL '2 days', NULL, NOW() - INTERVAL '2 days'
FROM household_channels
WHERE household_id = 'H067' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

-- H067 ─ 활성 정보: 도어 개방 패턴 (두 번째 채널, confidence 0.73 < 0.85 → info)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H067', channel_num, 'DOOR_OPEN_PATTERN', 0.73, 'nilm-v2.1-mock',
       NOW() - INTERVAL '6 days', NULL, NOW() - INTERVAL '6 days'
FROM (
    SELECT channel_num
    FROM household_channels
    WHERE household_id = 'H067' AND channel_num > 1
    ORDER BY channel_num
    LIMIT 2
) t
ORDER BY channel_num DESC
LIMIT 1;

-- H067 ─ 해결됨: 이상 전압 급등 (이력 로그용)
INSERT INTO appliance_status_intervals
    (household_id, channel_num, status_code, confidence, model_version, start_ts, end_ts, created_at)
SELECT 'H067', channel_num, 'VOLTAGE_SPIKE', 0.91, 'nilm-v2.1-mock',
       NOW() - INTERVAL '15 days',
       NOW() - INTERVAL '15 days' + INTERVAL '20 minutes',
       NOW() - INTERVAL '15 days'
FROM household_channels
WHERE household_id = 'H067' AND channel_num > 1
ORDER BY channel_num LIMIT 1;

COMMIT;
