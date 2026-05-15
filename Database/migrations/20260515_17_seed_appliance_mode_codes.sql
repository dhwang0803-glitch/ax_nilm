-- ax_nilm — 가전별 세부 모드 코드 시드
-- 의존: 20260426_07_seed_appliance_status_codes.sql (기존 0-32 코드)
--
-- 목적:
--   상태 모니터링 모델이 출력하는 가전별 세부 모드를
--   appliance_status_codes 에 40+ 범위로 등록.
--   데모 long_term/short_term JSON 의 mode 필드와 1:1 대응.
--
-- 코드 범위: 40-99 (기존 가이드의 "예약" 구간 활용)
--   40-44: 에어컨 (AC)
--   45-47: 김치냉장고 (KIMCHI_FRIDGE)
--   48-49: 전기밥솥 (RICE_COOKER)
--   50-51: 전기장판/담요 (ELEC_BLANKET)
--   52-53: 제습기 (DEHUMIDIFIER)
--   54-56: 세탁기 (WASHER)
--   57-58: 일반 냉장고 (FRIDGE)
--   59-61: 식기세척기 (DISHWASHER)
--   62-62: 공기청정기 (AIR_PURIFIER)
--   63-66: 에어프라이어 (AIR_FRYER)
--   67-70: 의류건조기 (DRYER)
--   71-75: 전기다리미 (IRON)
--   76-81: 헤어드라이기 (HAIR_DRYER)
--   82-82: 선풍기 (FAN)
--   83-85: 전자레인지 (MICROWAVE)
--   86-87: TV (TV)
--   88-90: 온수매트 (HOT_MAT)
--   91-94: 전기포트 (KETTLE)
--   95-96: 진공청소기 (VACUUM)
--   97-97: 컴퓨터 (PC)
--   98-101: 인덕션 (INDUCTION)
--   102-102: 무선공유기 (ROUTER)

BEGIN;

