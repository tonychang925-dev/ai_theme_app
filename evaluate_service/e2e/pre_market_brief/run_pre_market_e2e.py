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
        db_connect_kwargs,
        default_output_dir,
        ensure_dir,
        parse_trade_date,
        require_safe_db,
        table_exists,
        write_json,
    )
    from evaluate_service.e2e.pre_market_brief.evaluate_pre_market_brief import evaluate
    from evaluate_service.e2e.pre_market_brief.parse_test_cases import parse_test_cases_file
    from evaluate_service.e2e.pre_market_brief.replay_akshare_raw_news import replay_rows
    from evaluate_service.e2e.pre_market_brief.trace_pre_market_e2e_run import trace_run
else:
    from .cleanup_e2e_run import cleanup_run
    from .common import (
        db_connect_kwargs,
        default_output_dir,
        ensure_dir,
        parse_trade_date,
        require_safe_db,
        table_exists,
        write_json,
    )
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
            clean_trade_date_all_e2e=args.clean_trade_date_all_e2e,
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

    sps_payload = _get_json(
        f"{args.sps_base_url.rstrip('/')}/api/v1/pre_market_brief",
        {"trade_date": args.trade_date},
    )
    write_json(out_dir / "sps_payload.json", sps_payload)
    if not args.rebuild:
        snapshot_payload = sps_payload
        write_json(out_dir / "brief_snapshot.json", snapshot_payload)

    evaluation: dict[str, Any] = {}
    if args.evaluate:
        evaluation = evaluate(
            gold_path=gold_path,
            trace_path=out_dir / "db_trace_report.json",
            snapshot_path=out_dir / "sps_payload.json",
            out_dir=out_dir,
        )
        _append_run_metadata_to_summary(out_dir / "summary.md", args)

    snapshot_copy: dict[str, Any] | None = None
    if args.copy_snapshot_to_db:
        snapshot_copy = await copy_pre_market_snapshot_to_db(
            source_db=args.db_name,
            target_db=args.copy_snapshot_to_db,
            trade_date=args.trade_date,
            run_id=args.run_id,
        )
        write_json(out_dir / "snapshot_copy_result.json", snapshot_copy)

    result = {
        "run_id": args.run_id,
        "trade_date": args.trade_date,
        "out_dir": str(out_dir),
        "sps_base_url": args.sps_base_url.rstrip("/"),
        "trace_counts": trace.get("counts", {}),
        "evaluation": evaluation,
        "snapshot_copy": snapshot_copy,
    }
    write_json(out_dir / "run_result.json", result)
    return result


def _append_run_metadata_to_summary(path: Path, args: argparse.Namespace) -> None:
    if not path.exists():
        return
    lines = [
        "",
        "## Runtime",
        "",
        f"- sps_base_url: {args.sps_base_url.rstrip('/')}",
    ]
    if args.copy_snapshot_to_db:
        lines.append(f"- copied_snapshot_to_db: {args.copy_snapshot_to_db}")
    path.write_text(path.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(lines) + "\n", encoding="utf-8")


