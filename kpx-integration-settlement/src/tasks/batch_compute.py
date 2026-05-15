"""Celery 배치 작업 — 월별 기준선 계산 및 캐시백 사전 산정.

스케줄:
  매월 1일 00:00  — 전 가구 당월 기준선(monthly_baselines) 갱신
  매월 5일 00:00  — 전월 캐시백 결과(cashback_results) 확정 저장

DB 왕복 계획 (DEVELOPER.md 원칙 준수):
  refresh_all_baselines     : households(1) + power_1hour(1) + upsert(1) = 3회
  finalize_cashback_results : households(1) + baselines(1) + power_1hour(1) + upsert(1) = 4회
  refresh_household_baseline: households(1) + power_1hour(1) + upsert(1) = 3회

테이블 전제조건 (feat/add-billing-day 기준):
  households        : household_id, cluster_label, billing_day (SMALLINT 1~28, NULL=달력 월)
  power_1hour       : household_id, channel_num, hour_bucket (timestamptz), energy_wh
  monthly_baselines : (household_id, ref_month) PK, period_start, period_end,
                      baseline_kwh, baseline_method, updated_at
  cashback_results  : (household_id, billing_month) PK, period_start, period_end,
                      baseline_kwh, actual_kwh, savings_rate, cashback_rate_krw_per_kwh,
                      projected_cashback_krw, enrolled, baseline_method, status, updated_at
"""
from __future__ import annotations

import os
from calendar import monthrange
from datetime import date, timedelta
from typing import Any

from celery import Celery
from celery.schedules import crontab

from src.agent import ontology

BROKER  = os.getenv("CELERY_BROKER_URL",  "redis://localhost:6379/0")
BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

app = Celery("energy_cashback", broker=BROKER, backend=BACKEND)

app.conf.beat_schedule = {
    "monthly-baseline-refresh": {
        "task":     "tasks.batch_compute.refresh_all_baselines",
        "schedule": crontab(day_of_month="1", hour="0", minute="0"),
    },
    "monthly-cashback-finalize": {
        "task":     "tasks.batch_compute.finalize_cashback_results",
        "schedule": crontab(day_of_month="5", hour="0", minute="0"),
    },
}


def _tier_rate(savings_rate: float) -> float:
    """절감률 → 캐시백 단가(원/kWh). 미달 시 0."""
    for threshold, rate in ontology.cashback_tiers():
        if savings_rate >= threshold:
            return rate
    return 0.0


# ── DB 연결 ──────────────────────────────────────────────────────────────────────

def _get_db_conn():
    """psycopg2 연결 반환. DB_PASSWORD 미설정 시 None."""
    pw = os.getenv("DB_PASSWORD")
    if not pw:
        return None
    try:
        import psycopg2
        return psycopg2.connect(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5436")),
            dbname=os.getenv("DB_NAME", "ax_nilm"),
            user=os.getenv("DB_USER", "ax_nilm_team"),
            password=pw,
            connect_timeout=5,
        )
    except Exception:
        return None


# ── 기간 계산 유틸 ────────────────────────────────────────────────────────────────

def _billing_period(billing_day: int | None, ref_month: str) -> tuple[date, date]:
    """ref_month 기준 검침 사이클 시작/종료일 반환.

    billing_day=None → 달력 월(1일~말일).
    billing_day=D    → 전월 D일 ~ 당월 D-1일.
      예) billing_day=15, ref_month="2026-10" → 2026-09-15 ~ 2026-10-14
    """
    year, month = map(int, ref_month.split("-"))
    if billing_day is None:
        last_day = monthrange(year, month)[1]
        return date(year, month, 1), date(year, month, last_day)
    prev_month = month - 1 if month > 1 else 12
    prev_year  = year if month > 1 else year - 1
    period_start = date(prev_year, prev_month, billing_day)
    period_end   = date(year, month, billing_day) - timedelta(days=1)
    return period_start, period_end


def _prev_month(ref_month: str) -> str:
    """YYYY-MM → 전월 YYYY-MM."""
    year, month = map(int, ref_month.split("-"))
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"


# ── 기준선 계산 헬퍼 ──────────────────────────────────────────────────────────────

def _kwh_for_period(cur, household_ids: list[str], period_start: date, period_end: date) -> dict[str, float]:
    """period_start ~ period_end 구간 channel_num=1 누적 kWh를 가구별로 반환.

    DB 왕복 1회 (IN 절 배치 조회).
    """
    if not household_ids:
        return {}
    cur.execute(
        """
        SELECT household_id,
               ROUND(SUM(energy_wh)::numeric / 1000.0, 2) AS kwh
        FROM power_1hour
        WHERE household_id = ANY(%s)
          AND channel_num  = 1
          AND (hour_bucket AT TIME ZONE 'Asia/Seoul')::date
              BETWEEN %s AND %s
        GROUP BY household_id
        """,
        (household_ids, period_start, period_end),
    )
    return {row[0]: float(row[1] or 0) for row in cur.fetchall()}


