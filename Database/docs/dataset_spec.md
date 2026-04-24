# AI Hub 71685 — 데이터셋 명세 (실측 대조)

> 출처: AI Hub 「전기 인프라 지능화를 위한 가전기기 전력 사용량 데이터」 (dataSetSn=71685)
> 기반 문서: 데이터설명서, 활용가이드라인 (`Database/dataset_staging/aihub_71685/docs/`)
> 실측 샘플: `house_001` 1가구의 `ch01`(메인), `ch21`(냉장고) 2023-09-22 하루치
> 검증 스크립트: `Database/scripts/validate_sample.py` → `_validate_report.txt`

## 1. 요약

- **규모**: 110가구 × 31일, 22종 가전 + 메인 분전반 1채널, 총 40,641 파일(CSV=JSON 1:1)
- **샘플링**: 30Hz (하루 2,592,000 포인트/채널)
- **원천 형식**: CSV (11 컬럼, ~200 MB/채널/일)
- **라벨 형식**: JSON (meta 24 필드 + labels.active_inactive 구간 배열)

## 2. 파일 구조 및 명명 규칙

```
01.원천데이터/  house_NNN/ ch## /  H{NNN}_ch{##}_{YYYYMMDD}.csv
02.라벨링데이터/ house_NNN/ ch## /  H{NNN}_ch{##}_{YYYYMMDD}.json
```

- 가구 ID: `H001 ~ H110` (중도탈락 포함 `H112`까지 예약됨)
- 채널: `ch01 ~ ch23` (메인 + 22종)
- 일자: `YYYYMMDD`

## 3. 채널 ↔ 가전 매핑 (ch01~ch23)

| ch | 기기 | NILM Type | ch | 기기 | NILM Type |
|----|------|----|----|------|----|
| 01 | 메인 분전반 | — | 13 | 에어컨 | 3 |
| 02 | TV | 1 | 14 | 전기장판/담요 | 3 |
| 03 | 선풍기 | 1 | 15 | 온수매트 | 3 |
| 04 | 전기포트 | 1 | 16 | 인덕션 | 3 |
| 05 | 전기밥솥 | 2 | 17 | 컴퓨터(데스크탑) | 3 |
| 06 | 세탁기 | 2 | 18 | 전기다리미 | 3 |
| 07 | 헤어드라이기 | 2 | 19 | 공기청정기 | 3 |
| 08 | 진공청소기 | 2 | 20 | 제습기 | 3 |
| 09 | 전자레인지 | 2 | 21 | 냉장고 | 4 |
| 10 | 에어프라이어 | 2 | 22 | 김치냉장고 | 4 |
| 11 | 의류건조기 | 2 | 23 | 무선공유기/셋톱박스 | 4 |
| 12 | 식기세척기 | 2 | | | |

**NILM Type**: 1 단일상태(ON/OFF) · 2 다중상태(Finite-state) · 3 무한상태(Continuously variable) · 4 영구소비(Permanent consumer)

## 4. CSV 원천 데이터 스펙

### 4.1 컬럼 (11 개, 순서 고정)

| # | 컬럼 | 단위 | 실측 범위 (ch01 메인, hh001 20230922) | 비고 |
|---|------|------|---------------------------------------|------|
| 1 | `date_time` | — | `2023-09-22 00:00:00.000` ~ `23:59:59.967` | ISO datetime, 33ms 간격 |
| 2 | `active_power` | W | 0 ~ 3,334.19 (mean 348.77) | 유효전력 |
| 3 | `voltage` | V | 213 ~ 220 (mean 216.22) | 한국 220V |
| 4 | `current` | A | 0 ~ 15.94 (mean 2.38) | |
| 5 | `frequency` | Hz | 60 (상수) | 전력망 주파수 |
| 6 | `apparent_power` | VA | 0 ~ 3,410.09 | |
| 7 | `reactive_power` | var | 0 ~ 1,573.21 | |
| 8 | `power_factor` | 0–1 | 0 ~ 1 (mean 0.654) | |
| 9 | `phase_difference` | deg | 0 ~ 360 | **voltage_phase=0 기준이라 `current_phase`와 값 동일** |
| 10 | `current_phase` | deg | 0 ~ 360 | |
| 11 | `voltage_phase` | deg | **0 (상수)** | 기준 위상 |

### 4.2 실측 무결성 (샘플 2개 파일 기준)

- 행 수: **정확히 2,592,000** (30Hz × 86,400s, 헤더 제외) ✓
- 결측: 모든 컬럼 0건 ✓
- 타임스탬프 중복: 0건 ✓
- 간격: mean 33.333 ms / std 0.471 / min 33 / max 34 (정수 ms 반올림에 의한 지터) ✓
- 50 ms 초과 gap: 0건 ✓

