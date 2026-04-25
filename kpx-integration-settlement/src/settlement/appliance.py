"""가전별 DR 기여 분류 및 내부식 계산.

DR 가전 유형:
  온도 제어형  — 이벤트 구간 중 소비량 직접 절감 (에어컨, 제습기, 전기장판, 온수매트)
  부하 이동형  — 이벤트 구간 전후로 사용 이동 (세탁기, 의류건조기, 전기밥솥, 인덕션 등)
  상시 부하    — DR 절감 대상 외 (냉장고, 김치냉장고, 무선공유기/셋톱박스)
"""
from __future__ import annotations

from enum import Enum


class DRType(str, Enum):
    TEMPERATURE_CONTROL = "temperature_control"  # 온도 제어형
    LOAD_SHIFT          = "load_shift"           # 부하 이동형
    ALWAYS_ON           = "always_on"            # 상시 부하 (DR 제외)


APPLIANCE_DR_TYPE: dict[str, DRType] = {
    # 온도 제어형
    "에어컨":           DRType.TEMPERATURE_CONTROL,
    "제습기":           DRType.TEMPERATURE_CONTROL,
    "전기장판, 담요":   DRType.TEMPERATURE_CONTROL,
    "온수매트":         DRType.TEMPERATURE_CONTROL,
    # 부하 이동형
    "세탁기":           DRType.LOAD_SHIFT,
    "의류건조기":       DRType.LOAD_SHIFT,
    "전기밥솥":         DRType.LOAD_SHIFT,
    "인덕션(전기레인지)": DRType.LOAD_SHIFT,
    "식기세척기":       DRType.LOAD_SHIFT,
    "에어프라이어":     DRType.LOAD_SHIFT,
    "전자레인지":       DRType.LOAD_SHIFT,
    # 상시 부하
    "일반 냉장고":              DRType.ALWAYS_ON,
    "김치 냉장고":              DRType.ALWAYS_ON,
    "무선공유기/셋톱박스":      DRType.ALWAYS_ON,
    # DR 참여 가능하나 계절·상황 의존 (LLM이 판단)
    "TV":               DRType.LOAD_SHIFT,
    "컴퓨터":           DRType.LOAD_SHIFT,
    "전기다리미":       DRType.LOAD_SHIFT,
    "공기청정기":       DRType.LOAD_SHIFT,
    "헤어드라이기":     DRType.LOAD_SHIFT,
    "진공 청소기(유선)": DRType.LOAD_SHIFT,
    "전기포트":         DRType.LOAD_SHIFT,
    "선풍기":           DRType.TEMPERATURE_CONTROL,
}


def get_dr_type(appliance_name: str) -> DRType:
    return APPLIANCE_DR_TYPE.get(appliance_name, DRType.LOAD_SHIFT)


def is_dr_eligible(appliance_name: str) -> bool:
    return get_dr_type(appliance_name) != DRType.ALWAYS_ON


def calc_appliance_savings(
    appliance_name: str,
    channel_cbl_kwh: float,
    channel_actual_kwh: float,
) -> float:
    """내부식: 가전별 절감량(추정) = 가전별 기준 사용량 - 가전별 NILM 추정 사용량."""
    if not is_dr_eligible(appliance_name):
        return 0.0
    return channel_cbl_kwh - channel_actual_kwh
