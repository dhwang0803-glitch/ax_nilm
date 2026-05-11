-- ax_nilm — 가전 카테고리 시드
-- AI Hub 71685 채널 매핑 (ch01 메인 + ch02~ch23 22종 가전)
-- 전제: 001_core_tables.sql 선행 적용

BEGIN;

INSERT INTO appliance_types (appliance_code, name_ko, name_en, default_channel, nilm_type) VALUES
    ('MAIN',          '메인 분전반',           'Main Panel',            1,  NULL),
    ('TV',            'TV',                    'Television',            2,  1),
    ('FAN',           '선풍기',                 'Electric Fan',          3,  1),
    ('KETTLE',        '전기포트',               'Electric Kettle',       4,  1),
    ('RICE_COOKER',   '전기밥솥',               'Rice Cooker',           5,  2),
    ('WASHER',        '세탁기',                 'Washing Machine',       6,  2),
    ('HAIR_DRYER',    '헤어드라이기',           'Hair Dryer',            7,  2),
    ('VACUUM',        '진공청소기',             'Vacuum Cleaner',        8,  2),
    ('MICROWAVE',     '전자레인지',             'Microwave',             9,  2),
    ('AIR_FRYER',     '에어프라이어',           'Air Fryer',            10,  2),
    ('DRYER',         '의류건조기',             'Clothes Dryer',        11,  2),
    ('DISHWASHER',    '식기세척기',             'Dishwasher',           12,  2),
    ('AC',            '에어컨',                 'Air Conditioner',      13,  3),
    ('ELEC_BLANKET',  '전기장판/담요',          'Electric Blanket',     14,  3),
    ('HOT_MAT',       '온수매트',               'Hot Water Mat',        15,  3),
    ('INDUCTION',     '인덕션',                 'Induction Cooktop',    16,  3),
    ('PC',            '컴퓨터(데스크탑)',       'Desktop PC',           17,  3),
    ('IRON',          '전기다리미',             'Electric Iron',        18,  3),
    ('AIR_PURIFIER',  '공기청정기',             'Air Purifier',         19,  3),
    ('DEHUMIDIFIER',  '제습기',                 'Dehumidifier',         20,  3),
    ('FRIDGE',        '냉장고',                 'Refrigerator',         21,  4),
    ('KIMCHI_FRIDGE', '김치냉장고',             'Kimchi Refrigerator',  22,  4),
    ('ROUTER',        '무선공유기/셋톱박스',     'Router/Set-top Box',   23,  4);

COMMIT;