### 4.3 문서 "13종 항목" vs 실측 11 컬럼

설명서에는 13종(장치ID·MAC주소 포함)이지만 CSV는 11컬럼. 누락 2종은 파일 경로(`H001_ch01`)에 내재되어 있음 — 필요 시 파싱 시 컬럼으로 재구성.

## 5. JSON 라벨 데이터 스펙

### 5.1 구조

```json
{
  "meta":   { ... 24 fields ... },
  "labels": {
    "id": "ch01",
    "active_inactive": [ ["start_ts", "end_ts"], ... ]
  }
}
```

### 5.2 meta 필드 (24 개)

| # | 필드 | 문서 정의 | 실측 타입/값 | 갭 |
|---|------|----------|-------------|-----|
| 1 | `filename` | string / 필수 | `"H001_ch01_20230922.csv"` | — |
| 2 | `id` | string / 필수 | `"H001_ch01"` | — |
| 3 | `date` | string / 필수 | `"20230922"` (YYYYMMDD) | 문서 예시는 `"2023-07-31"`(하이픈) |
| 4 | `house_type` | string / 필수 | `"2~3인 가구"` | — |
| 5 | `residential_type` | string / 필수 | `"다세대 주택"` | — |
| 6 | `residential_area` | string / 필수 | `"85m(24평) 미만"` | `m` 표기(㎡ 아님) |
| 7 | `sampling_frequency` | **number** / 필수 | **`"30Hz"` (str)** | 🔴 타입 불일치 |
| 8 | `type` | `"type_1"` (언더스코어) | `"type4"` / `"main power"` | 🔴 표기 불일치 |
| 9 | `name` | string / 필수 | `"메인 분전반"`, `"일반 냉장고"` | — |
| 10 | `power_category` | string / 필수 | `"high"`, `"middle"`, `"low"` | — |
| 11 | `power_consumption` | string / 필수 | `"51.8"` 또는 `"unknown"` | `unknown` 허용 |
| 12 | `unit` | string / 필수 | `"W"` | — |
| 13 | `brand` | string / 필수 | `"LG"` / `"메인 분전반"` | 분전반은 브랜드 없음 |
| 14 | `energy_efficiency` | string / 필수 | `"3"` 또는 `"unknown"` | `unknown` 허용 |
| 15 | `address` | string / 필수 | `"서울 마포구"` | 🔒 **PII** |
| 16 | `utility_facilities` | array / 옵션 | `["헬스장"]` | — |
| 17 | `co-lighting` | boolean / 옵션 | `false` | — |
| 18 | `weather` | string / 필수 | `""` (빈값) 또는 `"{박무}2150-..."` | 결측 흔함 |
| 19 | `temperature` | **number** / 필수 | **`"20.5"` (str)** | 🔴 타입 불일치 (일평균 기온) |
| 20 | `windchill` | **number** / 필수 | `"1.7"` (str) | 🔴 **필드명=체감온도, 실제=평균풍속(avgWs)** |
| 21 | `humidity` | string / 필수 | `"68.4"` (str) | — |
| 22 | `extra_appliances` | array / 옵션 | `["노트북", " 태블릿PC", " 비데"]` | 🔴 앞 공백 혼입 |
| 23 | `members` | array / 옵션 | `["배우자 또는 동거인"]` | 🔒 **PII** |
| 24 | `income` | boolean / 옵션 | `false` | 🔒 **필드명=소득, 실제=맞벌이 여부** |

### 5.3 labels 필드

| 필드 | 타입 | 설명 |
|------|------|------|
| `id` | string | 채널 ID (`"ch01"` ~ `"ch23"`) |
| `active_inactive` | `[[start_ts, end_ts], ...]` | **기기 활성(ON) 구간** 시작·종료 타임스탬프 쌍 |

- `active_inactive`는 의미상 **활성 구간만** 열거 (비활성은 암묵적 여집합)
- 실측: ch01(메인)은 1구간(종일), ch21(냉장고)은 30구간/일 — 컴프레서 사이클 반영

## 6. 문서 ↔ 실측 핵심 갭 (요약)

