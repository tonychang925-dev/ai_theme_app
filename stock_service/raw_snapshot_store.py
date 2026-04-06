from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class RawSnapshotRecord:
    source_name: str
    dataset_name: str
    trade_date: str
    batch_id: str
    path: Path
    row_count: int


class RawSnapshotStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def write_json_snapshot(
        self,
        *,
        source_name: str,
        dataset_name: str,
        trade_date: str,
        batch_id: str,
        payload: Any,
        metadata: Mapping[str, Any] | None = None,
    ) -> RawSnapshotRecord:
        target_dir = self.root / source_name / dataset_name
        target_dir.mkdir(parents=True, exist_ok=True)
        file_name = f"{trade_date}__{batch_id}.json"
        path = target_dir / file_name

        document = {
            "source_name": source_name,
            "dataset_name": dataset_name,
            "trade_date": trade_date,
            "batch_id": batch_id,
            "metadata": dict(metadata or {}),
            "payload": payload,
        }
        path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")

        if isinstance(payload, list):
            row_count = len(payload)
        elif isinstance(payload, dict):
            row_count = 1
        else:
            row_count = 0

        return RawSnapshotRecord(
            source_name=source_name,
            dataset_name=dataset_name,
            trade_date=trade_date,
            batch_id=batch_id,
            path=path,
            row_count=row_count,
        )

    def find_latest_snapshot_path(
        self,
        *,
        source_name: str,
        dataset_name: str,
        trade_date: str,
    ) -> Path | None:
        target_dir = self.root / source_name / dataset_name
        if not target_dir.exists():
            return None
        matches = sorted(target_dir.glob(f"{trade_date}__*.json"))
        if not matches:
            return None
        return matches[-1]

    def load_json_snapshot(
        self,
        *,
        source_name: str,
        dataset_name: str,
        trade_date: str,
    ) -> dict[str, Any] | None:
        path = self.find_latest_snapshot_path(
            source_name=source_name,
            dataset_name=dataset_name,
            trade_date=trade_date,
        )
        if path is None:
            return None
        return json.loads(path.read_text(encoding="utf-8"))
