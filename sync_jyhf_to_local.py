#!/usr/bin/env python3
"""
久赢恒丰统一采集入口。

职责：
- 从远端 API 抓取指定题材数据到本地 theme_data_complete
- 生成批次 manifest
- 不直接写数据库
- 支持从 mitmproxy 捕获文件自动读取 Authorization 令牌
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from theme_collector import APIClient, Config, DataCollector, ThemeDiscovery  # noqa: E402


MANIFEST_DIR = PROJECT_ROOT / "theme_data_complete" / "_manifests"
STATE_DIR = PROJECT_ROOT / "theme_data_complete" / "_state"
CURSOR_FILE = STATE_DIR / "sync_cursor.json"
LIST_FILE = PROJECT_ROOT / "theme_data_complete" / "lists" / "full_theme_list.sync.jsonl"
LIST_WHITELIST = {"full_theme_list.sync.jsonl", "theme_hierarchy.jsonl"}
TOKEN_FILE = Path("/tmp/jyhf_auth_token.json")   # mitmproxy 插件写入的令牌文件


def ensure_meta_dirs() -> None:
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)


def resolve_token(cli_token: Optional[str]) -> str:
    """按优先级获取 token：命令行 -> 环境变量 -> mitmproxy 捕获文件"""
    if cli_token:
        return cli_token.strip()

    env_token = (os.getenv("JYHF_AUTH_TOKEN") or os.getenv("AUTHORIZATION") or "").strip()
    if env_token:
        return env_token

    # 从 mitmproxy 插件写入的文件读取
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                token = data.get("token", "").strip()
                if token:
                    print(f"[INFO] Loaded token from {TOKEN_FILE}")
                    return token
        except Exception as e:
            print(f"[WARN] Failed to read {TOKEN_FILE}: {e}")

    return ""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def normalize_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return (PROJECT_ROOT / path).resolve()


def collect_subject_files(subject_key: str) -> List[Dict]:
    subject_key = str(subject_key)
    candidates: List[Path] = []
    candidates.extend((Config.DETAILS_DIR).glob(f"{subject_key}_details.jsonl"))
    candidates.extend((Config.HISTORY_DIR).glob(f"{subject_key}_history.jsonl"))
    candidates.extend((Config.DAILY_DIR).glob(f"{subject_key}_daily.jsonl"))
    candidates.extend((Config.CHILDREN_DIR).glob(f"{subject_key}_children.jsonl"))
    candidates.extend((Config.STOCKS_DIR).glob(f"{subject_key}_*_stocks.jsonl"))
    candidates.extend((PROJECT_ROOT / "theme_data_complete" / "stock_daily").glob(f"{subject_key}_*_stocks.jsonl"))
    rows = []
    for path in candidates:
        path = normalize_path(path)
        data_type = "unknown"
        name = path.name
        if "_details" in name:
            data_type = "details"
        elif "_history" in name:
            data_type = "history"
        elif "_daily" in name:
            data_type = "daily"
        elif "_children" in name:
            data_type = "children"
        elif "_stocks" in name:
            data_type = "stock_daily" if "stock_daily" in str(path.parent) else "stock_details"
        rows.append(
            {
                "file_path": str(path.relative_to(PROJECT_ROOT)),
                "data_type": data_type,
                "subject_key": subject_key,
                "file_hash": sha256_file(path),
                "file_size": path.stat().st_size,
                "source_updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
        )
    return rows


def collect_list_files() -> List[Dict]:
    rows = []
    for path in Config.LISTS_DIR.glob("*.jsonl"):
        path = normalize_path(path)
        if path.name not in LIST_WHITELIST:
            continue
        rows.append(
            {
                "file_path": str(path.relative_to(PROJECT_ROOT)),
                "data_type": "lists",
                "subject_key": None,
                "file_hash": sha256_file(path),
                "file_size": path.stat().st_size,
                "source_updated_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
        )
    return rows


def save_manifest(manifest: Dict) -> Path:
    ensure_meta_dirs()
    out = MANIFEST_DIR / f"{manifest['batch_id']}.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def save_cursor_snapshot(manifest: Dict) -> None:
    ensure_meta_dirs()
    snapshot = {
        "last_batch_id": manifest["batch_id"],
        "updated_at": datetime.now().isoformat(),
        "files": {
            row["file_path"]: {
                "file_hash": row["file_hash"],
                "data_type": row["data_type"],
                "subject_key": row["subject_key"],
            }
            for row in manifest["files"]
        },
    }
    CURSOR_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] cursor={CURSOR_FILE}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="久赢恒丰统一采集入口")
    parser.add_argument("--token", help="久赢 token；默认读取 JYHF_AUTH_TOKEN/AUTHORIZATION 或 mitmproxy 捕获文件")
    parser.add_argument("--batch-id", help="同步批次 ID")
    parser.add_argument("--subject", action="append", help="指定单个 subject_id，可重复")
    parser.add_argument("--subjects-file", help="包含 subject_id 列表的 json/txt 文件")
    parser.add_argument("--full", action="store_true", help="显式执行全量采集；否则默认只做 lists 或指定 subject 的增量采集")
    parser.add_argument("--use-latest-list-subjects", action="store_true", help="从最新 full_theme_list.sync.jsonl 加载全部当前题材")
    parser.add_argument("--limit", type=int, default=0, help="从远端发现后只采集前 N 个")
    parser.add_argument("--types", default="", help="采集类型，逗号分隔；默认会根据模式自动决定")
    parser.add_argument("--history-mode", choices=("full", "incremental"), default="full", help="history 采集模式")
    parser.add_argument("--history-page-size", type=int, default=20, help="history 分页大小")
    parser.add_argument("--history-max-pages", type=int, default=12, help="history 最多抓取页数")
    parser.add_argument("--history-backfill-date", help="按指定日期回补全局 history(type=3)，格式 YYYY-MM-DD")
    parser.add_argument("--trade-date", help="stock_details 采集交易日，默认今天")
    parser.add_argument("--resume", action="store_true", help="启用断点续跑，当前用于配合 --skip-existing")
    parser.add_argument("--skip-existing", action="store_true", help="stock_details 文件已存在时直接跳过")
    parser.add_argument("--write-cursor", action="store_true", help="采集后更新本地 cursor 快照")
    return parser.parse_args()


def load_subjects(args: argparse.Namespace, discovery: ThemeDiscovery) -> List[int]:
    subjects: List[int] = []
    if args.subject:
        subjects.extend(int(x) for x in args.subject)
    if args.subjects_file:
        path = Path(args.subjects_file)
        if path.suffix.lower() == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            subjects.extend(int(x) for x in data)
        else:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line:
                    subjects.append(int(line))
    if not subjects and args.use_latest_list_subjects and LIST_FILE.exists():
        with LIST_FILE.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                subject_id = obj.get("subjectId") or obj.get("id") or obj.get("bizKey")
                if subject_id not in (None, ""):
                    subjects.append(int(subject_id))
    if not subjects and args.full:
        subjects = discovery.discover_from_api()
    if args.limit and args.limit > 0:
        subjects = subjects[: args.limit]
    return sorted(set(subjects))


def resolve_wanted_types(args: argparse.Namespace, explicit_subjects: bool) -> set[str]:
    if args.types.strip():
        return {x.strip() for x in args.types.split(",") if x.strip()}
    if args.full or explicit_subjects:
        return {"lists", "details", "history", "children", "daily", "stock_details"}
    return {"lists"}


def fetch_and_save_lists(client: APIClient) -> Optional[Path]:
    data = client.request("subject/list", {"pageNum": 1, "pageSize": 1000}, "lists")
    if not data:
        return None
    Config.LISTS_DIR.mkdir(parents=True, exist_ok=True)
    out = Config.LISTS_DIR / "full_theme_list.sync.jsonl"
    DataCollector(client).save_jsonl(data, out, "题材列表")
    return out


def _to_dt(value: Any) -> Optional[datetime]:
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


def _to_date(value: Any) -> Optional[date]:
    dt = _to_dt(value)
    return dt.date() if dt else None


def _history_path(subject_key: str) -> Path:
    return Config.HISTORY_DIR / f"{subject_key}_history.jsonl"


def _read_history_rows(subject_key: int) -> List[Dict]:
    path = _history_path(str(subject_key))
    if not path.exists():
        return []
    rows: List[Dict] = []
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


def _history_row_key(row: Dict) -> str:
    rank_id = row.get("subjectRankId")
    if rank_id not in (None, "", "null"):
        return f"id:{rank_id}"
    rank_date = row.get("rankDate") or ""
    create_time = row.get("createTime") or row.get("updateTime") or ""
    description = row.get("description") or ""
    return f"fallback:{rank_date}|{create_time}|{description[:120]}"


def _history_sort_key(row: Dict) -> tuple:
    rank_date = _to_date(row.get("rankDate")) or date.min
    update_dt = _to_dt(row.get("updateTime")) or _to_dt(row.get("createTime")) or datetime.min
    rank_id = int(row.get("subjectRankId") or 0)
    return (rank_date, update_dt, rank_id)


def _history_event_dt(row: Dict) -> Optional[datetime]:
    return _to_dt(row.get("createTime")) or _to_dt(row.get("updateTime")) or _to_dt(row.get("rankDate"))


def _response_rows(data: Any) -> List[Dict]:
    if isinstance(data, dict):
        if isinstance(data.get("rows"), list):
            return data["rows"]
        if isinstance(data.get("data"), list):
            return data["data"]
    return []


def collect_history_incremental(
    collector: DataCollector,
    theme_id: int,
    page_size: int,
    max_pages: int,
) -> int:
    existing_rows = _read_history_rows(theme_id)
    existing_event_dts = [_history_event_dt(row) for row in existing_rows]
    since_dt = max((dt for dt in existing_event_dts if dt is not None), default=None)

    fetched_rows: List[Dict] = []
    for page in range(1, max_pages + 1):
        params = {"subjectId": theme_id, "pageNum": page, "pageSize": page_size}
        data = collector.client.request("subject/top-history", params, f"history_p{page}")
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break
        page_hit_older = False
        for row in rows:
            event_dt = _history_event_dt(row)
            if since_dt and event_dt and event_dt <= since_dt:
                page_hit_older = True
                continue
            fetched_rows.append(row)
        if page_hit_older:
            break

    merged: Dict[str, Dict] = {}
    for row in existing_rows:
        merged[_history_row_key(row)] = row
    before = len(merged)
    for row in fetched_rows:
        merged[_history_row_key(row)] = row
    merged_rows = sorted(merged.values(), key=_history_sort_key, reverse=True)

    if len(merged) > before:
        collector.save_jsonl({"data": merged_rows}, _history_path(str(theme_id)), "历史事件")
    print(
        f"  history_mode=incremental since_event_time={since_dt} "
        f"fetched={len(fetched_rows)} new_rows={len(merged) - before}"
    )
    return len(merged) - before


def collect_history_backfill_for_theme(
    collector: DataCollector,
    theme_id: int,
    target_date: str,
    page_size: int,
    max_pages: int,
) -> int:
    backfill_date = _to_date(target_date)
    if backfill_date is None:
        print(f"  [WARN] invalid history backfill date: {target_date}")
        return 0

    existing_rows = _read_history_rows(theme_id)
    merged: Dict[str, Dict] = {_history_row_key(row): row for row in existing_rows}
    before = len(merged)
    fetched_rows: List[Dict] = []

    for page in range(1, max_pages + 1):
        params = {"subjectId": theme_id, "pageNum": page, "pageSize": page_size}
        data = collector.client.request("subject/top-history", params, f"history_backfill_p{page}")
        rows = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rows, list) or not rows:
            break

        page_hit_older = False
        for row in rows:
            event_dt = _history_event_dt(row)
            event_date = event_dt.date() if event_dt else None
            if event_date is None:
                continue
            if event_date > backfill_date:
                continue
            if event_date < backfill_date:
                page_hit_older = True
                continue
            fetched_rows.append(row)
        if page_hit_older:
            break

    for row in fetched_rows:
        merged[_history_row_key(row)] = row
    merged_rows = sorted(merged.values(), key=_history_sort_key, reverse=True)

    if len(merged) > before:
        collector.save_jsonl({"data": merged_rows}, _history_path(str(theme_id)), f"历史事件回补{backfill_date}")
    print(
        f"  history_mode=backfill target_date={backfill_date} "
        f"fetched={len(fetched_rows)} new_rows={len(merged) - before}"
    )
    return len(merged) - before


def collect_history_incremental_global(
    collector: DataCollector,
    subject_ids: Optional[List[int]],
    page_size: int,
    max_pages: int,
    backfill_date: Optional[str] = None,
) -> int:
    allowed_subjects = {str(x) for x in subject_ids} if subject_ids else None
    target_backfill_date = _to_date(backfill_date) if backfill_date else None

    existing_by_subject: Dict[str, Dict[str, Dict]] = {}
    global_since_dt: Optional[datetime] = None

    history_files = (
        [_history_path(str(x)) for x in subject_ids]
        if subject_ids
        else sorted(Config.HISTORY_DIR.glob("*_history.jsonl"))
    )
    for path in history_files:
        subject_key = path.stem.replace("_history", "")
        rows = _read_history_rows(int(subject_key)) if subject_key.isdigit() else []
        merged = {_history_row_key(row): row for row in rows}
        existing_by_subject[subject_key] = merged
        for row in rows:
            event_dt = _history_event_dt(row)
            if event_dt and (global_since_dt is None or event_dt > global_since_dt):
                global_since_dt = event_dt

    fetched_rows = 0
    inserted_rows = 0
    touched_subjects: set[str] = set()

    for page in range(1, max_pages + 1):
        params = {"type": 3, "pageNum": page, "pageSize": page_size}
        data = collector.client.request("subject/top-history", params, f"history_global_p{page}")
        rows = _response_rows(data)
        if not rows:
            break

        page_hit_older = False
        for row in rows:
            subject_key = str(row.get("subjectId") or "").strip()
            if not subject_key:
                continue
            if allowed_subjects is not None and subject_key not in allowed_subjects:
                continue

            event_dt = _history_event_dt(row)
            event_date = event_dt.date() if event_dt else None
            if target_backfill_date:
                if event_date is None:
                    continue
                if event_date > target_backfill_date:
                    continue
                if event_date < target_backfill_date:
                    page_hit_older = True
                    continue
            else:
                if global_since_dt and event_dt and event_dt <= global_since_dt:
                    page_hit_older = True
                    continue

            fetched_rows += 1
            bucket = existing_by_subject.setdefault(subject_key, {})
            row_key = _history_row_key(row)
            if row_key not in bucket:
                inserted_rows += 1
            bucket[row_key] = row
            touched_subjects.add(subject_key)

        if page_hit_older:
            break

    for subject_key in sorted(touched_subjects):
        merged_rows = sorted(existing_by_subject[subject_key].values(), key=_history_sort_key, reverse=True)
        collector.save_jsonl({"data": merged_rows}, _history_path(subject_key), "历史事件")

    print(
        f"[history_global] mode={'backfill' if target_backfill_date else 'incremental'} "
        f"since_event_time={global_since_dt} backfill_date={target_backfill_date} "
        f"fetched={fetched_rows} new_rows={inserted_rows} touched_subjects={len(touched_subjects)}"
    )
    return inserted_rows


def collect_stocks_for_trade_date(
    collector: DataCollector,
    theme_id: int,
    trade_date: Optional[str],
    *,
    skip_existing: bool = False,
) -> int:
    actual_trade_date = trade_date or datetime.now().strftime("%Y-%m-%d")
    stock_daily_dir = PROJECT_ROOT / "theme_data_complete" / "stock_daily"
    stock_daily_dir.mkdir(parents=True, exist_ok=True)
    out = stock_daily_dir / f"{theme_id}_{actual_trade_date}_stocks.jsonl"
    if skip_existing and out.exists():
        print(f"[SKIP] subject={theme_id} reason=existing_stock_snapshot file={out.name}")
        return -1
    data = collector.collect_stocks(theme_id, trade_date)
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        return 0
    collector.save_jsonl(rows, out, f"股票日快照{actual_trade_date}")
    return len(rows)


def main() -> int:
    args = parse_args()
    token = resolve_token(args.token)
    if not token:
        print("[ERROR] missing token: set token via --token, env, or ensure mitmproxy capture file exists")
        return 1

    Config.AUTH_TOKEN = token
    Config.STOCKS_DIR = Config.OUTPUT_DIR / "stock_details"
    Config.init_dirs()

    batch_id = args.batch_id or datetime.now().strftime("jyhf_%Y%m%d%H%M%S")

    client = APIClient(token)
    collector = DataCollector(client)
    discovery = ThemeDiscovery(client)
    explicit_subjects = bool(args.subject or args.subjects_file or args.use_latest_list_subjects)
    wanted_types = resolve_wanted_types(args, explicit_subjects)
    subject_ids = load_subjects(args, discovery)

    if not subject_ids and wanted_types != {"lists"}:
        print("[ERROR] no subjects discovered")
        return 1

    list_path = None
    if "lists" in wanted_types:
        list_path = fetch_and_save_lists(client)

    history_handled_globally = False
    if "history" in wanted_types and args.history_mode == "incremental":
        collect_history_incremental_global(
            collector,
            subject_ids if subject_ids else None,
            page_size=args.history_page_size,
            max_pages=args.history_max_pages,
            backfill_date=args.history_backfill_date,
        )
        history_handled_globally = not bool(args.history_backfill_date)

    files: List[Dict] = []
    for idx, subject_id in enumerate(subject_ids, 1):
        print(f"[{idx}/{len(subject_ids)}] collecting subject={subject_id}")
        if "details" in wanted_types:
            collector.collect_details(subject_id)
        if "history" in wanted_types:
            if history_handled_globally:
                pass
            elif args.history_mode == "incremental":
                if args.history_backfill_date:
                    collect_history_backfill_for_theme(
                        collector,
                        subject_id,
                        target_date=args.history_backfill_date,
                        page_size=args.history_page_size,
                        max_pages=args.history_max_pages,
                    )
                else:
                    collect_history_incremental(
                        collector,
                        subject_id,
                        page_size=args.history_page_size,
                        max_pages=args.history_max_pages,
                    )
            else:
                collector.collect_history(subject_id)
        if "daily" in wanted_types:
            collector.collect_daily(subject_id, Config.DAILY_DAYS)
        if "children" in wanted_types:
            collector.collect_children(subject_id)
        if "stock_details" in wanted_types:
            collect_stocks_for_trade_date(
                collector,
                subject_id,
                args.trade_date,
                skip_existing=args.skip_existing,
            )
        files.extend(collect_subject_files(str(subject_id)))

    if list_path:
        files.extend(collect_list_files())

    manifest = {
        "batch_id": batch_id,
        "started_at": datetime.now().isoformat(),
        "source": "jyhf",
        "subject_count": len(subject_ids),
        "subjects": [str(x) for x in subject_ids],
        "sync_mode": "full" if args.full else ("subjects" if explicit_subjects else "lists_only"),
        "wanted_types": sorted(wanted_types),
        "files": files,
        "stats": client.stats,
    }
    manifest_path = save_manifest(manifest)
    print(f"[OK] manifest={manifest_path}")
    if args.write_cursor:
        save_cursor_snapshot(manifest)

    print(f"[OK] batch_id={batch_id}")
    print(f"[OK] subject_count={len(subject_ids)} file_count={len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
