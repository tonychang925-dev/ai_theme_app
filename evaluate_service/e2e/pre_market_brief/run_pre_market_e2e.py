from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.cleanup_e2e_run import cleanup_run
    from evaluate_service.e2e.pre_market_brief.common import (
        default_output_dir,
        ensure_dir,
        require_safe_db,
        write_json,
    )
    from evaluate_service.e2e.pre_market_brief.evaluate_pre_market_brief import evaluate
    from evaluate_service.e2e.pre_market_brief.parse_test_cases import parse_test_cases_file
    from evaluate_service.e2e.pre_market_brief.replay_akshare_raw_news import replay_rows
    from evaluate_service.e2e.pre_market_brief.trace_pre_market_e2e_run import trace_run
else:
    from .cleanup_e2e_run import cleanup_run
    from .common import default_output_dir, ensure_dir, require_safe_db, write_json
    from .evaluate_pre_market_brief import evaluate
    from .parse_test_cases import parse_test_cases_file
    from .replay_akshare_raw_news import replay_rows
    from .trace_pre_market_e2e_run import trace_run


async def run(args: argparse.Namespace) -> dict[str, Any]:
    require_safe_db(args.db_name, allow_production=args.allow_production)
    out_dir = ensure_dir(Path(args.out_dir) if args.out_dir else default_output_dir(args.run_id))

    if args.force_clean:
        cleanup_result = await cleanup_run(
            db_name=args.db_name,
            source=args.source,
            trade_date=args.trade_date,
            run_id=args.run_id,
            dry_run=False,
            delete_final_snapshot=args.delete_final_snapshot,
        )
        write_json(out_dir / "cleanup_result.json", cleanup_result)

    input_rows, gold_rows = parse_test_cases_file(
        Path(args.test_cases),
        run_id=args.run_id,
        trade_date=args.trade_date,
        limit=args.limit,
    )
    input_path = out_dir / "input_news.jsonl"
    gold_path = out_dir / "gold_labels.jsonl"
    from evaluate_service.e2e.pre_market_brief.common import write_jsonl

    write_jsonl(input_path, input_rows)
    write_jsonl(gold_path, gold_rows)

    if args.inject:
        injection_result = await replay_rows(
            input_rows,
            redis_url=args.redis_url,
            stream=args.stream,
            run_id=args.run_id,
            trade_date=args.trade_date,
            limit=args.limit,
        )
        write_json(out_dir / "injection_result.json", injection_result)

    trace = await _wait_for_trace(args, out_dir, input_path) if args.wait else await _trace_once(args, out_dir, input_path)

    snapshot_payload: dict[str, Any] = {}
    if args.rebuild:
        snapshot_payload = _post_json(
            f"{args.sps_base_url.rstrip('/')}/api/v1/pre_market_brief/rebuild",
            _build_rebuild_payload(args),
        )
        write_json(out_dir / "brief_snapshot.json", snapshot_payload)
    else:
        snapshot_payload = _get_json(
            f"{args.sps_base_url.rstrip('/')}/api/v1/pre_market_brief",
            {"trade_date": args.trade_date},
        )
        write_json(out_dir / "brief_snapshot.json", snapshot_payload)

    try:
        bff_payload = _get_json(
            f"{args.bff_base_url.rstrip('/')}/api/v2/pre-market-brief",
            {"trade_date": args.trade_date},
        )
    except Exception as exc:
        bff_payload = {"diagnostics": {"partial": True, "error": str(exc)}}
    write_json(out_dir / "bff_payload.json", bff_payload)

    evaluation: dict[str, Any] = {}
    if args.evaluate:
        evaluation = evaluate(
            gold_path=gold_path,
            trace_path=out_dir / "db_trace_report.json",
            snapshot_path=out_dir / "brief_snapshot.json",
            out_dir=out_dir,
        )

    result = {
        "run_id": args.run_id,
        "trade_date": args.trade_date,
        "out_dir": str(out_dir),
        "trace_counts": trace.get("counts", {}),
        "evaluation": evaluation,
    }
    write_json(out_dir / "run_result.json", result)
    return result


async def _trace_once(args: argparse.Namespace, out_dir: Path, input_path: Path) -> dict[str, Any]:
    trace = await trace_run(
        db_name=args.db_name,
        run_id=args.run_id,
        trade_date=args.trade_date,
        input_path=input_path,
        redis_url=args.redis_url,
        redis_scan_limit=args.redis_scan_limit,
    )
    write_json(out_dir / "db_trace_report.json", trace)
    return trace


async def _wait_for_trace(args: argparse.Namespace, out_dir: Path, input_path: Path) -> dict[str, Any]:
    deadline = time.monotonic() + args.wait_timeout
    expected = args.limit or 0
    last_trace: dict[str, Any] = {}
    while time.monotonic() < deadline:
        last_trace = await _trace_once(args, out_dir, input_path)
        counts = last_trace.get("counts", {})
        news_events = int(counts.get("news_event_count") or 0)
        mapped = int(counts.get("event_theme_map_count") or 0)
        reviewed = int(counts.get("review_queue_count") or 0)
        if expected and news_events >= max(1, int(expected * 0.95)) and (mapped + reviewed) > 0:
            return last_trace
        await asyncio.sleep(args.wait_interval)
    return last_trace


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    full_url = f"{url}?{query}" if query else url
    try:
        with urllib.request.urlopen(full_url, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GET {full_url} failed: {exc.code} {body}") from exc


def _build_rebuild_payload(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "trade_date": args.trade_date,
        "source": "db_first",
        "limit": args.limit or 300,
        "force": bool(args.force_rebuild),
        "dry_run": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="盘前必读 E2E 多题材回放评测总控脚本。")
    parser.add_argument("--test-cases", default="evaluate_service/data/raw/test_cases.txt")
    parser.add_argument("--db-name", default="stock_data")
    parser.add_argument("--trade-date", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--redis-url", default="redis://127.0.0.1:6379/0")
    parser.add_argument("--stream", default="stream:news:raw")
    parser.add_argument("--sps-base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--bff-base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--source", default="akshare_replay")
    parser.add_argument("--out-dir")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force-clean", action="store_true")
    parser.add_argument("--delete-final-snapshot", action="store_true")
    parser.add_argument("--inject", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=180)
    parser.add_argument("--wait-interval", type=int, default=5)
    parser.add_argument("--redis-scan-limit", type=int, default=1000)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(run(args))
    print(result)


if __name__ == "__main__":
    main()
