-- ax_nilm — P2 3.1 appliance_types 에 NILM 모델 출력 인덱스 컬럼 추가
-- 의존: schemas/001_core_tables.sql (appliance_types), schemas/003_seed_appliance_types.sql
-- 출처 분석: docs/pending_db_requests.md §3.1
--
-- 배경:
--   nilm-engine src/classifier/label_map.py 의 APPLIANCE_LABELS 배열 순서가
--   곧 모델 출력 인덱스(0~21)다. 이는 DB 의 default_channel(AI Hub 채널 1~23)과
--   순서가 다르다.
--     예: 모델 idx 1 = 전기포트(KETTLE, ch04)
--         모델 idx 2 = 선풍기(FAN,    ch03)
--   추론 결과를 appliance_status_intervals 에 적재할 때 모델 인덱스 → appliance_code
--   번역이 필수다. label_map.py 한글 라벨 문자열은 표기 차이가 있어(예: NILM
--   "식기세척기/건조기" vs DB "식기세척기") 비교가 어렵고, 인덱스만이 안정적인 키다.
--
-- 정책:
--   * MAIN(ch01) 은 NILM 출력 대상이 아니므로 NULL 허용.
--   * 22 가전은 인덱스 0~21 과 1:1 매칭 (UNIQUE).
--   * DB 가 단일 진실 소스 — nilm-engine 측에 새 가전 추가 시 본 컬럼을 먼저 갱신한 뒤
--     label_map.py 를 동기화한다.

BEGIN;

ALTER TABLE appliance_types
    ADD COLUMN IF NOT EXISTS nilm_label_index SMALLINT;

ALTER TABLE appliance_types
    ADD CONSTRAINT chk_appliance_types_nilm_label_index_range
        CHECK (nilm_label_index IS NULL OR nilm_label_index BETWEEN 0 AND 21);

ALTER TABLE appliance_types
    ADD CONSTRAINT uq_appliance_types_nilm_label_index
        UNIQUE (nilm_label_index);

-- nilm-engine label_map.py APPLIANCE_LABELS 배열 순서 그대로 백필.
-- 한글 라벨이 아닌 appliance_code 로 매칭 — 표기 차이(식기세척기/건조기,
-- 진공청소기(유선), 컴퓨터(데스크탑), 일반 냉장고, 인덕션(전기레인지)) 무시.
UPDATE appliance_types SET nilm_label_index =  0 WHERE appliance_code = 'TV';
UPDATE appliance_types SET nilm_label_index =  1 WHERE appliance_code = 'KETTLE';
UPDATE appliance_types SET nilm_label_index =  2 WHERE appliance_code = 'FAN';
UPDATE appliance_types SET nilm_label_index =  3 WHERE appliance_code = 'DRYER';
UPDATE appliance_types SET nilm_label_index =  4 WHERE appliance_code = 'RICE_COOKER';
UPDATE appliance_types SET nilm_label_index =  5 WHERE appliance_code = 'DISHWASHER';
UPDATE appliance_types SET nilm_label_index =  6 WHERE appliance_code = 'WASHER';
UPDATE appliance_types SET nilm_label_index =  7 WHERE appliance_code = 'HAIR_DRYER';
UPDATE appliance_types SET nilm_label_index =  8 WHERE appliance_code = 'AIR_FRYER';
UPDATE appliance_types SET nilm_label_index =  9 WHERE appliance_code = 'VACUUM';
UPDATE appliance_types SET nilm_label_index = 10 WHERE appliance_code = 'MICROWAVE';
UPDATE appliance_types SET nilm_label_index = 11 WHERE appliance_code = 'AC';
UPDATE appliance_types SET nilm_label_index = 12 WHERE appliance_code = 'INDUCTION';
UPDATE appliance_types SET nilm_label_index = 13 WHERE appliance_code = 'ELEC_BLANKET';
UPDATE appliance_types SET nilm_label_index = 14 WHERE appliance_code = 'HOT_MAT';
UPDATE appliance_types SET nilm_label_index = 15 WHERE appliance_code = 'DEHUMIDIFIER';
UPDATE appliance_types SET nilm_label_index = 16 WHERE appliance_code = 'PC';
UPDATE appliance_types SET nilm_label_index = 17 WHERE appliance_code = 'AIR_PURIFIER';
UPDATE appliance_types SET nilm_label_index = 18 WHERE appliance_code = 'IRON';
UPDATE appliance_types SET nilm_label_index = 19 WHERE appliance_code = 'FRIDGE';
UPDATE appliance_types SET nilm_label_index = 20 WHERE appliance_code = 'KIMCHI_FRIDGE';
UPDATE appliance_types SET nilm_label_index = 21 WHERE appliance_code = 'ROUTER';

-- 22 가전 모두 채워졌는지 검증 — 매핑 누락 시 마이그레이션을 실패시킨다.
DO $$
DECLARE
    filled_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO filled_count
    FROM appliance_types
    WHERE nilm_label_index IS NOT NULL
      AND appliance_code <> 'MAIN';

    IF filled_count <> 22 THEN
        RAISE EXCEPTION
            'nilm_label_index 매핑 누락: %/22 행만 채워짐. label_map.py 와 appliance_code 동기화 확인 필요.',
            filled_count;
    END IF;
END
$$;

COMMENT ON COLUMN appliance_types.nilm_label_index IS
    'nilm-engine src/classifier/label_map.py APPLIANCE_LABELS 배열 인덱스(0~21). '
    '22 가전과 1:1, MAIN(ch01) 은 NULL. 모델 출력 인덱스 → appliance_code 번역의 단일 소스.';

COMMIT;
