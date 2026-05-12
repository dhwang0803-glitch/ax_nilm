-- migration 14: households.billing_day 추가
--
-- KEPCO 에너지캐시백 산정 기간은 달력 월이 아닌 검침일 기준 사이클.
-- 예) 검침일 15일 → 10월분 = 9월 15일 ~ 10월 14일
-- NULL 허용: 검침일 미확인 가구는 달력 월 fallback 처리.

ALTER TABLE households
    ADD COLUMN IF NOT EXISTS billing_day SMALLINT
        CONSTRAINT chk_households_billing_day CHECK (billing_day BETWEEN 1 AND 28);

COMMENT ON COLUMN households.billing_day IS
    'KEPCO 전기요금 검침일 (1~28). NULL = 달력 월 기준으로 캐시백 기준선 산정.';
