import os
from fastapi import APIRouter
from src.agent.data_tools import get_household_profile

router = APIRouter()


@router.get("/settings/account")
def account():
    hh = os.getenv("DEFAULT_HH", "HH001")

    profile = get_household_profile(hh)
    raw = profile.get("raw", {})

    if "error" in profile:
        return {
            "profile": {"name": "알 수 없음", "email": "", "phone": "", "memberCount": 0},
            "kepco": {
                "customerNo": "",
                "addressMasked": "",
                "contractType": "",
                "linkedAt": "",
            },
        }

    house_type = raw.get("house_type", "")
    # DB returns residential_area as string (e.g. "84㎡"); mock returns area_m2 as int
    area_raw = raw.get("residential_area") or raw.get("area_m2", "")
    area_str = f"{area_raw}㎡" if isinstance(area_raw, int) else str(area_raw or "")
    subscription = raw.get("subscription", "")
    # members is PII-encrypted in DB; mock provides it directly
    members = raw.get("members", 0)

    return {
        "profile": {
            "name": f"{hh} 가구",
            "email": "",
            "phone": "",
            "memberCount": members,
        },
        "kepco": {
            "customerNo": f"{hh}-KEPCO",
            "addressMasked": f"{house_type} {area_str}".strip(),
            "contractType": subscription,
            "linkedAt": "2026-01-01",
        },
    }
