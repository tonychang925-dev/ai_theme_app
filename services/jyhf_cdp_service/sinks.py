from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

from services.jyhf_cdp_service.schemas import RawJyhfCdpEvent


class RawEventJsonlSink:
    def __init__(self, output_dir: Path) -> None:
        self._output_dir = output_dir
        self._lock = RLock()

    def write(self, event: RawJyhfCdpEvent) -> None:
        with self._lock:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            path = self._output_dir / f"new_events_{event.trade_date.replace('-', '')}.jsonl"
            with path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")
