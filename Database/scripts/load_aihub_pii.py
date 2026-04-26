"""AI Hub 71685 라벨 ZIP → household_pii 적재 (Fernet AES-256 암호화).

🔒 보안 원칙
    1. 키는 환경변수 ``CREDENTIAL_MASTER_KEY`` 만으로 주입 (PIIRepository 가 강제).
       Secret Manager 에서 매 셸 동적 조립 — .env / 코드에 평문 저장 금지.
    2. 평문 address/members 를 stdout/로그에 출력하지 않음 (--dry-run 도 마스킹).
    3. 가구당 첫 JSON 1개의 meta 만 사용 — 79가구 전수조사로 가구 내 동일성 확인.

사전:
    set -a; source Database/.env; set +a
    gcloud compute start-iap-tunnel "$INSTANCE_NAME" 5432 \
        --local-host-port="localhost:$LOCAL_PG_PORT" --zone="$ZONE"  &  # 별도 터미널 권장
    APP_PWD=$(gcloud secrets versions access latest --secret="$SECRET_NAME")
    export DATABASE_URL="postgresql+asyncpg://$APP_USER:$APP_PWD@localhost:$LOCAL_PG_PORT/$DB_NAME"
    export CREDENTIAL_MASTER_KEY=$(gcloud secrets versions access latest --secret=ax-nilm-credential-master-key)

Usage:
    python Database/scripts/load_aihub_pii.py --limit-houses 5 --dry-run
    python Database/scripts/load_aihub_pii.py --limit-houses 5
    python Database/scripts/load_aihub_pii.py
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import zipfile
from collections import OrderedDict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Database.src.db import dispose_engine, session_scope  # noqa: E402
from Database.src.repositories.pii_repository import PIIRepository  # noqa: E402

DEFAULT_ZIP = Path(
    r"D:\nilm_raw\downloads"
    r"\129.전기 인프라 지능화를 위한 가전기기 전력 사용량 데이터"
    r"\3.개방데이터\1.데이터\Training\02.라벨링데이터\TL.zip"
)


def hid_from_path(raw: str) -> str | None:
    parts = raw.split("_")
    if len(parts) != 2 or not parts[1].isdigit():
        return None
    return f"H{int(parts[1]):03d}"


def normalize_blank(v):
    return None if v in (None, "") else v


def parse_bool_or_none(v) -> bool | None:
    # AI Hub `meta.income` 은 boolean true/false. 문자열로 들어올 가능성 방어.
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in {"true", "1", "yes"}:
            return True
        if s in {"false", "0", "no"}:
            return False
    return None


def members_to_str(v) -> str | None:
    # PIIRepository.upsert_encrypted 는 str | None 만 받으므로 list/dict 는
    # JSON 직렬화. ensure_ascii=False 로 한글 원형 보존 (복호화 후 가독성).
    if v is None or v == "":
        return None
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


def strip_list(v) -> list[str] | None:
    # extra_appliances 는 원본에 앞 공백 혼입 (` 태블릿PC` 등) → strip.
    # utility_facilities 도 동일 정제 적용 (해롭지 않음).
    if not isinstance(v, list):
        return None
    cleaned = [s.strip() for s in v if isinstance(s, str) and s.strip()]
    return cleaned or None


def collect(zip_path: Path, limit_houses: int | None) -> list[dict]:
    """가구당 첫 JSON 1개에서 PII 필드 수집."""
    pii: dict[str, dict] = OrderedDict()
    with zipfile.ZipFile(zip_path) as z:
        names = sorted(n for n in z.namelist() if n.endswith(".json"))
        for n in names:
            parts = n.split("/")
            if len(parts) < 3:
                continue
            hid = hid_from_path(parts[0])
            if hid is None:
                continue
            if hid in pii:
                continue
            if limit_houses and len(pii) >= limit_houses:
                break

            try:
                obj = json.loads(z.read(n).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            meta = obj.get("meta") or {}

            pii[hid] = {
                "household_id": hid,
                "address": normalize_blank(meta.get("address")),
                "members": members_to_str(meta.get("members")),
                "income_dual": parse_bool_or_none(meta.get("income")),
                "utility_facilities": strip_list(meta.get("utility_facilities")),
                "extra_appliances": strip_list(meta.get("extra_appliances")),
            }
    return list(pii.values())


def mask(s: str | None, keep: int = 2) -> str:
    if s is None:
        return "<NULL>"
    if len(s) <= keep:
        return "*" * len(s)
    return s[:keep] + "*" * (len(s) - keep)


async def insert_rows(rows: list[dict]) -> int:
    written = 0
    async with session_scope() as session:
        repo = PIIRepository(session)
        for r in rows:
            await repo.upsert_encrypted(
                household_id=r["household_id"],
                address=r["address"],
                members=r["members"],
                income_dual=r["income_dual"],
                utility_facilities=r["utility_facilities"],
                extra_appliances=r["extra_appliances"],
            )
            written += 1
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, default=DEFAULT_ZIP, help="TL.zip 경로")
    ap.add_argument("--limit-houses", type=int, default=0,
                    help="0=전체, >0=상위 N가구만 (스모크 테스트용)")
    ap.add_argument("--dry-run", action="store_true",
                    help="수집만 하고 INSERT 생략. 평문 PII 는 마스킹 출력")
    args = ap.parse_args()

    if not args.zip.exists():
        sys.exit(f"ZIP not found: {args.zip}")

    limit = args.limit_houses or None
    print(f"scan: {args.zip}  limit_houses={limit or 'ALL'}")
    rows = collect(args.zip, limit)
    print(f"collected: pii_rows={len(rows)}")

    addr_null = sum(1 for r in rows if r["address"] is None)
    members_null = sum(1 for r in rows if r["members"] is None)
    income_null = sum(1 for r in rows if r["income_dual"] is None)
    util_null = sum(1 for r in rows if r["utility_facilities"] is None)
    extra_null = sum(1 for r in rows if r["extra_appliances"] is None)
    print(
        f"NULL counts: address={addr_null}, members={members_null}, "
        f"income_dual={income_null}, utility_facilities={util_null}, "
        f"extra_appliances={extra_null}"
    )

    if args.dry_run:
        print("[dry-run] no INSERT — sample (masked):")
        for r in rows[:3]:
            print(
                f"  {r['household_id']}: address={mask(r['address'])}, "
                f"members={mask(r['members'])}, income_dual={r['income_dual']}, "
                f"utility_facilities={r['utility_facilities']}, "
                f"extra_appliances={r['extra_appliances']}"
            )
        return

    async def _run() -> None:
        try:
            n = await insert_rows(rows)
            print(f"INSERT ok (Fernet upsert): pii_rows={n}")
        finally:
            await dispose_engine()

    asyncio.run(_run())


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
