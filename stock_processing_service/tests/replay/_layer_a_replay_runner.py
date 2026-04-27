from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from database_service.config import DatabaseConfig, DatabaseType
from database_service.gateway import DatabaseGateway
from stock_processing_service.domain.services.enhanced_mainline_judgement_service import (
    EnhancedMainlineJudgementService,
    MainlineJudgementService,
    ThemeEventStats,
    ThemeMarketStats,
    build_mainline_judgement,
)


# ── JSON encoder for dataclasses / date / Decimal ──

class _ReplayJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        return super().default(obj)


def _to_json_serializable(obj: Any) -> Any:
    """Recursively convert dataclasses / dates / Decimals to JSON-serializable types."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_json_serializable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_serializable(v) for v in obj]
    return obj


# ── Facade adapter (reuses pattern from _post_market_replay_runner.py) ──

class _ReplayDatabaseStockFacade:
    """Runtime facade to adapt DatabaseGateway signatures to stock-processing ports."""

    def __init__(self, gateway: DatabaseGateway) -> None:
        self._gateway = gateway

    async def get_stock_daily_bars(self, trade_date: date, stock_ids=None):
        return await self._gateway.get_stock_daily_bars(trade_date, stock_ids=stock_ids)

    async def get_subject_stock_pool_by_trade_date(self, trade_date: date):
        return await self._gateway.get_subject_stock_pool_by_trade_date(trade_date)

    async def get_subject_context_by_subject_keys(self, subject_keys: list[str], trade_date: date):
        return await self._gateway.get_subject_context_by_subject_keys(subject_keys, trade_date)

    async def get_theme_mainline_judgements(self, trade_date: date) -> list[dict[str, Any]]:
        """Read old chain theme_mainline_judgement rows for comparison."""
        async with self._gateway._client.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM theme_mainline_judgement
                WHERE trade_date = $1::date
                """,
                trade_date,
            )
            return [dict(r) for r in rows]


# ── Replay helpers ──

def replay_enabled() -> bool:
    return os.getenv("RUN_REPLAY_DB", "0") == "1"


async def _get_replay_gateway() -> DatabaseGateway:
    target_db = os.getenv("REPLAY_DB_NAME", "stock_data_test")

    cfg = DatabaseConfig()
    cfg.db_type = DatabaseType.POSTGRESQL
    cfg.postgres_host = os.getenv("PG_HOST", "localhost")
    cfg.postgres_port = int(os.getenv("PG_PORT", "5432"))
    cfg.postgres_database = target_db
    cfg.postgres_username = os.getenv("PG_USERNAME", "postgres")
    cfg.postgres_password = os.getenv("PG_PASSWORD", "")
    cfg.postgres_ssl_mode = os.getenv("PG_SSL_MODE", "prefer")
    cfg.redis.enabled = False
    cfg.cache.enable_cache_warming = False
    cfg.enable_metrics = False
    cfg.enable_health_check = False

    # Force singleton reconnect with explicit replay config.
    old = DatabaseGateway._instance
    if old is not None and getattr(old, "_client", None) is not None:
        try:
            await old._client.close()
        except Exception:
            pass
    DatabaseGateway._instance = None
    DatabaseGateway._client = None
    DatabaseGateway._initialized = False
    return await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)


