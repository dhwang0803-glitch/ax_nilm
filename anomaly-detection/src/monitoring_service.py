"""MonitoringService — 모니터링 엔진 public API."""
from __future__ import annotations

from pathlib import Path

from anomaly_detection.src.memory.builder import ShortTermBuilder
from anomaly_detection.src.memory.compressor import compress
from anomaly_detection.src.memory.schemas import ApplianceBaseline, ShortTermEvent
from anomaly_detection.src.memory.store import MemoryStore
from anomaly_detection.src.models.schemas import DisaggregationResult

_DEFAULT_THRESHOLDS = Path(__file__).parents[1] / "config" / "thresholds.yaml"
_DEFAULT_MEMORY_DIR = Path(__file__).parents[1] / "memory"
_DEFAULT_REFERENCES = _DEFAULT_MEMORY_DIR / "cold_start" / "reference_images.json"


class MonitoringService:
    """모니터링 엔진 파이프라인.

    사용법:
        svc = MonitoringService()
        svc.update("house_001", records)   # 매시간 호출
        svc.compress("house_001")          # 매일 00시 호출
    """

    def __init__(
        self,
        thresholds_path: str | Path = _DEFAULT_THRESHOLDS,
        memory_dir: str | Path = _DEFAULT_MEMORY_DIR,
        references_path: str | Path = _DEFAULT_REFERENCES,
        min_confidence: float = 0.6,
    ) -> None:
        self._builder = ShortTermBuilder(thresholds_path, references_path)
        self._store = MemoryStore(memory_dir)
        self._min_confidence = min_confidence

    def update(
        self, house_id: str, records: list[DisaggregationResult]
    ) -> list[ShortTermEvent]:
        """DisaggregationResult → ShortTermEvent 생성 후 단기 메모리에 추가."""
        events = self._builder.build(records, self._min_confidence)
        for event in events:
            self._store.append_short_term(house_id, event)
        return events

    def compress(self, house_id: str) -> dict[str, ApplianceBaseline]:
        """00시 호출 — 단기 메모리를 장기 메모리에 EWM 반영 후 단기 리셋."""
        events = self._store.load_short_term(house_id)
        baselines = self._store.load_long_term(house_id)
        updated = compress(events, baselines)
        self._store.save_long_term(house_id, updated)
        self._store.reset_short_term(house_id)
        return updated

    def get_short_term(self, house_id: str) -> list[ShortTermEvent]:
        return self._store.load_short_term(house_id)

    def get_long_term(self, house_id: str) -> dict[str, ApplianceBaseline]:
        return self._store.load_long_term(house_id)
