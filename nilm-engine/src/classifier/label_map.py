from __future__ import annotations
from typing import TypedDict, Literal

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
    """22종 가전 ON 판정 임계값 리스트 — PDF 별첨4 per-appliance 기준 (인덱스 순서 = APPLIANCE_LABELS)."""
    return [get_threshold(name) for name in APPLIANCE_LABELS]


# ---------------------------------------------------------------------------
# AI Hub 71685 별첨4 — 가전별 라벨링 기준 (출처: '23년 활용가이드라인 v1.0)
# ---------------------------------------------------------------------------

class LabelingCriteria(TypedDict):
    """AI Hub 71685 별첨4 가전기기별 라벨링 기준."""
    threshold_w: float | None
    threshold_kind: Literal["absolute", "upper_bound", "relative", "always_on"]
    min_active_seconds: float | None
    gap_seconds: float | None
    pdf_group: Literal["A_heating", "B_step", "C_cycle", "D_always"]
    notes: str


# 키 순서 = APPLIANCE_LABELS 인덱스 순서 (0~21)
APPLIANCE_LABELING: dict[str, LabelingCriteria] = {
    "TV": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 120.0, "gap_seconds": 1.0,
        "pdf_group": "B_step",
        "notes": "센서 동작 구간(대기전력 이상 비슷한 수준)은 제외. 2분 이상만 라벨링.",
    },
    "전기포트": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating", "notes": "",
    },
    "선풍기": {
        "threshold_w": 2.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "B_step", "notes": "",
    },
    "의류건조기": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 60.0,
        "pdf_group": "C_cycle",
        "notes": "코스에 따라 휴지 구간 다양 — Gap 1분으로 분리.",
    },
    "전기밥솥": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": None, "gap_seconds": 300.0,
        "pdf_group": "C_cycle",
        "notes": "취사/보온 상태 구분. 5분 이상 분리되지 않으면 단일 구간.",
    },
    "식기세척기/건조기": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 300.0,
        "pdf_group": "C_cycle", "notes": "",
    },
    "세탁기": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 10.0,
        "pdf_group": "C_cycle",
        "notes": "코스 중간 휴지 시 단일 구간. 10W 미만이라도 단일 구간 가능.",
    },
    "헤어드라이기": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "짧은 ON/OFF 반복 가능.",
    },
    "에어프라이어": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "히팅-대기(바람순환) 패턴.",
    },
    "진공청소기(유선)": {
        "threshold_w": 6.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "B_step", "notes": "",
    },
    "전자레인지": {
        "threshold_w": 10.0, "threshold_kind": "absolute",
        "min_active_seconds": 10.0, "gap_seconds": 1.0,
        "pdf_group": "C_cycle",
        "notes": "동작 시 최소 1000W 이상. 10W 이하는 센싱/도어/종료 신호.",
    },
    "에어컨": {
        "threshold_w": 2.0, "threshold_kind": "absolute",
        "min_active_seconds": 60.0, "gap_seconds": 300.0,
        "pdf_group": "C_cycle",
        "notes": "인버터 미풍 모드(2W 이상)도 활성. Always-On 아님.",
    },
    "인덕션(전기레인지)": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "활성 시 약 1000W 이상으로 급상승.",
    },
    "전기장판/담요": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "0.5초 미만이라도 다음 활성과 1초 미만 간격이고 전체 0.5초 이상이면 활성 유지.",
    },
    "온수매트": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 0.5, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "전기장판과 동일 룰.",
    },
    "제습기": {
        "threshold_w": 3.0, "threshold_kind": "upper_bound",
        "min_active_seconds": 30.0, "gap_seconds": 300.0,
        "pdf_group": "D_always",
        "notes": "대기전력 상한 3W. 제습/Fan만/인버터 ON-OFF 3가지 상태 구분.",
    },
    "컴퓨터": {
        "threshold_w": 5.0, "threshold_kind": "absolute",
        "min_active_seconds": 10.0, "gap_seconds": 60.0,
        "pdf_group": "B_step",
        "notes": "기기별 보기로 다른 날 데이터 종합해 대기전력 범위 판단. 대기 5~10W 가능.",
    },
    "공기청정기": {
        "threshold_w": 3.0, "threshold_kind": "upper_bound",
        "min_active_seconds": 60.0, "gap_seconds": 60.0,
        "pdf_group": "D_always",
        "notes": "대기전력 상한 3W. 24시간 ON 가능성 높지만 활성 상태 아닐 수 있음.",
    },
    "전기다리미": {
        "threshold_w": 15.0, "threshold_kind": "absolute",
        "min_active_seconds": None, "gap_seconds": 1.0,
        "pdf_group": "A_heating",
        "notes": "ON 상태 매우 명확.",
    },
    "일반 냉장고": {
        "threshold_w": None, "threshold_kind": "always_on",
        "min_active_seconds": 3600.0, "gap_seconds": None,
        "pdf_group": "D_always",
        "notes": "24시간 전체 활성. X축 1시간 스케일에서 컴프 사이클 봉우리 라벨링.",
    },
    "김치냉장고": {
        "threshold_w": None, "threshold_kind": "always_on",
        "min_active_seconds": 3600.0, "gap_seconds": None,
        "pdf_group": "D_always",
        "notes": "일반 냉장고와 동일.",
    },
    "무선공유기/셋톱박스": {
        "threshold_w": 0.5, "threshold_kind": "relative",
        "min_active_seconds": 120.0, "gap_seconds": None,
        "pdf_group": "D_always",
        "notes": "기본 사용 전력 + 0.5W 이상이 임계. X축 2분 스케일 확대 후에도 구분되는 상승만 라벨링.",
    },
}


