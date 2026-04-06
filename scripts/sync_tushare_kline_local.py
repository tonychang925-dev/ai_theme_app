from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.adapters.tushare_adapter import TushareAdapter
from stock_service.config import StockServiceConfig
from stock_service.services.daily_snapshot_service import DailySnapshotService
from stock_service.services.jyhf_universe_service import JyhfUniverseService
from stock_service.services.tushare_kline_local_store import TushareKlineLocalStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="下载并保存 Tushare 股票日线到本地标准化 jsonl")
    parser.add_argument("--token", default=os.getenv("TUSHARE_TOKEN", ""), help="Tushare token")
    parser.add_argument("--start-date", default="", help="开始日期 YYYY-MM-DD，默认最近 6 个月")
    parser.add_argument("--end-date", default="", help="结束日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--months", type=int, default=6, help="未显式传 start-date 时的回溯月数")
    parser.add_argument("--from-jyhf-universe", action="store_true", help="从久赢本地股票池抽取下载 universe")
    parser.add_argument("--stock-ids", nargs="*", default=None, help="显式指定股票代码，可带或不带交易所后缀")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 只，便于验证")
    parser.add_argument("--pause-seconds", type=float, default=0.2, help="每只股票之间的节流秒数，默认 0.2")
    parser.add_argument("--rate-limit-sleep", type=float, default=65.0, help="遇到 Tushare 每分钟限频时的等待秒数")
    parser.add_argument("--max-rate-limit-retries", type=int, default=3, help="单只股票遇到限频时的最大重试次数")
    parser.add_argument("--resume", action="store_true", help="启用断点续跑，自动跳过已完成股票")
    parser.add_argument("--skip-existing", action="store_true", help="若本地已存在标准化 K 线文件则跳过")
    parser.add_argument("--progress-file", default="", help="进度文件路径，默认写入 tmp/tushare_kline_sync_progress.json")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT), help="项目根目录")
    return parser


def _resolve_dates(start_date: str, end_date: str, months: int) -> tuple[str, str]:
    end_value = datetime.strptime(end_date, "%Y-%m-%d").date() if end_date else date.today()
    if start_date:
        start_value = datetime.strptime(start_date, "%Y-%m-%d").date()
    else:
        start_value = end_value - timedelta(days=max(months, 1) * 31)
    return start_value.isoformat(), end_value.isoformat()


def _resolve_universe(project_root: Path, explicit_stock_ids: list[str] | None, from_jyhf_universe: bool) -> list[str]:
    if explicit_stock_ids:
        from stock_service.adapters.jyhf_adapter import normalize_stock_id

        return sorted({normalize_stock_id(item) for item in explicit_stock_ids if str(item).strip()})
    if not from_jyhf_universe:
        raise SystemExit("missing universe: pass --stock-ids or enable --from-jyhf-universe")
    service = JyhfUniverseService(project_root)
    return service.collect_stock_ids()


def _default_progress_file(project_root: Path) -> Path:
    return project_root / "tmp" / "tushare_kline_sync_progress.json"


def _load_progress(path: Path) -> dict:
    if not path.exists():
        return {"completed": [], "skipped": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"completed": [], "skipped": []}
    if not isinstance(data, dict):
        return {"completed": [], "skipped": []}
    return {
        "completed": list(data.get("completed") or []),
        "skipped": list(data.get("skipped") or []),
    }


