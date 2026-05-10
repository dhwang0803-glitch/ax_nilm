"""dev10 가구의 시연용 더미 일별 사용량 (`power_daily_historical`) 적재.

기간 : 시연(2026-05-15) - 24개월 ~ 시연 - 50일 = 2024-05-15 ~ 2026-03-25 (~680 일)
규모 : 10 가구 × ~680 일 ≈ 6,800 행

알고리즘 (synthetic_v1)
======================
가구별 base 사용량 (kWh/일) 에 시나리오 절감률·계절성·noise 적용.

    base[h]      = measured_avg[h] × (1 + savings_rate[h])
                   ↑ 실측 31일 평균 (shift 후 power_1min ch01)
                   ↑ "과거 baseline 은 절감 전이라 더 컸다" 가정
    seasonal[m]  = 월별 계절 계수 (겨울 1.20, 여름 1.15, 봄가을 0.90~0.95)
    noise[h, d]  = 1 + N(0, 0.05),  rng seed = sha256(h || d)[:16]
    daily[h, d]  = base[h] × seasonal[m(d)] × noise[h, d]

결정론
------
seed 가 (household_id, day) 의 sha256 → process/실행 무관 동일 값. 재생성·재실행
모두 같은 결과. 시연 시점의 모든 더미 행 재현 가능.

시나리오 분배 (`HOUSEHOLD_SCENARIOS`)
-------------------------------------
baseline 큰 가구 = 큰 절감률 (절대 절감량 큰 가구가 더 많이 절감 가능).
- 5%  : H011 / H015 / H016
- 8%  : H049
- 12% : H017 / H033 / H054
- 15% : H067
- 18% : H039 / H063

실행
----
    set -a && source Database/.env && set +a
    APP_PWD=$(gcloud secrets versions access latest --secret=$SECRET_NAME --project=$PROJECT_ID)
    export DATABASE_URL="postgresql+asyncpg://$APP_USER:$APP_PWD@localhost:$LOCAL_PG_PORT/$DB_NAME"
    # IAP 터널 별도 셸: gcloud compute start-iap-tunnel ... :5436

    # 스모크 (1가구 7일 dry-run + 실제)
    python Database/scripts/load_dummy_historical.py \\
        --households H011 --start-date 2024-05-15 --end-date 2024-05-21 --dry-run
    python Database/scripts/load_dummy_historical.py \\
        --households H011 --start-date 2024-05-15 --end-date 2024-05-21

    # 본 적용 (10가구 × 680일)
    python Database/scripts/load_dummy_historical.py
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from sqlalchemy import BigInteger, Column, Date, Float, MetaData, Table, Text
from sqlalchemy.dialects.postgresql import insert as pg_insert

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from Database.src.db import dispose_engine, session_scope  # noqa: E402

# ─── 설정 ─────────────────────────────────────────────────────────────────────

SOURCE = "synthetic_v1"

# 시연 시점 = 2026-05-15. baseline 24개월 = 2024-05-15. 실측 시작 직전 = 2026-03-25.
DEFAULT_START = date(2024, 5, 15)
DEFAULT_END = date(2026, 3, 25)

# (savings_rate, measured_avg_kwh) — measured_avg 는 shift 후 power_1min 31일 ch01 SUM/1000
# baseline 큰 가구 → 큰 절감률 분배
HOUSEHOLD_SCENARIOS: dict[str, tuple[float, float]] = {
    "H011": (0.05, 10.13),
    "H015": (0.05, 7.24),
    "H016": (0.05, 8.05),
    "H017": (0.12, 13.60),
    "H033": (0.12, 12.52),
    "H054": (0.12, 14.23),
    "H039": (0.18, 14.38),
    "H063": (0.18, 16.65),
    "H049": (0.08, 18.74),
    "H067": (0.15, 21.20),
}

# 월별 계절 계수 (겨울 난방 + 한여름 냉방 ↑, 봄가을 ↓)
SEASONAL: dict[int, float] = {
    1: 1.20, 2: 1.18, 3: 1.05, 4: 0.95, 5: 0.90, 6: 0.95,
    7: 1.10, 8: 1.15, 9: 1.05, 10: 0.95, 11: 1.05, 12: 1.18,
}

NOISE_SIGMA = 0.05  # 일별 5% 표준편차

INSERT_CHUNK = 2000  # PG bind 파라미터 한계 고려

# ─── SQLAlchemy Core Table (ORM 모델 미정의 — raw INSERT 용) ──────────────────

_metadata = MetaData()
power_daily_historical = Table(
    "power_daily_historical",
    _metadata,
    Column("household_id", Text, primary_key=True),
    Column("day", Date, primary_key=True),
    Column("kwh", Float),
    Column("savings_rate", Float),
    Column("source", Text, primary_key=True),
    Column("seed_value", BigInteger),
)


# ─── 결정론 seed ──────────────────────────────────────────────────────────────

def make_seed(household_id: str, day: date) -> int:
    """sha256(household_id || day.isoformat()) 의 상위 16 hex → int.

    Python 의 hash() 는 PYTHONHASHSEED 의존성으로 결정론 X. sha256 으로 치환.
    """
    s = f"{household_id}_{day.isoformat()}".encode("utf-8")
    return int(hashlib.sha256(s).hexdigest()[:16], 16) % (2**63 - 1)


def synth_kwh(household_id: str, day: date) -> tuple[float, float, int]:
    """가구·일별 더미 kWh + 적용된 savings_rate + seed 반환."""
    savings_rate, measured_avg = HOUSEHOLD_SCENARIOS[household_id]
    base = measured_avg * (1.0 + savings_rate)
    seasonal = SEASONAL[day.month]
    seed = make_seed(household_id, day)
    rng = np.random.default_rng(seed)
    noise = 1.0 + rng.normal(0.0, NOISE_SIGMA)
    # noise 음수 보호 (3σ 이내 안전하지만 방어)
    noise = max(noise, 0.5)
    kwh = round(base * seasonal * noise, 3)
    return kwh, savings_rate, seed


def date_range(start: date, end: date):
    """[start, end] 양끝 inclusive."""
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


# ─── 적재 ─────────────────────────────────────────────────────────────────────

async def load(
    households: list[str],
    start: date,
    end: date,
    dry_run: bool,
) -> None:
    rows: list[dict] = []
    for household_id in households:
        if household_id not in HOUSEHOLD_SCENARIOS:
            raise ValueError(f"unknown household: {household_id} (not in HOUSEHOLD_SCENARIOS)")
        for day in date_range(start, end):
            kwh, savings_rate, seed = synth_kwh(household_id, day)
            rows.append({
                "household_id": household_id,
                "day": day,
                "kwh": kwh,
                "savings_rate": savings_rate,
                "source": SOURCE,
                "seed_value": seed,
            })

    days = (end - start).days + 1
    print(f"generated {len(rows)} rows ({len(households)} households × {days} days)")

    if dry_run:
        print("\n[DRY-RUN] sample rows:")
        for r in rows[:5]:
            print(f"  {r}")
        if len(rows) > 5:
            print("  ...")
            for r in rows[-3:]:
                print(f"  {r}")
        unique_rates = sorted({r["savings_rate"] for r in rows})
        rate_count = {sr: sum(1 for r in rows if r["savings_rate"] == sr) for sr in unique_rates}
        kwhs = [r["kwh"] for r in rows]
        print(f"\nsavings_rate distribution: {rate_count}")
        print(f"kwh range: min={min(kwhs):.2f} max={max(kwhs):.2f} mean={sum(kwhs)/len(kwhs):.2f}")
        return

    try:
        inserted = 0
        async with session_scope() as session:
            for i in range(0, len(rows), INSERT_CHUNK):
                chunk = rows[i:i + INSERT_CHUNK]
                stmt = pg_insert(power_daily_historical).values(chunk).on_conflict_do_nothing(
                    index_elements=["household_id", "day", "source"],
                )
                result = await session.execute(stmt)
                inserted += result.rowcount or 0
                print(f"  chunk {i // INSERT_CHUNK + 1}: rowcount={result.rowcount}, cumulative={inserted}")

        print(f"\nDONE: inserted={inserted}, skipped(conflict)={len(rows) - inserted}, total processed={len(rows)}")
    finally:
        # Windows ProactorEventLoop + asyncpg 함정 회피 — 같은 event loop 안에서 dispose
        await dispose_engine()


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument(
        "--households", nargs="+",
        default=list(HOUSEHOLD_SCENARIOS.keys()),
        help="가구 ID 리스트 (default: dev10 10가구)",
    )
    p.add_argument(
        "--start-date", type=lambda s: date.fromisoformat(s),
        default=DEFAULT_START,
        help=f"시작일 (YYYY-MM-DD, default: {DEFAULT_START})",
    )
    p.add_argument(
        "--end-date", type=lambda s: date.fromisoformat(s),
        default=DEFAULT_END,
        help=f"종료일 inclusive (YYYY-MM-DD, default: {DEFAULT_END})",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="DB 적재 없이 분포 sanity 만 출력",
    )
    return p.parse_args()


def main():
    args = parse_args()
    if args.start_date > args.end_date:
        raise SystemExit("--start-date > --end-date")
    print(f"households : {args.households}")
    print(f"period     : {args.start_date} ~ {args.end_date} ({(args.end_date - args.start_date).days + 1} days)")
    print(f"source     : {SOURCE}")
    print()
    asyncio.run(load(args.households, args.start_date, args.end_date, args.dry_run))


if __name__ == "__main__":
    main()