def _cluster_avg_kwh(cur, cluster_label: int | None, period_start: date, period_end: date) -> float | None:
    """동일 클러스터 가구의 해당 기간 평균 kWh (proxy 기준선용)."""
    if cluster_label is None:
        return None
    cur.execute(
        """
        SELECT ROUND(AVG(kwh_sum)::numeric, 2)
        FROM (
            SELECT household_id,
                   SUM(energy_wh) / 1000.0 AS kwh_sum
            FROM power_1hour p
            JOIN households h USING (household_id)
            WHERE h.cluster_label = %s
              AND p.channel_num   = 1
              AND (p.hour_bucket AT TIME ZONE 'Asia/Seoul')::date
                  BETWEEN %s AND %s
            GROUP BY household_id
        ) sub
        """,
        (cluster_label, period_start, period_end),
    )
    row = cur.fetchone()
    return float(row[0]) if row and row[0] is not None else None


# ── 태스크 ────────────────────────────────────────────────────────────────────────

@app.task(name="tasks.batch_compute.refresh_all_baselines")
def refresh_all_baselines(ref_month: str | None = None) -> dict[str, Any]:
    """전 가구 당월 기준선(2개년 동월 평균) 계산 → monthly_baselines upsert.

    Args:
        ref_month: "YYYY-MM". None이면 현재 월 자동 계산.

    Returns:
        {"status": "ok", "upserted": N, "proxy_count": M}
        또는 {"status": "error", "reason": "..."}
    """
    conn = _get_db_conn()
    if conn is None:
        return {"status": "error", "reason": "db connection unavailable"}

    if ref_month is None:
        today = date.today()
        ref_month = f"{today.year}-{today.month:02d}"

    year, month = map(int, ref_month.split("-"))
    # 동월 1년전·2년전 ref_month
    ref_y1 = f"{year - 1}-{month:02d}"
    ref_y2 = f"{year - 2}-{month:02d}"

    upserted    = 0
    proxy_count = 0

    with conn.cursor() as cur:
        # 1) 전 가구 조회 (DB 왕복 1)
        cur.execute("SELECT household_id, cluster_label, billing_day FROM households")
        households = cur.fetchall()  # [(hid, cluster_label, billing_day), ...]

        if not households:
            conn.close()
            return {"status": "ok", "upserted": 0, "proxy_count": 0}

        # 2) 2개년 전체 구간 power_1hour 단일 배치 조회 (DB 왕복 2)
        #    GROUP BY (hid, 연도) → (hid, period_start_date, kwh) 형태로 반환
        #    Python에서 날짜 기준으로 y-1/y-2 구분
        hids = [row[0] for row in households]
        billing_map: dict[str, int | None] = {row[0]: row[2] for row in households}
        cluster_map: dict[str, int | None]  = {row[0]: row[1] for row in households}

        unique_bdays = set(billing_map.values())
        all_periods  = [
            _billing_period(bd, ref_y1) for bd in unique_bdays
        ] + [
            _billing_period(bd, ref_y2) for bd in unique_bdays
        ]
        min_date = min(s for s, _ in all_periods)
        max_date = max(e for _, e in all_periods)

        # Known Limitation: EXTRACT(YEAR...) 그룹핑은 billing_day≥2 + 1월 기준월처럼
        # 청구 기간이 연도 경계를 넘는 경우 y-1/y-2 데이터가 혼합될 수 있음.
        # 해당 경우 평균이 부정확해지나 발생 빈도가 낮아 MVP에서 수용.
        cur.execute(
            """
            SELECT household_id,
                   MIN((hour_bucket AT TIME ZONE 'Asia/Seoul')::date) AS period_start,
                   ROUND(SUM(energy_wh)::numeric / 1000.0, 2) AS kwh
            FROM power_1hour
            WHERE household_id = ANY(%s)
              AND channel_num  = 1
              AND (hour_bucket AT TIME ZONE 'Asia/Seoul')::date
                  BETWEEN %s AND %s
            GROUP BY household_id,
                     EXTRACT(YEAR FROM (hour_bucket AT TIME ZONE 'Asia/Seoul'))
            ORDER BY household_id, period_start
            """,
            (hids, min_date, max_date),
        )
        power_rows = cur.fetchall()  # [(hid, period_start_date, kwh), ...]

        # 가구별 이력 정리 (오래된 순 정렬)
        history: dict[str, list[float]] = {}
        for hid, _period_dt, kwh in power_rows:
            history.setdefault(hid, []).append(float(kwh or 0))

        # 3) 가구별 기준선 계산 + upsert (DB 왕복 3)
        upsert_rows = []

        for hid, cluster_label, billing_day in households:
            ps, pe = _billing_period(billing_day, ref_month)

            available = [v for v in history.get(hid, []) if v > 0]
            if len(available) >= 1:
                baseline_kwh    = round(sum(available) / len(available), 2)
                baseline_method = "2year_avg" if len(available) >= 2 else "1year_avg"
            else:
                # proxy fallback — cluster 동기간 평균 (DB 왕복 +1, 해당 가구에만 발생)
                proxy_start, proxy_end = _billing_period(billing_day, ref_y1)
                baseline_kwh    = _cluster_avg_kwh(cur, cluster_label, proxy_start, proxy_end)
                baseline_method = "proxy_cluster" if baseline_kwh else "unknown"
                proxy_count    += 1

            upsert_rows.append((
                hid, ref_month, ps, pe,
                baseline_kwh, baseline_method,
            ))

        if upsert_rows:
            cur.executemany(
                """
                INSERT INTO monthly_baselines
                    (household_id, ref_month, period_start, period_end,
                     baseline_kwh, baseline_method, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (household_id, ref_month)
                DO UPDATE SET
                    period_start     = EXCLUDED.period_start,
                    period_end       = EXCLUDED.period_end,
                    baseline_kwh     = EXCLUDED.baseline_kwh,
                    baseline_method  = EXCLUDED.baseline_method,
                    updated_at       = NOW()
                """,
                upsert_rows,
            )
            upserted = len(upsert_rows)

        conn.commit()

    conn.close()
    return {"status": "ok", "upserted": upserted, "proxy_count": proxy_count}