INSERT INTO appliance_status_codes (status_code, label_en, label_ko, appliance_code, description) VALUES
    -- 에어컨 (AC, nilm_type=3)
    (40, 'ac_fan',             '송풍',       'AC',            '에어컨 송풍 모드 — 저부하 팬 운전'),
    (41, 'ac_cooling',         '냉방',       'AC',            '에어컨 냉방 모드 — 압축기 가동 고부하'),
    -- 42-44: 예약 (난방·제습·자동 등 추가 예정)
    -- 김치냉장고 (KIMCHI_FRIDGE, nilm_type=4)
    (45, 'kimchi_fan',         '팬',         'KIMCHI_FRIDGE', '김치냉장고 팬 동작'),
    (46, 'kimchi_intermit',    '단속냉각',   'KIMCHI_FRIDGE', '김치냉장고 단속냉각 — 간헐적 압축기 on/off'),
    (47, 'kimchi_continuous',  '연속냉각',   'KIMCHI_FRIDGE', '김치냉장고 연속냉각 — 고부하 지속 냉각'),
    -- 전기밥솥 (RICE_COOKER, nilm_type=2)
    (48, 'rice_warm',          '보온',       'RICE_COOKER',   '전기밥솥 보온 모드'),
    (49, 'rice_cook',          '취사',       'RICE_COOKER',   '전기밥솥 취사 모드'),
    -- 전기장판/담요 (ELEC_BLANKET, nilm_type=3)
    (50, 'blanket_low',        '약',         'ELEC_BLANKET',  '전기장판 저온 모드'),
    (51, 'blanket_high',       '강',         'ELEC_BLANKET',  '전기장판 고온 모드'),
    -- 제습기 (DEHUMIDIFIER, nilm_type=3)
    (52, 'dehumid_fan',        '송풍',       'DEHUMIDIFIER',  '제습기 송풍 모드'),
    (53, 'dehumid_dehumid',    '제습',       'DEHUMIDIFIER',  '제습기 제습 모드 — 압축기 가동'),
    -- 세탁기 (WASHER, nilm_type=2)
    (54, 'wash_fill',          '급수',       'WASHER',        '세탁기 급수'),
    (55, 'wash_agitate',       '교반',       'WASHER',        '세탁기 교반 — 드럼 회전 세탁'),
    (56, 'wash_rinse',         '헹굼',       'WASHER',        '세탁기 헹굼'),
    -- 일반 냉장고 (FRIDGE, nilm_type=4)
    (57, 'fridge_cool',        '냉각',       'FRIDGE',        '냉장고 냉각 — 압축기 안정 가동'),
    (58, 'fridge_intermit',    '단속냉각',   'FRIDGE',        '냉장고 단속냉각 — 간헐적 압축기 on/off'),
    -- 식기세척기 (DISHWASHER, nilm_type=2)
    (59, 'dish_prerinse',      '예비헹굼',   'DISHWASHER',    '식기세척기 예비헹굼'),
    (60, 'dish_wash',          '세척',       'DISHWASHER',    '식기세척기 본세척'),
    (61, 'dish_heatdry',       '열풍건조',   'DISHWASHER',    '식기세척기 열풍건조'),
    -- 공기청정기 (AIR_PURIFIER, nilm_type=3)
    (62, 'purifier_run',       '작동',       'AIR_PURIFIER',  '공기청정기 작동'),
    -- 에어프라이어 (AIR_FRYER, nilm_type=2)
    (63, 'airfry_standby',     '대기',       'AIR_FRYER',     '에어프라이어 대기'),
    (64, 'airfry_low',         '저온',       'AIR_FRYER',     '에어프라이어 저온 조리'),
    (65, 'airfry_mid',         '중온',       'AIR_FRYER',     '에어프라이어 중온 조리'),
    (66, 'airfry_high',        '고온',       'AIR_FRYER',     '에어프라이어 고온 조리'),
    -- 의류건조기 (DRYER, nilm_type=2)
    (67, 'dryer_standby',      '대기',       'DRYER',         '의류건조기 대기'),
    (68, 'dryer_drum',         '드럼회전',   'DRYER',         '의류건조기 드럼회전'),
    (69, 'dryer_mid',          '중온건조',   'DRYER',         '의류건조기 중온건조'),
    (70, 'dryer_high',         '고온건조',   'DRYER',         '의류건조기 고온건조'),
    -- 전기다리미 (IRON, nilm_type=3)
    (71, 'iron_standby',       '대기',       'IRON',          '전기다리미 대기'),
    (72, 'iron_preheat',       '예열',       'IRON',          '전기다리미 예열'),
    (73, 'iron_low',           '저온',       'IRON',          '전기다리미 저온'),
    (74, 'iron_mid',           '중온',       'IRON',          '전기다리미 중온'),
    (75, 'iron_high',          '고온',       'IRON',          '전기다리미 고온'),
    -- 헤어드라이기 (HAIR_DRYER, nilm_type=2)
    (76, 'hair_cool_low',      '냉풍약',     'HAIR_DRYER',    '헤어드라이기 냉풍약'),
    (77, 'hair_cool_high',     '냉풍강',     'HAIR_DRYER',    '헤어드라이기 냉풍강'),
    (78, 'hair_warm_low',      '온풍약',     'HAIR_DRYER',    '헤어드라이기 온풍약'),
    (79, 'hair_warm_high',     '온풍강',     'HAIR_DRYER',    '헤어드라이기 온풍강'),
    (80, 'hair_hot_low',       '열풍약',     'HAIR_DRYER',    '헤어드라이기 열풍약'),
    (81, 'hair_hot_high',      '열풍강',     'HAIR_DRYER',    '헤어드라이기 열풍강'),
    -- 선풍기 (FAN, nilm_type=1)
    (82, 'fan_run',            '작동',       'FAN',           '선풍기 작동'),
    -- 전자레인지 (MICROWAVE, nilm_type=2)
    (83, 'micro_standby',      '대기',       'MICROWAVE',     '전자레인지 대기'),
    (84, 'micro_low',          '저출력',     'MICROWAVE',     '전자레인지 저출력'),
    (85, 'micro_high',         '고출력',     'MICROWAVE',     '전자레인지 고출력'),
    -- TV (TV, nilm_type=1)
    (86, 'tv_standby',         '대기',       'TV',            'TV 대기'),
    (87, 'tv_watch',           '시청',       'TV',            'TV 시청'),
    -- 온수매트 (HOT_MAT, nilm_type=3)
    (88, 'hotmat_low',         '저온',       'HOT_MAT',       '온수매트 저온'),
    (89, 'hotmat_mid',         '중온',       'HOT_MAT',       '온수매트 중온'),
    (90, 'hotmat_high',        '고온',       'HOT_MAT',       '온수매트 고온'),
    -- 전기포트 (KETTLE, nilm_type=1)
    (91, 'kettle_warm',        '보온',       'KETTLE',        '전기포트 보온'),
    (92, 'kettle_low',         '약끓임',     'KETTLE',        '전기포트 약끓임'),
    (93, 'kettle_mid',         '중끓임',     'KETTLE',        '전기포트 중끓임'),
    (94, 'kettle_high',        '강끓임',     'KETTLE',        '전기포트 강끓임'),
    -- 진공청소기 (VACUUM, nilm_type=2)
    (95, 'vacuum_low',         '약',         'VACUUM',        '진공청소기 약 모드'),
    (96, 'vacuum_high',        '강',         'VACUUM',        '진공청소기 강 모드'),
    -- 컴퓨터 (PC, nilm_type=3)
    (97, 'pc_run',             '가동',       'PC',            '컴퓨터 사용중'),
    -- 인덕션 (INDUCTION, nilm_type=3)
    (98, 'induction_standby',  '대기',       'INDUCTION',     '인덕션 대기'),
    (99, 'induction_low',      '약불',       'INDUCTION',     '인덕션 약불'),
   (100, 'induction_mid',      '중불',       'INDUCTION',     '인덕션 중불'),
   (101, 'induction_high',     '강불',       'INDUCTION',     '인덕션 강불'),
    -- 무선공유기/셋톱박스 (ROUTER, nilm_type=4)
   (102, 'router_run',         '작동',       'ROUTER',        '무선공유기 작동');

COMMIT;
