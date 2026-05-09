from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path
from threading import RLock

from services.jyhf_cdp_service.schemas import CollectorStatus


class StatusStore:
    def __init__(self, path: Path, cdp_port: int) -> None:
        self._path = path
        self._cdp_port = cdp_port
        self._status = CollectorStatus(cdp_port=cdp_port)
        self._lock = RLock()

    def get(self) -> CollectorStatus:
        with self._lock:
            return self._status

    def update(self, **kwargs: object) -> CollectorStatus:
        with self._lock:
            data = self._status.model_dump()
            data.update(kwargs)
            self._status = CollectorStatus(**data)
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
            temp_path.write_text(self._status.model_dump_json(indent=2), encoding="utf-8")
            temp_path.replace(self._path)
            return self._status


class DedupStore:
    def __init__(self, path: Path, max_keys: int = 5000) -> None:
        self._path = path
        self._max_keys = max_keys
        self._keys = self._load()
        self._lock = RLock()

    def seen(self, key: str) -> bool:
        with self._lock:
            return key in self._keys

    def mark(self, key: str) -> None:
        with self._lock:
            self._keys[key] = True
            self._keys.move_to_end(key)
            while len(self._keys) > self._max_keys:
                self._keys.popitem(last=False)
            self.flush()

    def flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._path.with_suffix(f"{self._path.suffix}.tmp")
        temp_path.write_text(json.dumps(list(self._keys.keys()), ensure_ascii=False), encoding="utf-8")
        temp_path.replace(self._path)

    def _load(self) -> OrderedDict[str, bool]:
        if not self._path.exists():
            return OrderedDict()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return OrderedDict((str(item), True) for item in data[-self._max_keys:])
            if isinstance(data, dict):
                items = data.get("keys") if isinstance(data.get("keys"), list) else []
                return OrderedDict((str(item), True) for item in items[-self._max_keys:])
        except Exception:
            return OrderedDict()
        return OrderedDict()