# ---------------------------------------------------------------------------
# 속도 그룹 — pdf_group 기반 (A/B_step → fast, C_cycle → slow, D_always → always_on)
# ---------------------------------------------------------------------------

SPEED_GROUP: dict[str, Literal["fast", "slow", "always_on"]] = {
    # A_heating (7종) + B_step (5종) → 30Hz, window=1024
    "TV": "fast", "전기포트": "fast", "선풍기": "fast",
    "헤어드라이기": "fast", "에어프라이어": "fast", "진공청소기(유선)": "fast",
    "전자레인지": "fast", "인덕션(전기레인지)": "fast", "전기장판/담요": "fast",
    "온수매트": "fast", "전기다리미": "fast", "컴퓨터": "fast",
    # C_cycle (5종) → 1Hz 다운샘플, window=1800 (30분)
    "의류건조기": "slow", "전기밥솥": "slow", "식기세척기/건조기": "slow",
    "세탁기": "slow", "에어컨": "slow",
    # D_always (5종) → 1Hz, 냉장고 2종은 always-ON 회귀 전용
    "제습기": "always_on", "공기청정기": "always_on",
    "일반 냉장고": "always_on", "김치냉장고": "always_on",
    "무선공유기/셋톱박스": "always_on",
}

SPEED_GROUP_CONFIG: dict[str, dict] = {
    #                   resample_hz  window_size  stride
    "fast":      {"resample_hz": 30, "window_size": 1024, "stride": 30},
    "slow":      {"resample_hz":  1, "window_size": 1800, "stride": 30},
    "always_on": {"resample_hz":  1, "window_size": 1800, "stride": 30},
}


def get_threshold(appliance_name: str) -> float:
    """가전별 ON 판정 임계값 (W). always_on → 5.0, relative → 5.0 (1차 근사)."""
    crit = APPLIANCE_LABELING[appliance_name]
    if crit["threshold_kind"] in ("always_on", "relative"):
        return 5.0
    assert crit["threshold_w"] is not None
    return crit["threshold_w"]


def get_min_active_samples(appliance_name: str, sampling_rate_hz: int = 30) -> int | None:
    """활성 최소 동작 시간 → 샘플 수. None이면 시간 기준 없음."""
    sec = APPLIANCE_LABELING[appliance_name]["min_active_seconds"]
    return None if sec is None else int(sec * sampling_rate_hz)


def get_gap_samples(appliance_name: str, sampling_rate_hz: int = 30) -> int | None:
    """Gap 분리 시간 → 샘플 수. None이면 적용 안 함."""
    sec = APPLIANCE_LABELING[appliance_name]["gap_seconds"]
    return None if sec is None else int(sec * sampling_rate_hz)
