from __future__ import annotations

import json
from pathlib import Path

from stock_service.adapters.jyhf_adapter import normalize_stock_id


class JyhfUniverseService:
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)

    @property
    def stock_daily_dir(self) -> Path:
        return self.project_root / "theme_data_complete" / "stock_daily"

    @property
    def stock_details_dir(self) -> Path:
        return self.project_root / "theme_data_complete" / "stock_details"

    def collect_stock_ids(
        self,
        *,
        include_stock_daily: bool = True,
        include_stock_details: bool = True,
    ) -> list[str]:
        stock_ids: set[str] = set()
        if include_stock_daily:
            stock_ids.update(self._collect_from_stock_daily())
        if include_stock_details:
            stock_ids.update(self._collect_from_stock_details())
        return sorted(stock_ids)

    def _collect_from_stock_daily(self) -> set[str]:
        results: set[str] = set()
        if not self.stock_daily_dir.exists():
            return results
        for path in self.stock_daily_dir.glob("*_stocks.jsonl"):
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, list) or len(row) < 3:
                        continue
                    stock_id = normalize_stock_id(row[2])
                    if stock_id:
                        results.add(stock_id)
        return results

    def _collect_from_stock_details(self) -> set[str]:
        results: set[str] = set()
        if not self.stock_details_dir.exists():
            return results
        for path in self.stock_details_dir.glob("*_stocks.jsonl"):
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, list) or len(row) < 3:
                        continue
                    stock_id = normalize_stock_id(row[2])
                    if stock_id:
                        results.add(stock_id)
        return results
