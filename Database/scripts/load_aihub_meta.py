"""AI Hub 71685 라벨 ZIP → households / household_channels / household_daily_env 적재.

PII (`household_pii`) 는 Fernet 키 발급 후 별도 스크립트에서 적재 — 본 스크립트 범위 외.
재실행 안전: 모든 INSERT 가 PG `ON CONFLICT DO NOTHING`.

Usage:
    # 사전: IAP 터널 + DATABASE_URL 환경변수 (postgresql+asyncpg://...) 활성
    python Database/scripts/load_aihub_meta.py --limit-houses 10 --dry-run
    python Database/scripts/load_aihub_meta.py --limit-houses 10
    python Database/scripts/load_aihub_meta.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import zipfile
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path

# Database/ 부모 디렉토리를 sys.path 에 추가해 src 모듈 import 가능하게.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402

from Database.src.db import dispose_engine, session_scope  # noqa: E402
from Database.src.models.household import (  # noqa: E402
    Household,
    HouseholdChannel,
    HouseholdDailyEnv,
)

DEFAULT_ZIP = Path(
    r"D:\nilm_raw\downloads"
    r"\129.전기 인프라 지능화를 위한 가전기기 전력 사용량 데이터"
    r"\3.개방데이터\1.데이터\Training\02.라벨링데이터\TL.zip"
)

# ch## → DB appliance_code. schemas/003_seed_appliance_types.sql 와 동기화 유지.
# AI Hub `meta.name` 은 DB `name_ko` 와 표기가 다른 경우가 있어 (냉장고/일반 냉장고 등)
# 한글 매칭 대신 채널 번호로 매핑. 같은 채널 = 같은 가전임을 79가구 전수조사로 확인.
CHANNEL_TO_CODE: dict[int, str] = {
    1: "MAIN",          2: "TV",            3: "FAN",           4: "KETTLE",
    5: "RICE_COOKER",   6: "WASHER",        7: "HAIR_DRYER",    8: "VACUUM",
    9: "MICROWAVE",    10: "AIR_FRYER",    11: "DRYER",        12: "DISHWASHER",
   13: "AC",           14: "ELEC_BLANKET", 15: "HOT_MAT",      16: "INDUCTION",
   17: "PC",           18: "IRON",         19: "AIR_PURIFIER", 20: "DEHUMIDIFIER",
   21: "FRIDGE",       22: "KIMCHI_FRIDGE", 23: "ROUTER",
}

VALID_POWER_CATEGORIES = {"high", "middle", "low"}


def hid_from_path(raw: str) -> str | None:
    # "house_001" → "H001"  (DB CHECK ^H[0-9]{3}$)
    parts = raw.split("_")
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return f"H{int(parts[1]):03d}"


def parse_float_or_none(v) -> float | None:
    if v is None or v == "" or v == "unknown":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_efficiency(v) -> int | None:
    """energy_efficiency 1~5 외 값은 NULL (DB CHECK 위반 방지)."""
    f = parse_float_or_none(v)
    if f is None:
        return None
    i = int(f)
    return i if 1 <= i <= 5 else None


def parse_power_category(v) -> str | None:
    if v is None or v == "":
        return None
    return v if v in VALID_POWER_CATEGORIES else None


def parse_date_yyyymmdd(s: str) -> date | None:
    try:
        return datetime.strptime(s, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def normalize_blank(v) -> str | None:
    return None if v in (None, "") else v


def collect(zip_path: Path, limit_houses: int | None) -> tuple[list[dict], list[dict], list[dict]]:
    """ZIP 단일 패스로 3 테이블 행 수집. (가구, 채널, 일) 첫 발견만 보존."""
    households: dict[str, dict] = OrderedDict()
    channels: dict[tuple[str, int], dict] = OrderedDict()
    daily_env: dict[tuple[str, date], dict] = OrderedDict()

    house_seen: set[str] = set()
    skipped_unknown_ch = 0
    skipped_bad_path = 0

    with zipfile.ZipFile(zip_path) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".json"))
        for n in names:
            parts = n.split("/")
            if len(parts) < 3:
                skipped_bad_path += 1
                continue

            hid = hid_from_path(parts[0])
            if hid is None:
                skipped_bad_path += 1
                continue

            # limit-houses: 새 가구 진입 차단 (이미 본 가구의 다른 채널/일은 계속 처리)
            if limit_houses and hid not in house_seen and len(house_seen) >= limit_houses:
                continue
            house_seen.add(hid)

            raw_ch = parts[1]
            if not raw_ch.startswith("ch") or not raw_ch[2:].isdigit():
                skipped_bad_path += 1
                continue
            ch_num = int(raw_ch[2:])

            fname = parts[-1][:-5]
            obs_date = parse_date_yyyymmdd(fname.split("_")[-1])

            need_household = hid not in households
            need_channel = (hid, ch_num) not in channels
            need_daily = obs_date is not None and (hid, obs_date) not in daily_env
            if not (need_household or need_channel or need_daily):
                continue

            try:
                obj = json.loads(z.read(n).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            meta = obj.get("meta") or {}

            if need_household:
                households[hid] = {
                    "household_id": hid,
                    "house_type": meta.get("house_type"),
                    "residential_type": meta.get("residential_type"),
                    "residential_area": meta.get("residential_area"),
                    "co_lighting": meta.get("co-lighting"),
                    # cluster_label / dr_enrolled / aggregator_id : DB default (NULL/false/NULL)
                }

            if need_channel:
                code = CHANNEL_TO_CODE.get(ch_num)
                if code is None:
                    skipped_unknown_ch += 1
                else:
                    channels[(hid, ch_num)] = {
                        "household_id": hid,
                        "channel_num": ch_num,
                        "appliance_code": code,
                        "device_name": meta.get("name"),
                        "brand": meta.get("brand"),
                        "power_category": parse_power_category(meta.get("power_category")),
                        "power_consumption": parse_float_or_none(meta.get("power_consumption")),
                        "energy_efficiency": parse_efficiency(meta.get("energy_efficiency")),
                    }

            if need_daily:
                daily_env[(hid, obs_date)] = {
                    "household_id": hid,
                    "observed_date": obs_date,
                    "weather_raw": normalize_blank(meta.get("weather")),
                    "temperature_c": parse_float_or_none(meta.get("temperature")),
                    "wind_speed_ms": parse_float_or_none(meta.get("windchill")),
                    "humidity_pct": parse_float_or_none(meta.get("humidity")),
                }

    if skipped_unknown_ch:
        print(f"⚠ skipped {skipped_unknown_ch} unknown-channel rows", file=sys.stderr)
    if skipped_bad_path:
        print(f"⚠ skipped {skipped_bad_path} malformed-path rows", file=sys.stderr)

    return list(households.values()), list(channels.values()), list(daily_env.values())


async def insert_rows(rows_h: list[dict], rows_c: list[dict], rows_d: list[dict]) -> None:
    async with session_scope() as session:
        if rows_h:
            stmt = pg_insert(Household.__table__).values(rows_h)
            stmt = stmt.on_conflict_do_nothing(index_elements=["household_id"])
            await session.execute(stmt)
        if rows_c:
            stmt = pg_insert(HouseholdChannel.__table__).values(rows_c)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["household_id", "channel_num"]
            )
            await session.execute(stmt)
        if rows_d:
            stmt = pg_insert(HouseholdDailyEnv.__table__).values(rows_d)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["household_id", "observed_date"]
            )
            await session.execute(stmt)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, default=DEFAULT_ZIP, help="TL.zip 경로")
    ap.add_argument("--limit-houses", type=int, default=0,
                    help="0=전체, >0=상위 N가구만 (스모크 테스트용)")
    ap.add_argument("--dry-run", action="store_true",
                    help="수집만 하고 INSERT 생략")
    args = ap.parse_args()

    if not args.zip.exists():
        sys.exit(f"ZIP not found: {args.zip}")

    limit = args.limit_houses or None
    print(f"scan: {args.zip}  limit_houses={limit or 'ALL'}")
    rows_h, rows_c, rows_d = collect(args.zip, limit)
    print(
        f"collected: households={len(rows_h)}, "
        f"channels={len(rows_c)}, daily_env={len(rows_d)}"
    )

    if args.dry_run:
        print("[dry-run] no INSERT")
        # 표본 1건씩 보여주기
        for label, rows in (("household", rows_h), ("channel", rows_c), ("daily_env", rows_d)):
            if rows:
                print(f"  {label}[0]: {rows[0]}")
        return

    async def _run() -> None:
        try:
            await insert_rows(rows_h, rows_c, rows_d)
            print(
                f"INSERT ok (ON CONFLICT DO NOTHING): "
                f"households={len(rows_h)}, channels={len(rows_c)}, daily_env={len(rows_d)}"
            )
        finally:
            await dispose_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
