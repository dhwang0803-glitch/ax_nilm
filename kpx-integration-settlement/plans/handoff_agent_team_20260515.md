# AI Agent 팀 전달 사항 — 2026-05-15

> NILM 모니터링 데모 데이터 + 이상탐지 필터링 변경 건

---

## 1. NILM 메모리 데이터 (GCS 업로드 완료)

### 버킷 경로

```
gs://ax-nilm-data-dhwang0803/memory/long_term/H015.json   (10.9 KB)
gs://ax-nilm-data-dhwang0803/memory/short_term/H015.json  (32.6 KB)
```

### 환경변수 설정

```bash
export NILM_MEMORY_BUCKET=ax-nilm-data-dhwang0803
```

`gcs_memory.py`가 `gs://{NILM_MEMORY_BUCKET}/memory/{long_term|short_term}/{household_id}.json`을 자동 조회합니다.
미설정 시 로컬 `memory/` 디렉토리 폴백.

### household_id

- **`H015`** 사용 (DB `households` 테이블 기준)
- 기존 로컬 파일 `house_015.json`과 다름 — GCS에는 `H015.json`으로 업로드됨
- 로컬 폴백용으로도 `memory/{type}/H015.json` 복사본 있음

### 날짜 shift

- **+911일** 적용 완료 (2023-10-01 → 2026-03-30)
- short_term의 `started_at` 필드만 shift 대상 (long_term은 날짜 필드 없음)
- DB의 power_1min, household_daily_env 등도 동일 shift 적용 상태

### 데이터 내용

| 파일 | 내용 |
|------|------|
| long_term | 22종 가전 × 60모드 baseline (avg_energy_wh, avg_duration_min, sample_count, standby_avg_w) |
| short_term | 144건 이벤트 (엔진 수정 후 — 냉장고 peak 400W 클리핑, 저전력 세그먼트 제거, 공유기 baseline 보정) |

---

## 2. 이상탐지 필터링 변경 (PR #90)

### 변경 파일

- `src/agent/multi_agent/nilm_monitor.py` (+155 lines)
- `src/agent/multi_agent/report_agent.py` (+11 lines)

### 핵심 변경: 가전 4유형 분류

22종 가전을 4유형으로 분류하고 유형별 탐지 규칙 적용:

| 유형 | 가전 | 피크스파이크 | 에너지이상 | 과소비 | 장시간 |
|------|------|:-:|:-:|:-:|:-:|
| A 상시 가동 | 냉장고, 김치냉장고, 공유기 | O | - | - | - |
| B 다단계 사이클 | 세탁기, 식기세척기, 건조기 | O | - | - | - |
| C 단발 사용 | 전자레인지, 포트, 드라이기 등 6종 | O | O | O | O |
| D 장시간 세션 | 에어컨, TV, 컴퓨터 등 10종 | O | O | O | - |

### 코드 사전 필터링 (LLM 호출 전)

- `_prefilter_events`: avg_w < 5W 대기 세그먼트 제거 + 모드명 정규화 ("사용중"→"가동")
- `_annotate_mode_refs`: 저신뢰 baseline 마킹 (sample < 30 or 마이크로 세그먼트) + duration 바닥값 5분 클램프 + 가전 유형(type) 태깅
- `_detect_absolute_anomalies`: peak ≥ 1000W (피크스파이크), 중앙값 × 5 (에너지이상)

### 프롬프트 변경 (report_agent.py)

- `anomaly_flags` 설명에 4가지 타입 명시 (과소비/장시간/피크스파이크/에너지이상)
- `mode_references`에 `type` 필드 + `low_confidence` 설명 추가
- 진단 시 `low_confidence` 모드는 "baseline 신뢰도 낮음" 접미 표기

### 시뮬레이션 결과

H015 데이터 기준 87건 플래그 (오탐률 ~94%) → **0건** (정상 데이터에서 오탐 0%)

---

## 3. E2E 실행 가이드

```bash
# 환경변수
export NILM_MEMORY_BUCKET=ax-nilm-data-dhwang0803
export OPENAI_API_KEY=<your-key>
export DB_PASSWORD=<from-secret-manager>
export DB_HOST=localhost
export DB_PORT=5436
export DB_NAME=ax_nilm
export DB_USER=ax_nilm_team

# IAP 터널 (별도 터미널)
gcloud compute start-iap-tunnel ax-nilm-db-dev 5432 \
    --local-host-port="localhost:5436" \
    --zone=asia-northeast3-a --project=ax-nilm

# 실행
cd kpx-integration-settlement
python -c "from src.agent.multi_agent import run_multi_agent; import json; r = run_multi_agent('H015'); print(json.dumps(r.model_dump(), ensure_ascii=False, indent=2))"
```

---

## 4. 주의사항

- `appliance_mode_references` 테이블은 DB에 없음 — long_term은 GCS/로컬 JSON 전용
- 새 가전 추가 시 `nilm_monitor.py`의 `_APPLIANCE_TYPE` dict에 유형 지정 필수 (미지정 시 C 기본값)
- `AnomalyFlag.flag_type`이 `Literal["과소비", "장시간"]` → `Literal["과소비", "장시간", "피크스파이크", "에너지이상"]`으로 확장됨