| # | 이슈 | 영향 |
|---|------|------|
| A | `sampling_frequency` 타입 mismatch (string `"30Hz"`) | 파싱 로직에서 `number` 가정 금지 |
| B | `type` 값 표기 불일치 (`"type_1"` vs `"type4"` vs `"main power"`) | 정규화 테이블 필요 |
| C | `windchill` 필드명 오용 (실제 avgWs 평균풍속) | 스키마에서 `wind_speed_ms`로 개명 |
| D | `income` 필드명 오용 (실제 맞벌이 여부) | 스키마에서 `income_dual`로 개명 |
| E | `temperature`, `humidity` string 저장 | 파싱 시 float 변환 |
| F | `extra_appliances` 배열 원소 앞 공백 | ETL 단계에서 trim |
| G | `phase_difference == current_phase` 항상 동일 | 하나만 저장(정규화) 또는 파생 컬럼 |
| H | `voltage_phase == 0` 상수 | 저장 생략 가능 — 도입 시 `SMALLINT` 또는 제거 검토 |
| I | `weather` 결측 빈번 (`""`) | NULL 허용 |

## 7. 개인정보(PII) / 민감정보

| 필드 | 민감도 | 처리 방침 |
|------|--------|-----------|
| `address` | 🔒 PII | 별도 테이블(`household_pii`) + AES-256 암호화 |
| `members` | 🔒 PII | 별도 테이블 + AES-256 암호화 |
| `income` (맞벌이) | 🔒 sensitive | 별도 테이블, 집계 쿼리 외 직접 노출 금지 |
| `house_type`, `residential_type`, `residential_area` | 🟡 저민감 준식별자 | `households` 본체에 평문 보관 (집계 필요) |

루트 `CLAUDE.md` 보안 규칙(개인정보 AES-256 암호화, 평문 저장 금지)의 **직접 적용 대상**.

## 8. 볼륨 추산

### 8.1 원시 30Hz (DB 비저장, NILM 엔진 입력용)

| 단위 | 행 수 | 원시(CSV) | 설명 |
|------|-------|-----------|------|
| 1 채널/일 | 2.592 M | ~200 MB | 실측 ch01 206MB, ch21 200MB |
| 1 가구/일 (23 채널 최대) | ~59 M | ~4.6 GB | |
| 전체 데이터셋 | ~105 B rows (40,641일 × 2.6M) | ~8 TB | |

**정책**: 30Hz 원시는 DB에 저장하지 않음. NILM 엔진이 로컬 파일에서 읽어
분해·이상탐지 수행 후 폐기. (근거: `schema_design.md §0`)

### 8.2 DB 저장 대상 (이중 보존)

**정책**: 최근 7일만 1분 해상도, 이후는 1일 해상도로 다운샘플 (`schema_design.md §0, §3.5, §3.7`).

| 계층 | 단위 | 행 수 | 예상 용량 |
|------|------|-------|-----------|
| Hot (1분) | 1 채널/일 | 1,440 | ~115 KB |
| Hot (1분) | 1 가구/일 (23채널) | ~33 K | ~2.6 MB |
| Hot (1분) | **7일치 총합 (110가구·23채널)** | ~18 M | **~1.1 GB** |
| Cold (1일) | 1 채널/일 | 1 | ~80 B |
| Cold (1일) | 1 가구/일 (23채널) | 23 | ~1.8 KB |
| Cold (1일) | **24일치 총합 (110가구·23채널)** | ~61 K | **~50 MB** |
| 운영 시점 DB 점유 총합 | — | ~18 M | **~1.2 GB** |

→ DB 점유는 상시 GB 단위 수준. 이상 이벤트 고해상도 스냅샷이 추가되면 별도 재추산.

## 9. 스키마 설계 시사점

1. **30Hz 원시** → DB 미저장 (NILM 엔진 내부 처리 후 폐기)
2. **1분 집계 시계열** → `power_1min` TimescaleDB hypertable (bucket_ts + household_id 공간 분할), avg/min/max + energy_wh
3. **가구·채널·가전 메타** → 관계형 정규화 (`households`, `household_channels`, `appliance_types`) — 1분 행마다 복제하지 않고 조회 시 조인
4. **PII 분리** → `household_pii` 전용 테이블 (AES-256 암호화)
5. **환경 데이터(날씨)** → `household_daily_env` (가구·일자 단위)
6. **라벨(활성 구간)** → `activity_intervals` (초 단위 정밀도 유지, tstzrange EXCLUDE 로 겹침 방지)
7. **NILM 모델 출력** → DB 미저장, AI Hub 라벨과의 평가 비교에만 사용
8. **ETL 주의사항**:
   - 30Hz → 1분 버킷 avg/min/max 집계
   - `energy_wh = Σ(active_power × dt)` 적분
   - 문자열 값 float 변환, 공백 trim, `"unknown"` → NULL, `type` 값 정규화
   - `voltage_phase`(상수 0)·`current_phase`(phase_difference와 동일) 집계 시 drop

구체 DDL은 `Database/schemas/` 참조. 설계 근거는 `Database/docs/schema_design.md` 참조.