def _write_progress(path: Path, completed: set[str], skipped: set[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "completed": sorted(completed),
                "skipped": sorted(skipped),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    args = build_parser().parse_args()
    if not args.token:
        raise SystemExit("missing token: pass --token or export TUSHARE_TOKEN")

    project_root = Path(args.project_root).resolve()
    start_date, end_date = _resolve_dates(args.start_date, args.end_date, args.months)
    explicit_date_range = bool(args.start_date or args.end_date)
    universe = _resolve_universe(project_root, args.stock_ids, args.from_jyhf_universe)
    if args.limit and args.limit > 0:
        universe = universe[: args.limit]

    config = StockServiceConfig(
        project_root=project_root,
        tushare_token=args.token,
        local_kline_root=project_root / "theme_data_complete" / "_stock_kline",
    )
    adapter = TushareAdapter(args.token)
    normalizer = DailySnapshotService()
    store = TushareKlineLocalStore(config.local_kline_root)
    progress_path = Path(args.progress_file) if args.progress_file else _default_progress_file(project_root)
    progress = (
        {"completed": [], "skipped": []}
        if explicit_date_range
        else (_load_progress(progress_path) if args.resume else {"completed": [], "skipped": []})
    )
    completed = {str(x) for x in progress["completed"]}
    skipped = {str(x) for x in progress["skipped"]}

    processed = 0
    total_rows = 0
    attempted = 0
    sample_paths: list[str] = []
    skipped_rate_limited = 0
    skipped_existing = 0
    for stock_id in universe:
        attempted += 1
        target_path = store.daily_bar_dir / f"{stock_id}.jsonl"
        if args.resume and not explicit_date_range and stock_id in completed:
            continue
        if args.skip_existing and target_path.exists() and not explicit_date_range:
            skipped_existing += 1
            skipped.add(stock_id)
            if args.resume:
                _write_progress(progress_path, completed, skipped)
            continue
        frame = None
        for attempt in range(args.max_rate_limit_retries + 1):
            try:
                frame = adapter.fetch_daily_history(stock_id, start_date, end_date)
                break
            except RuntimeError as exc:
                message = str(exc)
                if "每分钟最多访问该接口500次" not in message:
                    raise
                if attempt >= args.max_rate_limit_retries:
                    skipped_rate_limited += 1
                    skipped.add(stock_id)
                    print(f"[SKIP] stock_id={stock_id} reason=rate_limit_exhausted")
                    frame = None
                    if args.resume:
                        _write_progress(progress_path, completed, skipped)
                    break
                print(
                    f"[WAIT] stock_id={stock_id} reason=rate_limit "
                    f"sleep={args.rate_limit_sleep:.1f}s attempt={attempt + 1}"
                )
                time.sleep(args.rate_limit_sleep)
        if frame is None:
            if args.pause_seconds > 0:
                time.sleep(args.pause_seconds)
            continue
        records = adapter.to_records(frame)
        if not records:
            if args.pause_seconds > 0:
                time.sleep(args.pause_seconds)
            continue
        trade_date_rows = []
        for row in records:
            ts_trade_date = str(row.get("trade_date") or "").strip()
            if not ts_trade_date:
                continue
            if len(ts_trade_date) == 8:
                normalized_trade_date = f"{ts_trade_date[:4]}-{ts_trade_date[4:6]}-{ts_trade_date[6:8]}"
            else:
                normalized_trade_date = ts_trade_date
            trade_date_rows.append(
                {
                    "ts_code": row.get("ts_code") or stock_id,
                    "open": row.get("open"),
                    "high": row.get("high"),
                    "low": row.get("low"),
                    "close": row.get("close"),
                    "pre_close": row.get("pre_close"),
                    "pct_chg": row.get("pct_chg"),
                    "vol": row.get("vol"),
                    "amount": row.get("amount"),
                    "name": row.get("name"),
                    "trade_date": normalized_trade_date,
                }
            )

        grouped: dict[str, list[dict]] = {}
        for row in trade_date_rows:
            grouped.setdefault(row["trade_date"], []).append(row)

        stock_bars = []
        for trade_date in sorted(grouped):
            stock_bars.extend(normalizer.normalize_tushare_daily_rows(grouped[trade_date], trade_date))

        if not stock_bars:
            if explicit_date_range and (attempted <= 5 or attempted % 200 == 0):
                print(f"[MISS] stock_id={stock_id} no_rows_for_range={start_date}..{end_date}")
            continue
        path = store.upsert_stock_bars(stock_id, stock_bars)
        processed += 1
        total_rows += len(stock_bars)
        completed.add(stock_id)
        skipped.discard(stock_id)
        if explicit_date_range and (processed <= 5 or attempted % 200 == 0):
            print(
                f"[SYNC] attempted={attempted}/{len(universe)} stock_id={stock_id} "
                f"rows={len(stock_bars)} file={path.name}"
            )
        if args.resume:
            _write_progress(progress_path, completed, skipped)
        if len(sample_paths) < 5:
            sample_paths.append(str(path))
        if args.pause_seconds > 0:
            time.sleep(args.pause_seconds)

    print(f"[OK] start_date={start_date}")
    print(f"[OK] end_date={end_date}")
    print(f"[OK] universe_size={len(universe)}")
    print(f"[OK] processed={processed}")
    print(f"[OK] total_rows={total_rows}")
    print(f"[OK] skipped_rate_limited={skipped_rate_limited}")
    print(f"[OK] skipped_existing={skipped_existing}")
    if args.resume:
        print(f"[OK] progress_file={progress_path}")
    for path in sample_paths:
        print(f"[FILE] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
