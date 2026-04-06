from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from stock_service.models import StockDailySnapshot


class TushareKlineLocalStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    @property
    def daily_bar_dir(self) -> Path:
        return self.root / "tushare" / "daily_bar"

    def upsert_stock_bars(
        self,
        stock_id: str,
        bars: Iterable[StockDailySnapshot],
    ) -> Path:
        target_dir = self.daily_bar_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / f"{stock_id}.jsonl"

        merged: dict[str, dict] = {}
        if path.exists():
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    trade_date = str(row.get("trade_date") or "")
                    if trade_date:
                        merged[trade_date] = row

        for bar in bars:
            merged[bar.trade_date] = asdict(bar)

        ordered = [merged[key] for key in sorted(merged)]
        with path.open("w", encoding="utf-8") as handle:
            for row in ordered:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return path
