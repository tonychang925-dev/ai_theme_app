#!/usr/bin/env python3
"""
按日期水位精确增量采集 JYHF top-history。

策略：
- 读取 subject 的本地 history 文件，得到最新 rank_date 水位
- 仅向后翻页直到遇到早于水位的页面
- 仅保留 rank_date >= 水位 的记录，并按 subjectRankId 去重
- 将新增记录合并回本地 *_history.jsonl（倒序）
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

from sync_jyhf_to_local import resolve_token
from theme_collector import APIClient, Config


PROJECT_ROOT = Path(__file__).resolve().parent
HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"
LIST_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按日期水位增量采集 JYHF top-history")
    parser.add_argument("--token", help="JYHF token，可选")
    parser.add_argument("--subjects-file", help="txt/json 文件，每行一个 subject_key；不传则按最新 lists 处理全部")
    parser.add_argument("--batch-id", default=None, help="批次 ID，仅用于日志")
    parser.add_argument("--page-size", type=int, default=20, help="history 接口分页大小")
    parser.add_argument("--max-pages", type=int, default=12, help="每个题材最多抓取多少页")
    return parser.parse_args()


def _to_dt(value: Any) -> datetime | None:
    if value in (None, "", "null"):
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.split("Z")[0], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except Exception:
        return None


def _to_date(value: Any) -> date | None:
    dt = _to_dt(value)
    return dt.date() if dt else None


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


def _history_path(subject_key: str) -> Path:
    return HISTORY_DIR / f"{subject_key}_history.jsonl"


def _read_history(subject_key: str) -> list[dict[str, Any]]:
    path = _history_path(subject_key)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                rows.append(obj)
    return rows


def _latest_rank_date(existing_rows: list[dict[str, Any]]) -> date | None:
    dates = [_to_date(row.get("rankDate")) for row in existing_rows]
    dates = [d for d in dates if d is not None]
    return max(dates) if dates else None


def _row_key(row: dict[str, Any]) -> str:
    rank_id = row.get("subjectRankId")
    if rank_id not in (None, "", "null"):
        return f"id:{rank_id}"
    rank_date = row.get("rankDate") or ""
    create_time = row.get("createTime") or row.get("updateTime") or ""
    description = row.get("description") or ""
    return f"fallback:{rank_date}|{create_time}|{description[:120]}"


def _sort_key(row: dict[str, Any]) -> tuple:
    rank_date = _to_date(row.get("rankDate")) or date.min
    update_dt = _to_dt(row.get("updateTime")) or _to_dt(row.get("createTime")) or datetime.min
    rank_id = int(row.get("subjectRankId") or 0)
    return (rank_date, update_dt, rank_id)


def _merge_rows(existing_rows: list[dict[str, Any]], fetched_rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    merged: dict[str, dict[str, Any]] = {}
    for row in existing_rows:
        merged[_row_key(row)] = row
    before = len(merged)
    for row in fetched_rows:
        merged[_row_key(row)] = row
    merged_rows = sorted(merged.values(), key=_sort_key, reverse=True)
    return merged_rows, len(merged) - before


def _fetch_incremental_rows(
    client: APIClient,
    subject_key: str,
    since_date: date | None,
    page_size: int,
    max_pages: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        params = {"subjectId": subject_key, "pageNum": page, "pageSize": page_size}
        data = client.request("subject/top-history", params, f"history_p{page}")
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break

        keep_rows: list[dict[str, Any]] = []
        hit_older = False
        for row in rows:
            rank_date = _to_date(row.get("rankDate"))
            if since_date and rank_date and rank_date < since_date:
                hit_older = True
                continue
            keep_rows.append(row)

        out.extend(keep_rows)
        if hit_older:
            break
    return out


def _write_history(subject_key: str, rows: list[dict[str, Any]]) -> None:
    path = _history_path(subject_key)
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

    total_new_rows = 0
    touched_subjects = 0
    for idx, subject_key in enumerate(subject_keys, start=1):
        existing_rows = _read_history(subject_key)
        since_date = _latest_rank_date(existing_rows)
        fetched_rows = _fetch_incremental_rows(client, subject_key, since_date, args.page_size, args.max_pages)
        merged_rows, new_rows = _merge_rows(existing_rows, fetched_rows)
        if new_rows > 0:
            _write_history(subject_key, merged_rows)
            touched_subjects += 1
            total_new_rows += new_rows
        print(
            f"[{idx}/{len(subject_keys)}] subject={subject_key} "
            f"since_date={since_date} fetched={len(fetched_rows)} new_rows={new_rows}"
        )

    batch_id = args.batch_id or f"jyhf_history_incremental_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    print(f"[OK] batch_id={batch_id} subjects={len(subject_keys)} touched={touched_subjects} new_rows={total_new_rows}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