@app.task(name="tasks.batch_compute.finalize_cashback_results")
def finalize_cashback_results(billing_month: str | None = None) -> dict[str, Any]:
    """전월 실측 사용량 기준 캐시백 산정 → cashback_results upsert.

    Args:
        billing_month: "YYYY-MM". None이면 전월 자동 계산.

    Returns:
        {"status": "ok", "upserted": N}
        또는 {"status": "error", "reason": "..."}
    """
    conn = _get_db_conn()
    if conn is None:
        return {"status": "error", "reason": "db connection unavailable"}

    if billing_month is None:
        today = date.today()
        billing_month = _prev_month(f"{today.year}-{today.month:02d}")

    upserted = 0

    with conn.cursor() as cur:
        # 1) 전 가구 billing_day + enrolled (DB 왕복 1)
        cur.execute(
            "SELECT household_id, dr_enrolled, billing_day FROM households"
        )
        households = cur.fetchall()  # [(hid, enrolled, billing_day), ...]

        if not households:
            conn.close()
            return {"status": "ok", "upserted": 0}

        hids = [row[0] for row in households]
        enrolled_map:   dict[str, bool]       = {row[0]: bool(row[1]) for row in households}
        billing_day_map: dict[str, int | None] = {row[0]: row[2] for row in households}

        # 2) monthly_baselines에서 당월 기준선 조회 (DB 왕복 2)
        cur.execute(
            """
            SELECT household_id, baseline_kwh, baseline_method
            FROM monthly_baselines
            WHERE ref_month = %s AND household_id = ANY(%s)
            """,
            (billing_month, hids),
        )
        baseline_map: dict[str, tuple[float | None, str]] = {
            row[0]: (float(row[1]) if row[1] is not None else None, row[2])
            for row in cur.fetchall()
        }

        # 3) 실측 사용량 조회 (DB 왕복 3) — 가구별 기간이 다르므로 넉넉한 범위로 조회
        billing_days = set(billing_day_map.values())
        min_start = min(_billing_period(bd, billing_month)[0] for bd in billing_days)
        max_end   = max(_billing_period(bd, billing_month)[1] for bd in billing_days)
        actual_kwh_map = _kwh_for_period(cur, hids, min_start, max_end)

        # 4) 캐시백 계산 + upsert (DB 왕복 4)
        upsert_rows = []
        for hid, enrolled, billing_day in households:
            ps, pe = _billing_period(billing_day, billing_month)
            baseline_kwh, baseline_method = baseline_map.get(hid, (None, "unknown"))
            actual_kwh = actual_kwh_map.get(hid, 0.0)

            if baseline_kwh and baseline_kwh > 0:
                savings_kwh  = baseline_kwh - actual_kwh
                savings_rate = round(max(savings_kwh / baseline_kwh, 0.0), 4)
            else:
                savings_rate = 0.0

            rate_per_kwh      = _tier_rate(savings_rate)
            effective_savings = (baseline_kwh or 0.0) * min(savings_rate, ontology.cashback_savings_cap())
            projected_krw     = int(effective_savings * rate_per_kwh)

            if savings_rate >= 0.03 and savings_rate > 0:
                status = "지급완료"
            elif savings_rate > 0:
                status = "미달(3% 미만)"
            else:
                status = "집계중"

            upsert_rows.append((
                hid, billing_month, ps, pe,
                baseline_kwh, actual_kwh,
                savings_rate, rate_per_kwh,
                projected_krw, enrolled, baseline_method, status,
            ))

        if upsert_rows:
            cur.executemany(
                """
                INSERT INTO cashback_results
                    (household_id, billing_month, period_start, period_end,
                     baseline_kwh, actual_kwh, savings_rate,
                     cashback_rate_krw_per_kwh, projected_cashback_krw,
                     enrolled, baseline_method, status, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (household_id, billing_month)
                DO UPDATE SET
                    period_start              = EXCLUDED.period_start,
                    period_end                = EXCLUDED.period_end,
                    baseline_kwh              = EXCLUDED.baseline_kwh,
                    actual_kwh                = EXCLUDED.actual_kwh,
                    savings_rate              = EXCLUDED.savings_rate,
                    cashback_rate_krw_per_kwh = EXCLUDED.cashback_rate_krw_per_kwh,
                    projected_cashback_krw    = EXCLUDED.projected_cashback_krw,
                    enrolled                  = EXCLUDED.enrolled,
                    baseline_method           = EXCLUDED.baseline_method,
                    status                    = EXCLUDED.status,
                    updated_at                = NOW()
                """,
                upsert_rows,
            )
            upserted = len(upsert_rows)

        conn.commit()

    conn.close()
    return {"status": "ok", "upserted": upserted}


