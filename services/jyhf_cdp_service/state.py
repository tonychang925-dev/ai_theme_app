from __future__ import annotations

import json
from pathlib import Path

from services.jyhf_cdp_service.schemas import CollectorStatus


class StatusStore:
    def __init__(self, path: Path, cdp_port: int) -> None:
        self._path = path
        self._cdp_port = cdp_port
        self._status = CollectorStatus(cdp_port=cdp_port)

    def get(self) -> CollectorStatus:
        return self._status

    def update(self, **kwargs: object) -> CollectorStatus:
        data = self._status.model_dump()
        data.update(kwargs)
        self._status = CollectorStatus(**data)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(self._status.model_dump_json(indent=2), encoding="utf-8")
        return self._status


class DedupStore:
    def __init__(self, path: Path, max_keys: int = 5000) -> None:
        self._path = path
        self._max_keys = max_keys
        self._keys = self._load()

    def seen(self, key: str) -> bool:
        return key in self._keys

    def mark(self, key: str) -> None:
        self._keys.add(key)
        self.flush()

    def flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(sorted(self._keys)[-self._max_keys:], ensure_ascii=False), encoding="utf-8")

    def _load(self) -> set[str]:
        if not self._path.exists():
            return set()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {str(item) for item in data}
        except Exception:
            return set()
        return set()