def _build_theme_event_stats(
    subject_key: str,
    theme_name: str,
    ctx_dto: Any | None,
    diagnostics: dict[str, Any],
) -> ThemeEventStats:
    """
    Build ThemeEventStats from SubjectContextDTO.metadata.

    Mapping (from plan):
      today_event_count  ← metadata["today_event_count"] or 0
      recent_event_count ← metadata["event_count_7d"] or metadata["recent_event_count"] or 0
      distinct_event_days ← metadata["distinct_event_days"] or min(event_recency_days, 7) or 0
      key_event_count    ← metadata["key_event_count"] or count_key_events(sample_summaries)
      sample_summaries   ← metadata["sample_summaries"] or [theme_event_summary] or []
    """
    metadata: dict[str, Any] = getattr(ctx_dto, "metadata", None) or {}
    theme_event_summary: str | None = getattr(ctx_dto, "theme_event_summary", None) or None

    missing_fields: list[str] = []
    data_source = "metadata"

    today_event_count = metadata.get("today_event_count", 0)
    if "today_event_count" not in metadata:
        missing_fields.append("today_event_count")
        data_source = "approximated"

    recent_event_count = metadata.get("event_count_7d") or metadata.get("recent_event_count", 0)
    if "event_count_7d" not in metadata and "recent_event_count" not in metadata:
        missing_fields.append("event_count_7d")
        data_source = "approximated"

    distinct_event_days = metadata.get("distinct_event_days")
    if distinct_event_days is None:
        event_recency_days = metadata.get("event_recency_days", 0)
        distinct_event_days = min(event_recency_days, 7) if event_recency_days else 0
        missing_fields.append("distinct_event_days")
        data_source = "approximated"

    sample_summaries: list[str] = metadata.get("sample_summaries", [])
    if not sample_summaries:
        if theme_event_summary:
            sample_summaries = [theme_event_summary]
        missing_fields.append("sample_summaries")
        data_source = "approximated"

    key_event_count = metadata.get("key_event_count")
    if key_event_count is None:
        key_event_count = MainlineJudgementService.count_key_events(sample_summaries)
        missing_fields.append("key_event_count")
        data_source = "approximated"

    if not metadata:
        data_source = "empty"

    diagnostics["event_stats_source"] = data_source
    if missing_fields:
        diagnostics["missing_metadata_fields"] = missing_fields
    diagnostics["data_quality"] = "full" if data_source == "metadata" else data_source

    return ThemeEventStats(
        subject_key=subject_key,
        theme_name=theme_name,
        today_event_count=int(today_event_count),
        recent_event_count=int(recent_event_count),
        distinct_event_days=int(distinct_event_days),
        key_event_count=int(key_event_count),
        sample_summaries=[str(s)[:200] for s in sample_summaries],
    )


def _build_theme_market_stats(
    subject_key: str,
    theme_name: str,
    pool_rows: list[Any],
    diagnostics: dict[str, Any],
) -> ThemeMarketStats:
    """
    Build ThemeMarketStats from subject_stock_daily_snapshot pool rows.

    Each pool row (raw dict) already has: rank_order, limit_up, pct_chg, is_leader.
    We use these directly instead of joining against stock_daily_bars.

    Mapping (from plan):
      limit_up_count ← count of limit_up = True
      strong_stock_count ← count of pct_chg >= 5.0
      leader_pct_chg ← leader's pct_chg (by rank_order or is_leader)
      member_count ← len(pool_rows)
      leader_limit_up ← leader's limit_up flag
    """
    member_count = len(pool_rows)
    limit_up_count = 0
    strong_stock_count = 0
    leader_pct_chg = 0.0
    leader_limit_up = False
    data_source = "pool_rows"

    def _get(row: Any, key: str, default: Any = None) -> Any:
        """Helper: read key from dict or attribute."""
        if isinstance(row, dict):
            return row.get(key, default)
        return getattr(row, key, default)

    # Find leader: rank_order=1 / pool_rank=1 first, then is_leader=True
    sorted_rows = sorted(
        pool_rows,
        key=lambda r: (
            (_get(r, "rank_order") is None and _get(r, "pool_rank") is None),
            _get(r, "rank_order") or _get(r, "pool_rank") or 9999,
        )
    )
    leader_row = sorted_rows[0] if sorted_rows else None

    for row in pool_rows:
        if _get(row, "limit_up"):
            limit_up_count += 1
        pct = float(_get(row, "pct_chg", 0) or 0)
        if pct >= 5.0:
            strong_stock_count += 1

    # Leader stats
    if leader_row:
        leader_pct_chg = float(_get(leader_row, "pct_chg", 0) or 0)
        leader_limit_up = bool(_get(leader_row, "limit_up", False))
        leader_is_leader = bool(_get(leader_row, "is_leader", False))
        if not leader_row:
            data_source = "partial"
    else:
        data_source = "partial"

    # Diagnose: how many rows missing pct_chg
    missing_pct = sum(1 for r in pool_rows if _get(r, "pct_chg") is None)
    if missing_pct > 0:
        data_source = "partial"

    diagnostics["market_stats_source"] = data_source
    if missing_pct > 0:
        diagnostics["rows_missing_pct_chg"] = missing_pct

    return ThemeMarketStats(
        subject_key=subject_key,
        theme_name=theme_name,
        limit_up_count=limit_up_count,
        strong_stock_count=strong_stock_count,
        leader_pct_chg=round(leader_pct_chg, 2),
        member_count=member_count,
        leader_limit_up=leader_limit_up,
    )