async def copy_pre_market_snapshot_to_db(
    *,
    source_db: str,
    target_db: str,
    trade_date: str,
    run_id: str,
) -> dict[str, Any]:
    import asyncpg

    parsed_trade_date = parse_trade_date(trade_date)
    source_conn = await asyncpg.connect(**db_connect_kwargs(source_db))
    target_conn = await asyncpg.connect(**db_connect_kwargs(target_db))
    try:
        if not await table_exists(source_conn, "pre_market_brief_snapshot"):
            raise RuntimeError(f"source database {source_db} missing pre_market_brief_snapshot")
        if not await table_exists(target_conn, "pre_market_brief_snapshot"):
            raise RuntimeError(f"target database {target_db} missing pre_market_brief_snapshot")
        await _ensure_target_snapshot_columns(target_conn)
        conflict_target = await _snapshot_conflict_target(target_conn)

        row = await source_conn.fetchrow(
            """
            SELECT
              trade_date,
              snapshot_version,
              batch_id,
              trace_id,
              source_trace_id,
              payload,
              source_name,
              status,
              generated_at,
              finalized_at,
              updated_at
            FROM pre_market_brief_snapshot
            WHERE trade_date = $1::date
              AND snapshot_version = 'pre_market_brief.v1'
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            parsed_trade_date,
        )
        if not row:
            raise RuntimeError(f"source snapshot missing: db={source_db}, trade_date={trade_date}")

        payload = row["payload"]
        if isinstance(payload, str):
            payload_json = payload
        else:
            payload_json = json.dumps(payload or {}, ensure_ascii=False, default=str)
        source_trace_id = f"e2e_copy:{run_id}:{row['source_trace_id'] or ''}"[:128]
        result = await target_conn.execute(
            f"""
            INSERT INTO pre_market_brief_snapshot (
              trade_date,
              snapshot_version,
              batch_id,
              trace_id,
              source_trace_id,
              payload,
              source_name,
              status,
              generated_at,
              finalized_at,
              updated_at
            ) VALUES (
              $1, $2, $3, $4, $5, $6::jsonb, $7, $8, $9, $10, NOW()
            )
            ON CONFLICT {conflict_target} DO UPDATE SET
              snapshot_version = EXCLUDED.snapshot_version,
              batch_id = EXCLUDED.batch_id,
              trace_id = EXCLUDED.trace_id,
              source_trace_id = EXCLUDED.source_trace_id,
              payload = EXCLUDED.payload,
              source_name = EXCLUDED.source_name,
              status = EXCLUDED.status,
              generated_at = EXCLUDED.generated_at,
              finalized_at = EXCLUDED.finalized_at,
              updated_at = NOW()
            """,
            row["trade_date"],
            row["snapshot_version"],
            f"e2e_copy:{run_id}",
            f"e2e_copy:{run_id}:{row['trace_id'] or ''}",
            source_trace_id,
            payload_json,
            "pre_market_brief_builder_e2e_copy",
            row["status"] or "draft",
            row["generated_at"],
            row["finalized_at"],
        )
        copied = 0 if str(result).endswith(" 0") else 1
        return {
            "source_db": source_db,
            "target_db": target_db,
            "trade_date": trade_date,
            "snapshot_version": row["snapshot_version"],
            "status": row["status"] or "draft",
            "source_trace_id": source_trace_id,
            "copied": copied,
        }
    finally:
        await source_conn.close()
        await target_conn.close()


async def _ensure_target_snapshot_columns(conn: Any) -> None:
    await conn.execute(
        """
        ALTER TABLE pre_market_brief_snapshot
          ADD COLUMN IF NOT EXISTS status varchar(20) NOT NULL DEFAULT 'draft',
          ADD COLUMN IF NOT EXISTS generated_at timestamptz,
          ADD COLUMN IF NOT EXISTS finalized_at timestamptz,
          ADD COLUMN IF NOT EXISTS source_trace_id varchar(100),
          ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now()
        """
    )


async def _snapshot_conflict_target(conn: Any) -> str:
    columns = await conn.fetch(
        """
        SELECT a.attname
        FROM pg_index i
        JOIN pg_attribute a
          ON a.attrelid = i.indrelid
         AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'pre_market_brief_snapshot'::regclass
          AND i.indisprimary
        ORDER BY array_position(i.indkey, a.attnum)
        """
    )
    names = [str(row["attname"]) for row in columns]
    if names == ["trade_date", "snapshot_version"]:
        return "(trade_date, snapshot_version)"
    if names == ["trade_date"]:
        return "(trade_date)"
    raise RuntimeError(f"unsupported pre_market_brief_snapshot primary key: {names}")


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
        mapped_events = int(counts.get("mapped_event_count") or 0)
        mapped = int(counts.get("event_subject_map_count") or counts.get("event_theme_map_count") or 0)
        reviewed = int(counts.get("review_queue_count") or 0)
        expected_ready = max(1, int(expected * 0.95))
        if expected and news_events >= expected_ready and (mapped_events + reviewed) >= expected_ready and (mapped + reviewed) > 0:
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
    parser.add_argument("--source", default="akshare_replay")
    parser.add_argument("--out-dir")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--force-clean", action="store_true")
    parser.add_argument("--delete-final-snapshot", action="store_true")
    parser.add_argument(
        "--clean-trade-date-all-e2e",
        action="store_true",
        help="配合 --force-clean 使用：清理该 trade_date 下全部 akshare_replay E2E 数据，避免旧 run 污染报告。",
    )
    parser.add_argument("--inject", action="store_true")
    parser.add_argument("--wait", action="store_true")
    parser.add_argument("--wait-timeout", type=int, default=180)
    parser.add_argument("--wait-interval", type=int, default=5)
    parser.add_argument("--redis-scan-limit", type=int, default=1000)
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--force-rebuild", action="store_true")
    parser.add_argument("--evaluate", action="store_true")
    parser.add_argument(
        "--copy-snapshot-to-db",
        help="可选：将最终 pre_market_brief_snapshot 从 E2E 写库复制到指定数据库，例如 stock_data_test。",
    )
    parser.add_argument("--allow-production", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    result = asyncio.run(run(args))
    print(result)


if __name__ == "__main__":
    main()
