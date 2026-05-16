"""JSON 파일 기반 단기/장기 메모리 저장소."""
from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from pathlib import Path

from anomaly_detection.src.memory.schemas import (
    ApplianceBaseline,
    ModeBaseline,
    ShortTermEvent,
    StandbyEvent,
)

_DATE_FMT = "%Y-%m-%dT%H:%M:%S"


def _to_dict(obj) -> dict:
    """dataclass → JSON 직렬화 가능한 dict."""
    d = dataclasses.asdict(obj)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.strftime(_DATE_FMT)
    return d


def _event_from_dict(d: dict) -> ShortTermEvent:
    d["started_at"] = datetime.strptime(d["started_at"], _DATE_FMT)
    standby = d.get("standby")
    d["standby"] = StandbyEvent(**standby) if standby else None
    d.pop("tda_fingerprint", None)
    d.pop("mode_confidence", None)
    return ShortTermEvent(**d)


def _baseline_from_dict(d: dict) -> ApplianceBaseline:
    modes = {
        mode_name: ModeBaseline(**mode_data)
        for mode_name, mode_data in d.pop("modes", {}).items()
    }
    bl = ApplianceBaseline(**d)
    bl.modes = modes
    return bl


class MemoryStore:
    """JSON 파일 read/write.

    PoC 저장소 — 프로덕션 전환 시 Redis(단기) + TimescaleDB(장기)로 교체.
    """

    def __init__(self, base_dir: str | Path) -> None:
        self.base = Path(base_dir)
        self._short = self.base / "short_term"
        self._long = self.base / "long_term"
        self._cold = self.base / "cold_start"
        for d in (self._short, self._long, self._cold):
            d.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    #  단기 메모리                                                          #
    # ------------------------------------------------------------------ #

    def load_short_term(self, house_id: str) -> list[ShortTermEvent]:
        path = self._short / f"{house_id}.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        return [_event_from_dict(d) for d in data]

    def save_short_term(self, house_id: str, events: list[ShortTermEvent]) -> None:
        path = self._short / f"{house_id}.json"
        path.write_text(
            json.dumps([_to_dict(e) for e in events], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def append_short_term(self, house_id: str, event: ShortTermEvent) -> None:
        events = self.load_short_term(house_id)
        events.append(event)
        self.save_short_term(house_id, events)

    def reset_short_term(self, house_id: str) -> None:
        path = self._short / f"{house_id}.json"
        path.write_text("[]", encoding="utf-8")

    # ------------------------------------------------------------------ #
    #  장기 메모리                                                          #
    # ------------------------------------------------------------------ #

    def load_long_term(self, house_id: str) -> dict[str, ApplianceBaseline]:
        path = self._long / f"{house_id}.json"
        if not path.exists():
            return self._load_cold_start()
        data = json.loads(path.read_text(encoding="utf-8"))
        return {k: _baseline_from_dict(v) for k, v in data.items()}

    def save_long_term(
        self, house_id: str, baselines: dict[str, ApplianceBaseline]
    ) -> None:
        path = self._long / f"{house_id}.json"
        path.write_text(
            json.dumps(
                {k: _to_dict(v) for k, v in baselines.items()},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def _load_cold_start(self) -> dict[str, ApplianceBaseline]:
        path = self._cold / "baseline.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        result = {}
        for app_name, mode_dict in data.items():
            modes = {}
            for mode_name, mode_data in mode_dict.items():
                if not isinstance(mode_data, dict):
                    continue
                mode_data.pop("tda_reference", None)
                modes[mode_name] = ModeBaseline(**mode_data)
            bl = ApplianceBaseline(appliance=app_name)
            bl.modes = modes
            result[app_name] = bl
        return result