def _compute_diagnostics(
    event_stats: ThemeEventStats,
    market_stats: ThemeMarketStats,
    event_stats_source: str,
    market_stats_source: str,
) -> dict[str, Any]:
    return {
        "event_stats_source": event_stats_source,
        "market_stats_source": market_stats_source,
        "member_count": market_stats.member_count,
        "limit_up_count": market_stats.limit_up_count,
        "today_event_count": event_stats.today_event_count,
        "recent_event_count": event_stats.recent_event_count,
    }


# ── Main replay orchestration ──

async def run_layer_a_replay(
    trade_date: date,
    sample_name: str,
) -> dict[str, Any]:
    """Run Layer A algorithm on all subjects and write replay.json."""
    gateway = await _get_replay_gateway()
    facade = _ReplayDatabaseStockFacade(gateway)

    # 1. Fetch data through StockReadPort methods (3 methods only)
    pool_rows = await facade.get_subject_stock_pool_by_trade_date(trade_date)
    bars = await facade.get_stock_daily_bars(trade_date)

    # Collect unique subject_keys
    subject_keys = list({r['subject_key'] for r in pool_rows})
    ctx_list = await facade.get_subject_context_by_subject_keys(subject_keys, trade_date)
    ctx_by_key = {c['subject_key']: c for c in ctx_list}

    # Build bars index
    bars_by_stock = {b['stock_id']: b for b in bars}

    # Group pool rows by subject_key
    pool_by_subject: dict[str, list[Any]] = defaultdict(list)
    for r in pool_rows:
        pool_by_subject[r['subject_key']].append(r)

    # Build subject_names from context (ctx rows have subject_name; pool rows only have stock_name)
    subject_names: dict[str, str] = {c['subject_key']: c.get('subject_name', '') for c in ctx_list}

    # 2. Run algorithm on each subject_key
    mainline_svc = MainlineJudgementService()
    enhanced_svc = EnhancedMainlineJudgementService()
    results: list[dict[str, Any]] = []

    with_event_stats = 0
    with_market_stats = 0

    for subject_key in subject_keys:
        theme_name = subject_names.get(subject_key, "")
        ctx = ctx_by_key.get(subject_key)
        rows = pool_by_subject.get(subject_key, [])

        diag: dict[str, Any] = {}

        # Build event stats
        event_stats = _build_theme_event_stats(subject_key, theme_name, ctx, diag)
        if diag.get("event_stats_source") != "empty":
            with_event_stats += 1

        # Build market stats
        market_stats = _build_theme_market_stats(subject_key, theme_name, rows, diag)
        with_market_stats += 1

        # Run base judgement
        trade_date_str = trade_date.isoformat()
        base_judgement = mainline_svc.build_judgement(trade_date_str, event_stats, market_stats)

        # Run enhanced judgement
        enhanced_judgement = enhanced_svc.build_enhanced_judgement(trade_date_str, event_stats, market_stats)

        result_entry: dict[str, Any] = {
            "subject_key": subject_key,
            "theme_name": theme_name,
            "base_judgement": _to_json_serializable(base_judgement),
            "enhanced_judgement": _to_json_serializable(enhanced_judgement),
            "diagnostics": diag,
        }
        results.append(result_entry)

    # Sort results by subject_key
    results.sort(key=lambda r: r["subject_key"])

    # 3. Write replay.json
    output_dir = os.path.join("tmp", "layer_a", f"{trade_date.isoformat()}_{sample_name}")
    os.makedirs(output_dir, exist_ok=True)

    replay_doc: dict[str, Any] = {
        "meta": {
            "trade_date": trade_date.isoformat(),
            "sample_name": sample_name,
            "generated_at": datetime.now().isoformat(),
            "subject_count": len(subject_keys),
            "with_event_stats": with_event_stats,
            "with_market_stats": with_market_stats,
        },
        "results": results,
    }

    output_path = os.path.join(output_dir, "replay.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(replay_doc, f, ensure_ascii=False, indent=2, cls=_ReplayJSONEncoder)

    # Print summary
    tier_counts: dict[str, int] = defaultdict(int)
    alive_count = 0
    for r in results:
        tier = r["base_judgement"]["theme_tier"]
        tier_counts[tier] += 1
        trace = r["enhanced_judgement"].get("source_trace", {})
        if trace.get("mainline_alive"):
            alive_count += 1

    print(f"Layer A replay complete: {len(results)} subjects")
    print(f"  Event stats: {with_event_stats} with data, {len(subject_keys) - with_event_stats} empty")
    print(f"  Market stats: {with_market_stats} with data")
    print(f"  Tiers: {dict(tier_counts)}")
    print(f"  Alive: {alive_count}")
    print(f"  Output: {output_path}")

    return replay_doc


async def run_layer_a_compare(
    trade_date: date,
    sample_name: str,
) -> dict[str, Any]:
    """Run replay AND compare against old chain theme_mainline_judgement table."""
    gateway = await _get_replay_gateway()
    facade = _ReplayDatabaseStockFacade(gateway)

    # 1. Run replay first
    replay_doc = await run_layer_a_replay(trade_date, sample_name)

    # 2. Read old chain data
    old_rows = await facade.get_theme_mainline_judgements(trade_date)
    old_by_key: dict[str, dict[str, Any]] = {}
    for row in old_rows:
        key = str(row.get("subject_key", ""))
        if key:
            old_by_key[key] = row

    # 3. Write old_chain.json
    output_dir = os.path.join("tmp", "layer_a", f"{trade_date.isoformat()}_{sample_name}")
    old_chain_doc: dict[str, Any] = {
        "meta": {
            "trade_date": trade_date.isoformat(),
            "sample_name": sample_name,
            "generated_at": datetime.now().isoformat(),
            "row_count": len(old_rows),
        },
        "rows": _to_json_serializable(old_rows),
    }
    old_path = os.path.join(output_dir, "old_chain.json")
    with open(old_path, "w", encoding="utf-8") as f:
        json.dump(old_chain_doc, f, ensure_ascii=False, indent=2)

    # 4. Diff
    results = replay_doc.get("results", [])
    summary = {
        "total_subjects": len(results),
        "matched_in_old_chain": 0,
        "exact_match": 0,
        "approx_match": 0,
        "mismatch": 0,
        "only_in_new": 0,
        "only_in_old": 0,
    }
    field_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"exact": 0, "approx": 0, "mismatch": 0})
    mismatches: list[dict[str, Any]] = []

    # Fields to compare
    compare_fields = [
        ("event_chain_score", 5.0),
        ("event_chain_continuity_score", 5.0),
        ("market_recognition_score", 5.0),
        ("mainline_stability_score", 5.0),
        ("is_main_theme", 0),
        ("theme_tier", 0),
    ]
    enhanced_compare_fields = [
        ("mainline_strength_score", 5.0),
        ("mainline_alive", 0),
    ]

    for r in results:
        sk = r["subject_key"]
        old = old_by_key.get(sk)
        if old is None:
            summary["only_in_new"] += 1
            continue

        summary["matched_in_old_chain"] += 1
        base = r["base_judgement"]
        trace = r["enhanced_judgement"].get("source_trace", {})

        # Compare base fields
        all_match = True
        has_approx = False
        for field_name, tolerance in compare_fields:
            new_val = base.get(field_name)
            # Map field names between schemas
            old_field = field_name
            old_val = old.get(old_field)

            if field_name == "is_main_theme":
                match_type = "exact" if new_val == old_val else "mismatch"
            elif field_name == "theme_tier":
                match_type = "exact" if new_val == old_val else "mismatch"
            else:
                # Numeric comparison
                try:
                    diff = abs(float(new_val) - float(old_val))
                except (TypeError, ValueError):
                    match_type = "mismatch"
                else:
                    if diff <= 0.01:
                        match_type = "exact"
                    elif diff <= tolerance:
                        match_type = "approx"
                        has_approx = True
                    else:
                        match_type = "mismatch"

            field_stats[field_name][match_type] += 1

            if match_type == "mismatch":
                all_match = False
                mismatches.append({
                    "subject_key": sk,
                    "theme_name": r["theme_name"],
                    "field": field_name,
                    "new_value": str(new_val),
                    "old_value": str(old_val),
                    "delta": f"new={new_val} old={old_val}",
                    "root_cause": "requires investigation",
                })

        # Compare enhanced fields (from source_trace in new, from source_trace in old)
        old_trace_raw = old.get("source_trace", {}) or {}
        if isinstance(old_trace_raw, str):
            try:
                old_trace = json.loads(old_trace_raw)
            except json.JSONDecodeError:
                old_trace = {}
        else:
            old_trace = old_trace_raw or {}
        for field_name, tolerance in enhanced_compare_fields:
            new_val = trace.get(field_name)
            old_val = old_trace.get(field_name)
            if new_val is None and old_val is None:
                field_stats[field_name]["exact"] += 1
                continue
            if new_val is None or old_val is None:
                field_stats[field_name]["mismatch"] += 1
                continue

            if field_name == "mainline_alive":
                match_type = "exact" if new_val == old_val else "mismatch"
            else:
                try:
                    diff = abs(float(new_val) - float(old_val))
                except (TypeError, ValueError):
                    match_type = "mismatch"
                else:
                    if diff <= 0.01:
                        match_type = "exact"
                    elif diff <= tolerance:
                        match_type = "approx"
                        has_approx = True
                    else:
                        match_type = "mismatch"

            field_stats[field_name][match_type] += 1

        # Categorize overall match
        if all_match and not has_approx:
            summary["exact_match"] += 1
        elif not any(
            field_stats[f]["mismatch"] > 0
            for f, _ in compare_fields + enhanced_compare_fields
        ):
            summary["approx_match"] += 1
        else:
            summary["mismatch"] += 1

    # Only in old
    for sk in old_by_key:
        if not any(r["subject_key"] == sk for r in results):
            summary["only_in_old"] += 1

    # 5. Write diff.json
    diff_doc: dict[str, Any] = {
        "meta": {
            "trade_date": trade_date.isoformat(),
            "sample_name": sample_name,
            "generated_at": datetime.now().isoformat(),
        },
        "summary": {
            k: v for k, v in summary.items()
        },
        "field_stats": {k: dict(v) for k, v in field_stats.items()},
        "mismatches": mismatches[:200],  # Cap to 200 entries
    }

    diff_path = os.path.join(output_dir, "diff.json")
    with open(diff_path, "w", encoding="utf-8") as f:
        json.dump(diff_doc, f, ensure_ascii=False, indent=2)

    print(f"\nCompare complete:")
    print(f"  Matched in old chain: {summary['matched_in_old_chain']}")
    print(f"  Exact: {summary['exact_match']}, Approx: {summary['approx_match']}, Mismatch: {summary['mismatch']}")
    print(f"  Only in new: {summary['only_in_new']}, Only in old: {summary['only_in_old']}")
    print(f"  Field stats: {json.dumps({k: dict(v) for k, v in field_stats.items()}, indent=4)}")
    print(f"  Diff output: {diff_path}")

    return diff_doc


