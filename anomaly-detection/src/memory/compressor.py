"""00시 단기 메모리 → 장기 메모리 압축 (EWM 갱신)."""
from __future__ import annotations

from anomaly_detection.src.memory.schemas import (
    ApplianceBaseline,
    ModeBaseline,
    ShortTermEvent,
)

_EWM_ALPHA = 0.2


def _ewm_update(old: float, new: float, alpha: float = _EWM_ALPHA) -> float:
    return alpha * new + (1 - alpha) * old


def compress(
    events: list[ShortTermEvent],
    baselines: dict[str, ApplianceBaseline],
) -> dict[str, ApplianceBaseline]:
    """단기 이벤트를 장기 기준값에 EWM으로 반영.

    baselines는 load_long_term()으로 읽어온 현재 장기 메모리.
    반환값을 save_long_term()으로 저장한다.
    """
    updated = {k: v for k, v in baselines.items()}

    for event in events:
        appliance = event.appliance

        if appliance not in updated:
            updated[appliance] = ApplianceBaseline(appliance=appliance)

        bl = updated[appliance]

        mode = event.mode
        if mode not in bl.modes:
            bl.modes[mode] = ModeBaseline(
                avg_energy_wh=event.energy_wh,
                avg_duration_min=event.duration_min,
                sample_count=1,
            )
        else:
            m = bl.modes[mode]
            m.avg_energy_wh = _ewm_update(m.avg_energy_wh, event.energy_wh)
            m.avg_duration_min = _ewm_update(m.avg_duration_min, event.duration_min)
            m.sample_count += 1

        if event.standby:
            bl.standby_avg_w = _ewm_update(bl.standby_avg_w, event.standby.avg_w)
            bl.standby_avg_duration_min = _ewm_update(
                bl.standby_avg_duration_min, event.standby.duration_min
            )

    return updated
