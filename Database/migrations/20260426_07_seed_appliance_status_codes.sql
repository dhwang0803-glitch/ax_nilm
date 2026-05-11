-- ax_nilm — P2 3.2 appliance_status_codes 시드 적재
-- 의존: schemas/004_nilm_inference_tables.sql (appliance_status_codes 빈 테이블)
-- 출처: model_interface.md §5.1 모델 팀 확정안 (2026-04-26 회신본)
--
-- 코드 체계 (모델 팀 확정):
--   * 0-9    범용 + Type 1 단일 ON/OFF (TV, 선풍기, 전기포트, 헤어드라이기 등)
--   * 10-19  Type 2 복합 사이클 (세탁기, 식기세척기, 건조기 등)
--            ※ 라벨 데이터가 ON/OFF 두 가지뿐이므로 wash/rinse/spin 같은 작업명이 아닌
--               유효전력 밴드(저전력 모터 vs 고전력 히터) 기준으로 정의.
--   * 20-29  Type 3 가변/온도 제어 (에어컨, 인덕션, 전기장판 등)
--            ※ 연속 가변 출력을 3개 bucket(Low/Mid/High)으로 백분위 양자화.
--   * 30-39  Type 4 상시 전원/주기성 (냉장고, 김치냉장고, 공유기 등)
--            ※ schemas/004 COMMENT 가이드("20-29 Type4")는 회신 전 임시 가이드였음.
--               본 마이그레이션 끝에서 COMMENT 를 회신 결과로 덮어쓴다.
--   * 40-99  예약
--
-- appliance_code 정책:
--   모든 코드에 NULL. 사유:
--     - 31/32 "냉장고 전용" 은 FRIDGE 와 KIMCHI_FRIDGE 둘 다 해당하므로 단일 FK 로 못 묶음.
--     - 10/11/20/21/22 도 타입 단위 바인딩이라 단일 가전 FK 로 표현 부정확.
--     - 가전-코드 호환성은 application 레이어에서 nilm_type 으로 판정.

BEGIN;

INSERT INTO appliance_status_codes (status_code, label_en, label_ko, appliance_code, description) VALUES
    -- [0~9] 범용 / Type 1 단일 ON/OFF
    ( 0, 'off',           '전원 OFF',     NULL,
      '전원 완전 OFF / 소비량 거의 0. 모든 가전 공통.'),
    ( 1, 'standby',       '대기',         NULL,
      '대기전력 수준 (수 W 이하). 모든 가전 공통.'),
    ( 2, 'active',        '동작',         NULL,
      '일반 동작 — Type 1 가전의 켜짐 구간 또는 단일 상태 가전 일반.'),
    ( 3, 'peak',          '피크',         NULL,
      '피크 구간 / 초기 기동 전류. 짧은 고전력 트랜지언트.'),
    -- [10~19] Type 2 복합 사이클
    (10, 'motor_active',  '모터 동작',    NULL,
      'Type 2 저전력 교번 동작 — 세탁기 세탁/헹굼, 식기세척기 세척 펌프 등. '
      'UI 에서 [기기 + 코드] 결합으로 작업명 추론 (예: 세탁기 + 10 → "세탁/헹굼 중").'),
    (11, 'heater_active', '히터 동작',    NULL,
      'Type 2 고전력 동작 — 세탁기/식세기 온수 가열, 건조기 열풍, 세탁기 탈수 등.'),
    -- [20~29] Type 3 가변/온도 제어 (백분위수 3-bucket 양자화, 추후 k-means 발전 예정)
    (20, 'level_low',     '저전력',       NULL,
      'Type 3 저전력 운전 — 에어컨/인덕션 설정 온도 도달 후 유지 구간.'),
    (21, 'level_mid',     '중전력',       NULL,
      'Type 3 중전력 운전 — 일반 작동 구간.'),
    (22, 'level_high',    '고전력',       NULL,
      'Type 3 고전력 운전 — 초기 급속 냉방/가열 구간.'),
    -- [30~39] Type 4 상시 전원 / 주기성
    (30, 'base_load',     '상시 부하',    NULL,
      'Type 4 상시 전원 유지 / compressor OFF (내부 순환 중). 공유기처럼 항시 켜진 가전 포함.'),
    (31, 'compressor_on', '컴프레서 가동', NULL,
      '냉각 사이클 가동 (냉장고/김치냉장고 전용). 일 100+ 전환 정상 — 이상탐지에서 주기성 변화로 활용.'),
    (32, 'defrost',       '성에 제거',    NULL,
      '성에 제거 — 냉장고/김치냉장고 전용 고전력 히터 가동 구간.');

-- schemas/004 의 COMMENT 가이드를 모델 팀 확정 코드 범위로 갱신.
-- (schemas/ 는 immutable 이므로 본 마이그레이션에서 COMMENT 만 덮어씀)
COMMENT ON TABLE appliance_status_codes IS
    'CNN+TDA NILM 모델의 status_code 의미 정의 마스터. '
    'appliance_code NULL = 범용/타입 단위 상태. '
    'appliance_code 값 있음 = 특정 가전 전용 상태 (현재 시드는 모두 NULL). '
    '코드 범위 (모델 팀 확정 2026-04-26): '
    '0-9 범용+Type1 / 10-19 Type2 복합사이클 / 20-29 Type3 양자화 bucket / 30-39 Type4 주기성 / 40-99 예약.';

COMMIT;