# ── Validation mode (apples-to-apples algorithm check) ──

def _parse_leader_from_evidence_market(evidence_market: Any) -> dict[str, Any]:
    """Parse leader_pct_chg, member_count, leader_limit_up from evidence_market list."""
    result = {"leader_pct_chg": 0.0, "member_count": 0, "leader_limit_up": False}
    if not evidence_market:
        return result
    if isinstance(evidence_market, str):
        try:
            items = json.loads(evidence_market)
        except (json.JSONDecodeError, TypeError):
            return result
    elif isinstance(evidence_market, list):
        items = evidence_market
    else:
        return result
    for item in items:
        text = str(item)
        m = re.search(r'龙头涨幅\s+([\d.]+)%', text)
        if m:
            result["leader_pct_chg"] = float(m.group(1))
        m = re.search(r'板块联动个股\s+(\d+)', text)
        if m:
            result["member_count"] = int(m.group(1))
        if '龙头涨停' in text:
            result["leader_limit_up"] = True
    return result


def _parse_key_event_count_from_evidence_logic(evidence_logic: Any) -> int:
    """Parse key_event_count from evidence_logic list."""
    if not evidence_logic:
        return 0
    if isinstance(evidence_logic, str):
        try:
            items = json.loads(evidence_logic)
        except (json.JSONDecodeError, TypeError):
            return 0
    elif isinstance(evidence_logic, list):
        items = evidence_logic
    else:
        return 0
    for item in items:
        m = re.search(r'关键事件\s+(\d+)', str(item))
        if m:
            return int(m.group(1))
    return 0


