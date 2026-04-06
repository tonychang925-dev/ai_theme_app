#!/usr/bin/env python3
"""
按交易日精确采集 JYHF 题材股票池快照。

输出：
- theme_data_complete/stock_daily/<subject_key>_<trade_date>_stocks.jsonl
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from sync_jyhf_to_local import resolve_token
from theme_collector import APIClient, Config


PROJECT_ROOT = Path(__file__).resolve().parent
LIST_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
STOCK_DAILY_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
LEGACY_STOCK_DIR = PROJECT_ROOT / "theme_data_complete" / "stock_details"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按交易日采集 JYHF 题材股票池快照")
    parser.add_argument("--token", help="JYHF token，可选")
    parser.add_argument("--subjects-file", help="txt/json 文件，每行一个 subject_key；不传则按最新 lists 处理全部")
    parser.add_argument("--trade-date", default=datetime.now().strftime("%Y-%m-%d"), help="交易日，格式 YYYY-MM-DD")
    parser.add_argument("--batch-id", default=None, help="批次 ID，仅用于日志")
    return parser.parse_args()


def _load_subject_keys(subjects_file: str | None) -> list[str]:
    if subjects_file:
        content = Path(subjects_file).read_text(encoding="utf-8").strip()
        if not content:
            return []
        if subjects_file.endswith(".json"):
            return sorted({str(x) for x in json.loads(content)})
        return sorted({line.strip() for line in content.splitlines() if line.strip()})

    subject_keys: set[str] = set()
    if LIST_FILE.exists():
        with LIST_FILE.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                sid = obj.get("subjectId") or obj.get("id") or obj.get("bizKey")
                if sid not in (None, ""):
                    subject_keys.add(str(sid))
    return sorted(subject_keys)


def _save_rows(path: Path, rows: list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    args = parse_args()
    token = resolve_token(args.token)
    if not token:
        print("[ERROR] missing token")
        return 1

    Config.AUTH_TOKEN = token
    Config.init_dirs()
    client = APIClient(token)
    subject_keys = _load_subject_keys(args.subjects_file)
    if not subject_keys:
        print("[ERROR] no subject keys found")
        return 1

    STOCK_DAILY_DIR.mkdir(parents=True, exist_ok=True)
    touched = 0
    total_rows = 0
    for idx, subject_key in enumerate(subject_keys, start=1):
        params = {
            "sort": "pctChg",
            "sortType": "desc",
            "date": args.trade_date,
            "subjectId": subject_key,
            "start": 0,
            "end": 1200,
        }
        data = client.request("stock/realtime-by-subject/v2", params, f"stocks_{args.trade_date}")
        rows = data.get("rows") if isinstance(data, dict) else None
        if isinstance(rows, list) and rows:
            out_path = STOCK_DAILY_DIR / f"{subject_key}_{args.trade_date}_stocks.jsonl"
            _save_rows(out_path, rows)
            legacy_month = args.trade_date[:7]
            legacy_path = LEGACY_STOCK_DIR / f"{subject_key}_{legacy_month}_stocks.jsonl"
            _save_rows(legacy_path, rows)
            touched += 1
            total_rows += len(rows)
            print(f"[{idx}/{len(subject_keys)}] subject={subject_key} rows={len(rows)} file={out_path.name}")
        else:
            print(f"[{idx}/{len(subject_keys)}] subject={subject_key} rows=0")

    batch_id = args.batch_id or f"jyhf_stock_daily_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"[OK] batch_id={batch_id} trade_date={args.trade_date} touched={touched} rows={total_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
