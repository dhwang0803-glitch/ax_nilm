N_APPLIANCES = 22

APPLIANCE_LABELS: list[str] = [
    "TV",                    # 0  type1
    "전기포트",               # 1  type1
    "선풍기",                 # 2  type1
    "의류건조기",             # 3  type2
    "전기밥솥",               # 4  type2
    "식기세척기/건조기",       # 5  type2
    "세탁기",                 # 6  type2
    "헤어드라이기",           # 7  type2
    "에어프라이어",           # 8  type2
    "진공청소기(유선)",        # 9  type2
    "전자레인지",             # 10 type2
    "에어컨",                 # 11 type3
    "인덕션(전기레인지)",      # 12 type3
    "전기장판/담요",          # 13 type3
    "온수매트",               # 14 type3
    "제습기",                 # 15 type3
    "컴퓨터",                 # 16 type3
    "공기청정기",             # 17 type3
    "전기다리미",             # 18 type3
    "일반 냉장고",            # 19 type4
    "김치냉장고",             # 20 type4
    "무선공유기/셋톱박스",    # 21 type4
]

APPLIANCE_TYPES: dict[str, str] = {
    "TV": "type1", "전기포트": "type1", "선풍기": "type1",
    "의류건조기": "type2", "전기밥솥": "type2", "식기세척기/건조기": "type2",
    "세탁기": "type2", "헤어드라이기": "type2", "에어프라이어": "type2",
    "진공청소기(유선)": "type2", "전자레인지": "type2",
    "에어컨": "type3", "인덕션(전기레인지)": "type3", "전기장판/담요": "type3",
    "온수매트": "type3", "제습기": "type3", "컴퓨터": "type3",
    "공기청정기": "type3", "전기다리미": "type3",
    "일반 냉장고": "type4", "김치냉장고": "type4", "무선공유기/셋톱박스": "type4",
}

# Type별 ON/OFF 판정 임계값 [W]
_ON_THRESHOLD: dict[str, float] = {
    "type1": 30.0,
    "type2": 20.0,
    "type3": 50.0,
    "type4": 5.0,
}


def get_on_thresholds() -> list[float]:
    """22종 가전 ON 판정 임계값 리스트 — 인덱스 순서 = APPLIANCE_LABELS 순서."""
    return [_ON_THRESHOLD[APPLIANCE_TYPES[name]] for name in APPLIANCE_LABELS]