async def run_layer_a_validate(
    trade_date: date,
    sample_name: str,
) -> dict[str, Any]:
    """
    Validate algorithm correctness by feeding old chain INPUTS into new chain algorithm.

    Extracts ThemeEventStats / ThemeMarketStats from old chain source_trace,
    runs the new chain algorithm with those same inputs, and compares the outputs.
    This eliminates data-source differences and tests pure algorithm equivalence.
    """
    gateway = await _get_replay_gateway()
    facade = _ReplayDatabaseStockFacade(gateway)

    old_rows = await facade.get_theme_mainline_judgements(trade_date)

    mainline_svc = MainlineJudgementService()
    enhanced_svc = EnhancedMainlineJudgementService()

    validations: list[dict[str, Any]] = []
    stats = {
        "total": len(old_rows),
        "with_input_data": 0,
        "without_input_data": 0,
        "event_chain_score_exact": 0,
        "event_chain_score_diff": 0,
        "event_chain_continuity_score_exact": 0,
        "event_chain_continuity_score_diff": 0,
        "market_recognition_score_exact": 0,
        "market_recognition_score_approx": 0,
        "market_recognition_score_diff": 0,
        "mainline_stability_score_exact": 0,
        "mainline_stability_score_approx": 0,
        "mainline_stability_score_diff": 0,
        "is_main_theme_exact": 0,
        "is_main_theme_diff": 0,
        "theme_tier_exact": 0,
        "theme_tier_diff": 0,
    }

    for row in old_rows:
        sk = str(row.get("subject_key", ""))
        theme_name = str(row.get("theme_name", ""))

        # Parse source_trace (JSON string in old chain)
        st_raw = row.get("source_trace", {})
        if isinstance(st_raw, str):
            try:
                st = json.loads(st_raw)
            except json.JSONDecodeError:
                st = {}
        else:
            st = st_raw or {}

        # Extract event stats inputs from old chain source_trace
        today_event_count = int(st.get("today_event_count", 0))
        recent_event_count = int(st.get("recent_event_count", 0))
        distinct_event_days = int(st.get("distinct_event_days", 0))
        strong_stock_count_src = int(st.get("strong_stock_count", 0))
        limit_up_count_src = int(st.get("limit_up_count", 0))

        has_input_data = (
            "today_event_count" in st
            or "recent_event_count" in st
            or "distinct_event_days" in st
        )

        if not has_input_data:
            stats["without_input_data"] += 1
            continue

        stats["with_input_data"] += 1

        # ── Parse leader data from evidence_market ──
        evidence_market_raw = row.get("evidence_market", None)
        leader_info = _parse_leader_from_evidence_market(evidence_market_raw)

        # ── Parse key_event_count from evidence_logic ──
        evidence_logic_raw = row.get("evidence_logic", None)
        key_event_count = _parse_key_event_count_from_evidence_logic(evidence_logic_raw)

        # Build ThemeEventStats with old chain's input values
        # All event fields come from source_trace + parsed key_event_count from evidence_logic
        event_stats = ThemeEventStats(
            subject_key=sk,
            theme_name=theme_name,
            today_event_count=today_event_count,
            recent_event_count=recent_event_count,
            distinct_event_days=distinct_event_days,
            key_event_count=key_event_count,
            sample_summaries=[],  # Not reconstructable from old chain data
        )

        # Build ThemeMarketStats from old chain source_trace + parsed evidence_market
        market_stats = ThemeMarketStats(
            subject_key=sk,
            theme_name=theme_name,
            limit_up_count=limit_up_count_src,
            strong_stock_count=strong_stock_count_src,
            leader_pct_chg=leader_info["leader_pct_chg"],
            member_count=leader_info["member_count"],
            leader_limit_up=leader_info["leader_limit_up"],
        )

        # Run new chain algorithms
        trade_date_str = trade_date.isoformat()
        base_judgement = mainline_svc.build_judgement(
            trade_date_str, event_stats, market_stats
        )
        enhanced_judgement = enhanced_svc.build_enhanced_judgement(
            trade_date_str, event_stats, market_stats
        )

        # Old chain scores (from table columns)
        old_scores = {
            "event_chain_score": float(row.get("event_chain_score", 0)),
            "event_chain_continuity_score": float(
                row.get("event_chain_continuity_score", 0)
            ),
            "market_recognition_score": float(
                row.get("market_recognition_score", 0)
            ),
            "mainline_stability_score": float(
                row.get("mainline_stability_score", 0)
            ),
            "is_main_theme": bool(row.get("is_main_theme", False)),
            "theme_tier": str(row.get("theme_tier", "")),
        }

        # Compare
        new_scores = {
            "event_chain_score": base_judgement.event_chain_score,
            "event_chain_continuity_score": base_judgement.event_chain_continuity_score,
            "market_recognition_score": base_judgement.market_recognition_score,
            "mainline_stability_score": base_judgement.mainline_stability_score,
            "is_main_theme": base_judgement.is_main_theme,
            "theme_tier": base_judgement.theme_tier,
        }

        diffs = {}
        for field, old_val in old_scores.items():
            new_val = new_scores[field]
            if field in ("is_main_theme", "theme_tier"):
                match = "exact" if new_val == old_val else "diff"
            else:
                delta = abs(float(new_val) - float(old_val))
                if delta <= 0.01:
                    match = "exact"
                elif delta <= 5.0:
                    match = "approx"
                else:
                    match = "diff"
            diffs[field] = {
                "match": match,
                "new": (
                    str(new_val)
                    if not isinstance(new_val, (int, float))
                    else new_val
                ),
                "old": (
                    str(old_val)
                    if not isinstance(old_val, (int, float))
                    else old_val
                ),
                "delta": (
                    round(float(new_val) - float(old_val), 2)
                    if field not in ("is_main_theme", "theme_tier")
                    else None
                ),
            }

            if match == "exact":
                stats[f"{field}_exact"] += 1
            elif match == "approx":
                stats[f"{field}_approx"] += 1
            elif match == "diff":
                stats[f"{field}_diff"] += 1

        validations.append({
            "subject_key": sk,
            "theme_name": theme_name,
            "inputs": {
                "today_event_count": today_event_count,
                "recent_event_count": recent_event_count,
                "distinct_event_days": distinct_event_days,
                "limit_up_count": limit_up_count_src,
                "strong_stock_count": strong_stock_count_src,
                "note": "inputs from source_trace + parsed from evidence_market/evidence_logic",
            },
            "scores": diffs,
            "all_exact": all(d["match"] == "exact" for d in diffs.values()),
        })

    # Write validation.json
    output_dir = os.path.join(
        "tmp", "layer_a", f"{trade_date.isoformat()}_{sample_name}"
    )
    os.makedirs(output_dir, exist_ok=True)

    valid_doc: dict[str, Any] = {
        "meta": {
            "trade_date": trade_date.isoformat(),
            "sample_name": sample_name,
            "generated_at": datetime.now().isoformat(),
            "description": "Apples-to-apples algorithm validation",
            "missing_inputs": "sample_summaries (not reconstructable from old chain data)",
        },
        "stats": stats,
        "validations": validations,
    }

    output_path = os.path.join(output_dir, "validation.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(valid_doc, f, ensure_ascii=False, indent=2, cls=_ReplayJSONEncoder)

    # Print summary
    n = stats["with_input_data"]
    print(f"Algorithm validation complete: {n} subjects with input data")
    for field in [
        "event_chain_score",
        "event_chain_continuity_score",
        "market_recognition_score",
        "mainline_stability_score",
        "is_main_theme",
        "theme_tier",
    ]:
        exact = stats[f"{field}_exact"]
        approx = stats.get(f"{field}_approx", 0)
        diff = stats[f"{field}_diff"]
        pct = exact / max(n, 1) * 100
        parts = [f"exact={exact} ({pct:.1f}%)"]
        if approx:
            parts.append(f"approx={approx}")
        if diff:
            parts.append(f"diff={diff}")
        print(f"  {field}: {', '.join(parts)}")
    print(f"  Output: {output_path}")

    return valid_doc


# ── CLI ──

def _parse_date(raw: str) -> date:
    return date.fromisoformat(raw)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Layer A replay / compare runner")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD format")
    parser.add_argument("--sample-name", default="baseline", help="Sample name for output directory")
    parser.add_argument(
        "--mode",
        choices=["replay", "compare", "validate"],
        default="replay",
        help="replay: run new chain only; compare: run new + old chain diff; validate: apples-to-apples algorithm check",
    )
    args = parser.parse_args()

    trade_date = _parse_date(args.trade_date)

    if not replay_enabled():
        print("Set RUN_REPLAY_DB=1 to enable replay database access.")
        sys.exit(1)

    if args.mode == "replay":
        asyncio.run(run_layer_a_replay(trade_date, args.sample_name))
    elif args.mode == "compare":
        asyncio.run(run_layer_a_compare(trade_date, args.sample_name))
    else:
        asyncio.run(run_layer_a_validate(trade_date, args.sample_name))
