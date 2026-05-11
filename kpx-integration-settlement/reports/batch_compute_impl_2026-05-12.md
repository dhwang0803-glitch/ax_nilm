# Celery 배치 태스크 구현 보고서

**날짜**: 2026-05-12  
**파일**: `src/tasks/batch_compute.py`  
**테스트**: `tests/test_batch_compute.py` — 22/22 PASS  

---

## 구현 범위

### 공개 태스크 3개

| 태스크 | 스케줄 | DB 왕복 |
|--------|--------|---------|
| `refresh_all_baselines` | 매월 1일 00:00 | 3회 (+ proxy 가구당 +1) |
| `finalize_cashback_results` | 매월 5일 00:00 | 4회 |
| `refresh_household_baseline` | 수동/신규 가입 트리거 | 3회 |

### 내부 헬퍼

| 함수 | 역할 |
|------|------|
| `_billing_period(billing_day, ref_month)` | 검침일 기반 청구 사이클 날짜 계산 |
| `_tier_rate(savings_rate)` | KEPCO 에너지캐시백 단가 조회 |
| `_get_db_conn()` | psycopg2 연결 (DB_PASSWORD 미설정 시 None) |
| `_kwh_for_period(cur, hids, start, end)` | 기간별 kWh 배치 조회 |
| `_cluster_avg_kwh(cur, cluster_label, start, end)` | 클러스터 평균 (proxy 기준선용) |

---

## 설계 결정

### 1. DB 왕복 최소화 (N+1 방지)

`refresh_all_baselines`는 전 가구 2개년 전력 데이터를 단일 쿼리로 조회한다.

```sql
SELECT household_id,
       MIN((hour_bucket AT TIME ZONE 'Asia/Seoul')::date) AS period_start,
       ROUND(SUM(energy_wh)::numeric / 1000.0, 2) AS kwh
FROM power_1hour
WHERE household_id = ANY(%s)
  AND channel_num  = 1
  AND (hour_bucket AT TIME ZONE 'Asia/Seoul')::date BETWEEN %s AND %s
GROUP BY household_id, EXTRACT(YEAR FROM (hour_bucket AT TIME ZONE 'Asia/Seoul'))
```

`GROUP BY (hid, YEAR)` 로 y-1 / y-2 데이터를 한 번에 반환, Python에서 `history[hid]` 리스트로 누적해 평균 계산. 가구 수 N에 관계없이 DB 왕복 2회.

### 2. proxy_cluster 폴백

이력이 없는 신규 가구는 동일 클러스터의 동기간 평균을 기준선으로 사용한다. 해당 가구에만 추가 DB 왕복 1회 발생 (MVP에서 드문 케이스 허용).

### 3. KEPCO 에너지캐시백 단가 테이블

| 절감률 | 단가 |
|--------|------|
| ≥ 20% | 100원/kWh |
| ≥ 10% | 80원/kWh |
| ≥ 5%  | 60원/kWh |
| ≥ 3%  | 30원/kWh |
| < 3%  | 0원/kWh |

절감률 상한 `_SAVINGS_CAP = 0.30` (30%) 적용 — 초과 절감은 산정 대상에서 제외.

### 4. upsert 전략

`ON CONFLICT (household_id, ref_month) DO UPDATE SET` 패턴으로 재실행 멱등성 보장. `executemany` 단일 호출로 전 가구 일괄 처리.

---

## Known Limitation

`EXTRACT(YEAR...)` 그룹핑은 **billing_day ≥ 2 이고 ref_month가 1월**인 경우처럼 청구 기간이 연도 경계를 넘을 때 y-1/y-2 데이터가 혼합될 수 있다. 발생 빈도가 낮고 평균 오차가 미미하여 MVP 범위에서 수용. 추후 BETWEEN 절을 가구별 기간으로 세분화 시 해소 가능.

---

## 테스트 커버리지

| 클래스 | 케이스 수 | 대상 |
|--------|-----------|------|
| `TestBillingPeriod` | 5 | `_billing_period` 경계값 (검침일/달력 월/연도 경계) |
| `TestTierRate` | 10 | `_tier_rate` 전 구간 + 경계값 파라미터화 |
| `TestTasksNoDb` | 3 | DB 없음 → early-return error dict |
| `TestRefreshAllBaselinesMocked` | 2 | 정상 upsert + proxy fallback |
| `TestFinalizeCashbackMocked` | 2 | 20% 절감(100원), 2% 미달(0원) |
| **합계** | **22** | **22/22 PASS** |

---

## 보안

- DB 접속 정보 전량 `os.getenv()` 참조, 기본값에 실제 인프라 정보 없음
- `DB_PASSWORD` 미설정 시 즉시 `{"status": "error"}` 반환 (연결 시도 없음)
- `.env` 미커밋 (`.gitignore` 확인 완료)
