-- ax_nilm — 코어 관계형 테이블
-- 대상: PostgreSQL 16 + TimescaleDB 2.x
-- 관련 문서: Database/docs/dataset_spec.md, Database/docs/schema_design.md
--
-- 수록: 확장(extensions), 가전 카테고리 마스터, 가구 마스터,
--       PII 분리 테이블, 가구-채널-가전 매핑, 일별 환경 데이터

BEGIN;

-- ─── 확장 ───────────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS btree_gist;   -- activity_intervals EXCLUDE 제약용
-- CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- 선택: DB 레벨 암호화 사용 시

-- ─── 가전 카테고리 마스터 ───────────────────────────────────────────────
-- 22종 가전 + 메인 분전반의 정적 분류
CREATE TABLE appliance_types (
    appliance_code     TEXT PRIMARY KEY,
    name_ko            TEXT NOT NULL,
    name_en            TEXT,
    default_channel    SMALLINT NOT NULL UNIQUE,
    nilm_type          SMALLINT,
    CHECK (default_channel BETWEEN 1 AND 23),
    CHECK (nilm_type IS NULL OR nilm_type BETWEEN 1 AND 4)
);

COMMENT ON COLUMN appliance_types.default_channel IS
    'AI Hub 71685 기본 채널 번호 (ch01 = 1, ... ch23 = 23)';
COMMENT ON COLUMN appliance_types.nilm_type IS
    '1 단일ON/OFF, 2 다중상태, 3 무한상태, 4 영구소비 (메인 분전반은 NULL)';

-- ─── 가구 마스터 ────────────────────────────────────────────────────────
-- 집계·분석에 필요한 분류 정보만 평문 보관.
-- 개인식별·민감정보는 household_pii 로 분리 (아래 참조).
CREATE TABLE households (
    household_id       TEXT PRIMARY KEY,
    house_type         TEXT,
    residential_type   TEXT,
    residential_area   TEXT,
    co_lighting        BOOLEAN,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (household_id ~ '^H[0-9]{3}$')
);

CREATE INDEX idx_households_house_type ON households(house_type);

COMMENT ON COLUMN households.household_id IS
    'AI Hub 가구 ID (H001 ~ H110, 중도탈락 포함 H112까지 예약)';

-- ─── 개인식별정보 분리 테이블 ──────────────────────────────────────────
-- 루트 CLAUDE.md 보안 규칙(AES-256 암호화) 적용 대상.
-- address_enc/members_enc 는 애플리케이션 레이어에서 Fernet(AES-256)으로 암호화한
-- 원본을 BYTEA로 저장. 직접 SELECT 권한은 분석 역할에 부여하지 않음.
CREATE TABLE household_pii (
    household_id       TEXT PRIMARY KEY REFERENCES households(household_id) ON DELETE CASCADE,
    address_enc        BYTEA,
    members_enc        BYTEA,
    income_dual        BOOLEAN,
    utility_facilities TEXT[],
    extra_appliances   TEXT[],
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE household_pii IS
    '개인정보 분리 테이블 — 접근통제/암호화 대상 (CLAUDE.md 보안 규칙 적용)';
COMMENT ON COLUMN household_pii.income_dual IS
    'AI Hub meta.income (이름과 달리 실제 의미는 맞벌이 여부)';
COMMENT ON COLUMN household_pii.extra_appliances IS
    '원본의 앞 공백은 ETL 단계에서 trim 후 저장';

-- ─── 가구별 채널 구성 ──────────────────────────────────────────────────
-- 어떤 가구의 ch## 가 어떤 가전인지. 가구마다 보유 가전이 달라 희소 매트릭스.
CREATE TABLE household_channels (
    household_id       TEXT NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    channel_num        SMALLINT NOT NULL,
    appliance_code     TEXT NOT NULL REFERENCES appliance_types(appliance_code),
    device_name        TEXT,
    brand              TEXT,
    power_category     TEXT,
    power_consumption  NUMERIC(8,2),
    energy_efficiency  SMALLINT,
    PRIMARY KEY (household_id, channel_num),
    CHECK (channel_num BETWEEN 1 AND 23),
    CHECK (power_category IS NULL OR power_category IN ('high','middle','low')),
    CHECK (energy_efficiency IS NULL OR energy_efficiency BETWEEN 1 AND 5)
);

CREATE INDEX idx_household_channels_appliance ON household_channels(appliance_code);

COMMENT ON COLUMN household_channels.power_category IS
    'AI Hub meta.power_category (high/middle/low)';
COMMENT ON COLUMN household_channels.power_consumption IS
    '정격 소비전력 W (AI Hub meta.power_consumption; "unknown" → NULL)';

-- ─── 가구별 일별 환경 데이터 ───────────────────────────────────────────
-- JSON meta 중 날짜별로 변하는 값(날씨·기온·풍속·습도)만 별도 테이블.
-- 원본 'windchill' 필드명은 실제로는 avgWs(평균풍속)이므로 컬럼명을 실의미로 변경.
CREATE TABLE household_daily_env (
    household_id       TEXT NOT NULL REFERENCES households(household_id) ON DELETE CASCADE,
    observed_date      DATE NOT NULL,
    weather_raw        TEXT,
    temperature_c      NUMERIC(5,2),
    wind_speed_ms      NUMERIC(5,2),
    humidity_pct       NUMERIC(5,2),
    PRIMARY KEY (household_id, observed_date)
);

COMMENT ON COLUMN household_daily_env.weather_raw IS
    'AI Hub meta.weather 원본 — "{박무}2150-..." 등 ISCS 코드 문자열 (결측 빈번)';
COMMENT ON COLUMN household_daily_env.wind_speed_ms IS
    'AI Hub meta.windchill (필드명과 달리 실제는 평균풍속 avgWs, 단위 m/s)';

COMMIT;