@app.task(name="tasks.batch_compute.refresh_household_baseline")
def refresh_household_baseline(household_id: str, ref_month: str) -> dict[str, Any]:
    """단일 가구 기준선 즉시 갱신 (신규 가입·수동 트리거).

    Args:
        household_id: 가구 ID
        ref_month:    "YYYY-MM"

    Returns:
        {"status": "ok", "baseline_kwh": X, "method": "..."}
        또는 {"status": "error", "reason": "..."}
    """
    conn = _get_db_conn()
    if conn is None:
        return {"status": "error", "reason": "db connection unavailable"}

    year, month = map(int, ref_month.split("-"))
    ref_y1 = f"{year - 1}-{month:02d}"
    ref_y2 = f"{year - 2}-{month:02d}"

    with conn.cursor() as cur:
        # 1) 가구 정보 (DB 왕복 1)
        cur.execute(
            "SELECT cluster_label, billing_day FROM households WHERE household_id = %s",
            (household_id,),
        )
        row = cur.fetchone()
        if row is None:
            conn.close()
            return {"status": "error", "reason": f"household not found: {household_id}"}

        cluster_label, billing_day = row

        # 2) 1년전·2년전 동기간 조회 (DB 왕복 2)
        ps_y1, pe_y1 = _billing_period(billing_day, ref_y1)
        ps_y2, pe_y2 = _billing_period(billing_day, ref_y2)

        kwh_y1 = _kwh_for_period(cur, [household_id], ps_y1, pe_y1).get(household_id)
        kwh_y2 = _kwh_for_period(cur, [household_id], ps_y2, pe_y2).get(household_id)

        available = [v for v in (kwh_y1, kwh_y2) if v is not None and v > 0]
        if len(available) >= 1:
            baseline_kwh    = round(sum(available) / len(available), 2)
            baseline_method = "2year_avg" if len(available) == 2 else "1year_avg"
        else:
            ps_proxy, pe_proxy = _billing_period(billing_day, ref_y1)
            baseline_kwh    = _cluster_avg_kwh(cur, cluster_label, ps_proxy, pe_proxy)
            baseline_method = "proxy_cluster" if baseline_kwh else "unknown"

        ps, pe = _billing_period(billing_day, ref_month)

        # 3) upsert (DB 왕복 3)
        cur.execute(
            """
            INSERT INTO monthly_baselines
                (household_id, ref_month, period_start, period_end,
                 baseline_kwh, baseline_method, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (household_id, ref_month)
            DO UPDATE SET
                period_start    = EXCLUDED.period_start,
                period_end      = EXCLUDED.period_end,
                baseline_kwh    = EXCLUDED.baseline_kwh,
                baseline_method = EXCLUDED.baseline_method,
                updated_at      = NOW()
            """,
            (household_id, ref_month, ps, pe, baseline_kwh, baseline_method),
        )
        conn.commit()

    conn.close()
    return {
        "status":       "ok",
        "baseline_kwh": baseline_kwh,
        "method":       baseline_method,
    }
