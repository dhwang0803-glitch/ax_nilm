"""이상 이벤트 DB 저장 — Database 레포지토리 연동."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from anomaly_detection.src.models.schemas import AnomalyEvent


async def save_events(
    session: AsyncSession,
    household_id: str,
    events: list[AnomalyEvent],
) -> list[str]:
    """AnomalyEvent 리스트를 anomaly_events 테이블에 저장. 저장된 event_id 목록 반환."""
    from Database.src.repositories.anomaly_event_repository import AnomalyEventRepository  # noqa: PLC0415

    repo = AnomalyEventRepository(session)
    ids: list[str] = []
    for event in events:
        event_id = await repo.save(
            household_id=household_id,
            event_id=event.event_id,
            appliance_code=event.appliance_type,  # appliance_type = appliance_code 값 사용
            anomaly_type=event.anomaly_type.value,
            severity=event.severity.value,
            detected_at=event.detected_at,
            description=event.description,
            recommended_action=event.recommended_action,
        )
        ids.append(event_id)
    return ids
