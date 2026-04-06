from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable


def normalize_stock_id(raw_stock_id: str) -> str:
    value = str(raw_stock_id).strip()
    if "." in value:
        return value.upper()
    if value.startswith(("60", "68", "90")):
        return f"{value}.SH"
    if value.startswith(("00", "30")):
        return f"{value}.SZ"
    if value.startswith(("43", "83", "87", "92")):
        return f"{value}.BJ"
    return value


def _to_float(value):
    if value in (None, "", "null"):
        return None
    try:
        return float(value)
    except Exception:
        return None


class JyhfAdapter:
    """Thin placeholder to mark JYHF as theme/intel source in stock_service skeleton."""

    def __init__(self, project_root: Path):
        self.project_root = project_root

    @property
    def history_dir(self) -> Path:
        return self.project_root / "theme_data_complete" / "history"

    @property
    def stock_daily_dir(self) -> Path:
        return self.project_root / "theme_data_complete" / "stock_daily"

    @staticmethod
    def _extract_subject_name(row: list, subject_key: str):
        for idx in (15, 16):
            if len(row) <= idx:
                continue
            value = row[idx]
            if not isinstance(value, list):
                continue
            for item in value:
                if (
                    isinstance(item, list)
                    and len(item) >= 2
                    and str(item[0]) == str(subject_key)
                ):
                    return item[1]
            if value and isinstance(value[0], list) and len(value[0]) >= 2:
                return value[0][1]
        return None

    def iter_stock_daily_rows(self, trade_date: str, subject_keys: Iterable[str] | None = None):
        wanted = {str(x) for x in subject_keys} if subject_keys is not None else None
        for path in sorted(self.stock_daily_dir.glob(f"*_{trade_date}_stocks.jsonl")):
            subject_key = path.name.split("_")[0]
            if wanted is not None and subject_key not in wanted:
                continue
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for idx, line in enumerate(handle, start=1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(row, list) or len(row) < 4:
                        continue
                    subject_name = self._extract_subject_name(row, subject_key)
                    yield {
                        "trade_date": trade_date,
                        "subject_key": subject_key,
                        "subject_name": subject_name,
                        "selected_id": row[1] if len(row) > 1 else None,
                        "stock_id": normalize_stock_id(row[2]) if len(row) > 2 else None,
                        "stock_name": row[3] if len(row) > 3 else None,
                        "close_price": _to_float(row[4] if len(row) > 4 else None),
                        "open_price": _to_float(row[6] if len(row) > 6 else None),
                        "high_price": _to_float(row[7] if len(row) > 7 else None),
                        "low_price": _to_float(row[8] if len(row) > 8 else None),
                        "pre_close": _to_float(row[9] if len(row) > 9 else None),
                        "pct_chg": _to_float(row[10] if len(row) > 10 else None),
                        "volume": _to_float(row[12] if len(row) > 12 else None),
                        "amount": _to_float(row[13] if len(row) > 13 else None),
                        "rank_order": idx,
                        "is_leader": idx == 1,
                        "raw_row": row,
                    }
