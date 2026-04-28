"""GCS dev10 raw parquet → power_1min 1분 집계 적재.

입력 : ``gs://ax-nilm-data-dhwang0803/nilm/training_dev10/``
       (hive: ``household_id=house_XXX/channel=chXX/date=YYYYMMDD/part-*.parquet``)
출력 : ``power_1min`` hypertable
변환 : 30Hz raw → 1분 floor groupby → avg/min/max + ``energy_wh = Σ(P_W × dt)`` + sample_count
재실행 안전: ON CONFLICT DO NOTHING. 시간대는 KST naive → UTC 로 변환 후 적재.

Usage:
    # 사전 (둘 다 필요):
    #   1) IAP 터널 + DATABASE_URL=postgresql+asyncpg://...
    #   2) gcloud auth application-default login (pyarrow GcsFileSystem 용)

    # 스모크 (1가구 1채널 1일)
    python Database/scripts/load_dev10_power.py \
        --households H011 --channels 1 --dates 20231004 --dry-run
    python Database/scripts/load_dev10_power.py \
        --households H011 --channels 1 --dates 20231004

    # 전체 (~7.5M row, 1~수시간)
    python Database/scripts/load_dev10_power.py
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path

# Database/ 부모 디렉토리를 sys.path 에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import gcsfs  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402
from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from Database.src.db import dispose_engine, session_scope  # noqa: E402
from Database.src.models.power import PowerMinute  # noqa: E402

GCS_BUCKET = "ax-nilm-data-dhwang0803"
GCS_PREFIX = "nilm/training_dev10"
KST = "Asia/Seoul"
SAMPLE_HZ = 30
SECONDS_PER_HOUR = 3600
# Wh = Σ(W) × dt[s] / 3600 → sum / (30 × 3600) = sum / 108000
WH_DIVISOR = SAMPLE_HZ * SECONDS_PER_HOUR  # 108000
INSERT_CHUNK = 4000  # PG bind 파라미터 65535 한계 고려 (행당 ~17 컬럼)

# parquet raw 컬럼 → power_1min `_avg` 컬럼 (mean 집계)
AVG_COLS: list[tuple[str, str]] = [
    ("voltage", "voltage_avg"),
    ("current", "current_avg"),
    ("frequency", "frequency_avg"),
    ("apparent_power", "apparent_power_avg"),
    ("reactive_power", "reactive_power_avg"),
    ("power_factor", "power_factor_avg"),
    ("phase_difference", "phase_difference_avg"),
]


def hid_db_from_partition(raw: str) -> str | None:
    # "house_011" → "H011"  (DB CHECK ^H[0-9]{3}$)
    m = re.fullmatch(r"house_(\d{3})", raw)
    return f"H{m.group(1)}" if m else None


def _ls_dirs(gcs_fs: gcsfs.GCSFileSystem, path: str) -> list[str]:
    """gcsfs ls(detail=True) → 정렬된 directory 경로 list."""
    return sorted(
        e["name"] for e in gcs_fs.ls(path, detail=True) if e["type"] == "directory"
    )


def _ls_parquets(gcs_fs: gcsfs.GCSFileSystem, path: str) -> list[str]:
    return sorted(
        e["name"]
        for e in gcs_fs.ls(path, detail=True)
        if e["type"] == "file" and e["name"].endswith(".parquet")
    )


def list_partitions(
    gcs_fs: gcsfs.GCSFileSystem,
    bucket: str,
    prefix: str,
    limit_houses: int | None,
    hid_filter: set[str],
    ch_filter: set[int],
    date_filter: set[str],
) -> list[tuple[str, int, str, str]]:
    """디렉토리 walk 로 ``(hid_db, ch_num, date_str, gcs_uri)`` 산출."""
    root = f"{bucket}/{prefix}"
    out: list[tuple[str, int, str, str]] = []
    seen_houses: set[str] = set()

    for hpath in _ls_dirs(gcs_fs, root):
        raw_h = hpath.rsplit("/", 1)[-1].split("=", 1)[-1]
        hid_db = hid_db_from_partition(raw_h)
        if hid_db is None:
            continue
        if hid_filter and hid_db not in hid_filter:
            continue
        if limit_houses and hid_db not in seen_houses and len(seen_houses) >= limit_houses:
            continue
        seen_houses.add(hid_db)

        for cpath in _ls_dirs(gcs_fs, hpath):
            raw_c = cpath.rsplit("/", 1)[-1].split("=", 1)[-1]
            if not raw_c.startswith("ch") or not raw_c[2:].isdigit():
                continue
            ch_num = int(raw_c[2:])
            if ch_filter and ch_num not in ch_filter:
                continue

            for dpath in _ls_dirs(gcs_fs, cpath):
                raw_d = dpath.rsplit("/", 1)[-1].split("=", 1)[-1]
                if not re.fullmatch(r"\d{8}", raw_d):
                    continue
                if date_filter and raw_d not in date_filter:
                    continue

                for fpath in _ls_parquets(gcs_fs, dpath):
                    out.append((hid_db, ch_num, raw_d, fpath))
    return out


def aggregate_partition(
    table, hid_db: str, ch_num: int
) -> list[dict]:
    """pyarrow Table → 1분 버킷 dict list."""
    df = table.to_pandas()
    if df.empty or "date_time" not in df.columns:
        return []

    ts = pd.to_datetime(df["date_time"])
    # AI Hub 71685 raw 는 KST naive timestamp → UTC 변환 후 적재
    if ts.dt.tz is None:
        ts = ts.dt.tz_localize(KST)
    df = df.assign(_bucket=ts.dt.floor("1min").dt.tz_convert("UTC"))

    rows: list[dict] = []
    for bucket_ts, sub in df.groupby("_bucket", sort=True):
        sample_count = int(len(sub))
        # CHECK 위반 방어 (이론상 1800 ≤; 라우저 클럭 jitter 로 1801 가능성)
        if sample_count > 1800:
            sample_count = 1800

        ap = sub.get("active_power")
        if ap is not None:
            ap = ap.dropna()
        if ap is None or ap.empty:
            ap_avg = ap_min = ap_max = None
            energy_wh = None
        else:
            ap_sum = float(ap.sum())
            ap_avg = float(ap.mean())
            ap_min = float(ap.min())
            ap_max = float(ap.max())
            energy_wh = ap_sum / WH_DIVISOR  # Wh

        row: dict = {
            "household_id": hid_db,
            "channel_num": ch_num,
            "bucket_ts": bucket_ts.to_pydatetime(),
            "active_power_avg": ap_avg,
            "active_power_min": ap_min,
            "active_power_max": ap_max,
            "energy_wh": energy_wh,
            "sample_count": sample_count,
        }
        for raw_col, db_col in AVG_COLS:
            vals = sub.get(raw_col)
            if vals is None:
                row[db_col] = None
                continue
            vals = vals.dropna()
            row[db_col] = float(vals.mean()) if not vals.empty else None

        # power_factor CHECK 0..1 위반 방어 (parquet 노이즈 대응)
        pf = row["power_factor_avg"]
        if pf is not None and not (0.0 <= pf <= 1.0):
            row["power_factor_avg"] = None

        rows.append(row)
    return rows


async def insert_partition(rows: list[dict]) -> int:
    if not rows:
        return 0
    async with session_scope() as session:
        for start in range(0, len(rows), INSERT_CHUNK):
            chunk = rows[start : start + INSERT_CHUNK]
            stmt = pg_insert(PowerMinute.__table__).values(chunk)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["household_id", "channel_num", "bucket_ts"]
            )
            await session.execute(stmt)
    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bucket", default=GCS_BUCKET)
    ap.add_argument("--prefix", default=GCS_PREFIX)
    ap.add_argument("--limit-houses", type=int, default=0,
                    help="0=전체, >0=상위 N가구만 (스모크용)")
    ap.add_argument("--households", type=str, default="",
                    help="콤마구분 가구ID DB형식 (예: H011,H017)")
    ap.add_argument("--channels", type=str, default="",
                    help="콤마구분 채널 정수 (예: 1,21)")
    ap.add_argument("--dates", type=str, default="",
                    help="콤마구분 YYYYMMDD")
    ap.add_argument("--dry-run", action="store_true",
                    help="GCS read + 집계만 수행, INSERT 생략")
    args = ap.parse_args()

    hid_filter = {x.strip() for x in args.households.split(",") if x.strip()}
    ch_filter = {int(x) for x in args.channels.split(",") if x.strip()}
    date_filter = {x.strip() for x in args.dates.split(",") if x.strip()}
    limit = args.limit_houses or None

    gcs_fs = gcsfs.GCSFileSystem()  # ADC 자동
    print(
        f"scan: gs://{args.bucket}/{args.prefix}/  "
        f"limit_houses={limit or 'ALL'}  hid={hid_filter or 'ALL'}  "
        f"ch={ch_filter or 'ALL'}  dates={date_filter or 'ALL'}"
    )
    partitions = list_partitions(
        gcs_fs, args.bucket, args.prefix, limit, hid_filter, ch_filter, date_filter
    )
    print(f"partitions: {len(partitions)} parquet files")

    if not partitions:
        print("no partitions match — exit")
        return

    async def _run() -> None:
        total_rows = 0
        try:
            for i, (hid_db, ch_num, day, gcs_uri) in enumerate(partitions, 1):
                try:
                    table = pq.read_table(gcs_uri, filesystem=gcs_fs)
                except Exception as e:
                    print(
                        f"[{i}/{len(partitions)}] {hid_db} ch{ch_num:02d} {day}: "
                        f"READ FAIL — {type(e).__name__}: {e}",
                        file=sys.stderr,
                    )
                    continue

                try:
                    rows = aggregate_partition(table, hid_db, ch_num)
                except Exception as e:
                    print(
                        f"[{i}/{len(partitions)}] {hid_db} ch{ch_num:02d} {day}: "
                        f"AGG FAIL — {type(e).__name__}: {e}",
                        file=sys.stderr,
                    )
                    continue

                if args.dry_run:
                    msg = f"buckets={len(rows)} (dry-run)"
                    print(f"[{i}/{len(partitions)}] {hid_db} ch{ch_num:02d} {day}: {msg}")
                    if i == 1 and rows:
                        print(f"  sample[0]: {rows[0]}")
                    continue

                try:
                    inserted = await insert_partition(rows)
                except Exception as e:
                    print(
                        f"[{i}/{len(partitions)}] {hid_db} ch{ch_num:02d} {day}: "
                        f"INSERT FAIL — {type(e).__name__}: {e}",
                        file=sys.stderr,
                    )
                    continue

                total_rows += inserted
                print(
                    f"[{i}/{len(partitions)}] {hid_db} ch{ch_num:02d} {day}: "
                    f"buckets={inserted}  cum={total_rows}"
                )
            if not args.dry_run:
                print(f"DONE: total inserted (incl. CONFLICT NO-OP) = {total_rows}")
        finally:
            if not args.dry_run:
                await dispose_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
