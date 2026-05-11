"""ax_nilm ORM 모델 — SQLAlchemy 2.0 declarative 통합 export.

신규 ORM 추가 시 본 모듈에 re-export 해 한 번의 import 로 모든 모델이
등록(metadata 에 적재) 되도록 한다 (테스트 픽스처/마이그레이션 추론용).
"""
from .base import Base
from .meta import ApplianceType, Aggregator, ApplianceStatusCode
from .household import (
    Household,
    HouseholdChannel,
    HouseholdDailyEnv,
    HouseholdEmbedding,
    HouseholdPII,
)
from .power import PowerEfficiency30Min, PowerHour, PowerMinute
from .nilm import ActivityInterval, ApplianceStatusInterval, IngestionLog
from .dr import DRApplianceSavings, DREvent, DRResult

__all__ = [
    "Base",
    # meta
    "ApplianceType",
    "Aggregator",
    "ApplianceStatusCode",
    # household
    "Household",
    "HouseholdChannel",
    "HouseholdDailyEnv",
    "HouseholdEmbedding",
    "HouseholdPII",
    # power
    "PowerMinute",
    "PowerHour",
    "PowerEfficiency30Min",
    # nilm
    "ActivityInterval",
    "ApplianceStatusInterval",
    "IngestionLog",
    # dr
    "DREvent",
    "DRResult",
    "DRApplianceSavings",
]
