"""Repository 구현체 + Protocol 통합 export.

다운스트림은 Protocol 만 import 권장:

.. code-block:: python

    from Database.src.repositories import PowerRepository  # 구현체 type alias
    from Database.src.repositories.protocols import PowerRepository as PowerRepoProto

또는 인터페이스를 직접 사용:

.. code-block:: python

    def __init__(self, repo: PowerRepoProto): ...
"""
from .activity_repository import ActivityRepository
from .aggregator_repository import AggregatorRepository
from .dr_repository import DRRepository
from .household_repository import HouseholdRepository
from .ingestion_log_repository import IngestionLogRepository
from .nilm_inference_repository import NILMInferenceRepository
from .pii_repository import PIIRepository
from .power_repository import PowerRepository
from .protocols import (
    ActivityRepository as ActivityRepositoryProto,
    AggregatorRepository as AggregatorRepositoryProto,
    DailyUsage,
    DecryptedPII,
    DRRepository as DRRepositoryProto,
    HouseholdRepository as HouseholdRepositoryProto,
    IngestionLogRepository as IngestionLogRepositoryProto,
    NILMInferenceRepository as NILMInferenceRepositoryProto,
    PIIRepository as PIIRepositoryProto,
    PowerRepository as PowerRepositoryProto,
)

__all__ = [
    # 구현체
    "ActivityRepository",
    "AggregatorRepository",
    "DRRepository",
    "HouseholdRepository",
    "IngestionLogRepository",
    "NILMInferenceRepository",
    "PIIRepository",
    "PowerRepository",
    # Protocols (다운스트림 의존 표면)
    "ActivityRepositoryProto",
    "AggregatorRepositoryProto",
    "DRRepositoryProto",
    "HouseholdRepositoryProto",
    "IngestionLogRepositoryProto",
    "NILMInferenceRepositoryProto",
    "PIIRepositoryProto",
    "PowerRepositoryProto",
    # DTO
    "DailyUsage",
    "DecryptedPII",
]
