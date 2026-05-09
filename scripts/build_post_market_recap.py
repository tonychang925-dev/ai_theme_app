#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

import asyncpg

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database_service.scripts.build_stock_abnormal_signal import (
    _canonical_stock_id,
    load_current_inputs,
)
from stock_service.config import StockServiceConfig
from stock_service.repositories.report_repository import ReportRepository
from stock_service.services.recap_service import RecapService
from stock_service.services.stock_abnormal_signal_service import (
    StockAbnormalSignalService,
)
from stock_service.services.tushare_auction_snapshot_service import (
    TushareAuctionSnapshotService,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="统一执行盘后复盘第2阶段：基于已采集数据构建真源、生成快照与 fallback 异动清单")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--postgres-database", default="stock_data_test", help="目标数据库名")
    parser.add_argument("--token", default="", help="可选：Tushare token，用于龙虎榜/尾盘竞价刷新")
    parser.add_argument("--batch-id", default="", help="可选：固定快照批次号")
    parser.add_argument("--top-k", type=int, default=20, help="预览输出前 K 条")
    parser.add_argument("--limit", type=int, default=0, help="异动候选最多处理前 N 条")
    parser.add_argument("--min-turnover-rate", type=float, default=3.0, help="异动最低换手率")
    parser.add_argument("--min-composite-score", type=float, default=40.0, help="异动正式口径最低综合分")
    parser.add_argument("--max-main-net-rank", type=int, default=3, help="主力净流入题材内排名阈值")
    parser.add_argument("--fallback-top-k", type=int, default=20, help="fallback 异动清单输出条数")
    parser.add_argument("--details-root", default=str(PROJECT_ROOT / "theme_data_complete" / "stock_details"))
    parser.add_argument("--kline-root", default=str(PROJECT_ROOT / "theme_data_complete" / "_stock_kline" / "tushare" / "daily_bar"))
    parser.add_argument("--skip-fallback-abnormal", action="store_true", help="跳过生成 fallback 异动清单")
    parser.add_argument("--force-refresh-tail-auction", action="store_true", help="强制刷新尾盘竞价缓存")
    parser.add_argument("--force-refresh-dragon-tiger", action="store_true", help="强制刷新龙虎榜原始快照")
    parser.add_argument("--skip-dragon-tiger", action="store_true", help="跳过龙虎榜构建")
    parser.add_argument("--skip-abnormal-signal", action="store_true", help="跳过异动股票构建")
    parser.add_argument("--identity-mode", choices=["incremental", "init"], default="incremental", help="主线身份注册表模式")
    parser.add_argument("--identity-lookback-days", type=int, default=20, help="主线身份热点回看窗口")
    parser.add_argument("--identity-universe-size", type=int, default=180, help="主线身份评估题材上限")
    parser.add_argument("--identity-top-k", type=int, default=20, help="主线身份预览输出前K条")
    parser.add_argument("--identity-review-existing", action="store_true", help="incremental 模式是否重评近期已存在题材")
    parser.add_argument("--identity-deactivate-fade-days", type=int, default=2, help="连续 fade_confirmed 天数达到阈值时降级 inactive")
    parser.add_argument("--identity-disable-llm", action="store_true", help="禁用主线身份 LLM 复核（仅规则层）")
    parser.add_argument("--identity-allow-llm-fallback", action="store_true", help="允许主线身份 LLM 不可用时降级（默认不允许）")
    parser.add_argument("--skip-mainline-identity", action="store_true", help="跳过主线身份增量构建（默认执行 incremental，仅覆盖新题材）")
    parser.add_argument(
        "--skip-theme-cycle-judgement",
        action="store_true",
        help="跳过 v2 周期数据门禁与自动补建（排障模式）。",
    )
    parser.add_argument("--skip-v2-identity-prior-enforce", action="store_true", help="跳过 v2 身份先验收敛（默认执行）")
    parser.add_argument("--skip-mainline-state-tracking", action="store_true", help="跳过主线状态快照与迁移构建")
    parser.add_argument("--mainline-state-report-topn", type=int, default=10, help="主线状态迁移日报每类输出前N条")
    parser.add_argument("--skip-mainline-transition-gate", action="store_true", help="跳过主线迁移分布门禁")
    parser.add_argument(
        "--strict-mainline-transition-gate",
        action="store_true",
        help="启用严格主线迁移门禁（当日无迁移样本时仍强制执行并可失败）。默认无样本仅告警并跳过。",
    )
    parser.add_argument("--transition-gate-lookback-days", type=int, default=20, help="主线迁移门禁历史窗口天数")
    parser.add_argument("--transition-gate-min-total", type=int, default=8, help="主线迁移门禁最小样本数")
    parser.add_argument("--transition-gate-single-type-threshold", type=float, default=0.95, help="主线迁移门禁单类型集中阈值")
    parser.add_argument("--transition-gate-downgrade-jump", type=float, default=0.35, help="主线迁移门禁 downgrade 抬升阈值")
    parser.add_argument("--transition-gate-fade-jump", type=float, default=0.15, help="主线迁移门禁 fade 抬升阈值")
    parser.add_argument("--transition-gate-min-history-days", type=int, default=3, help="主线迁移门禁最小历史天数")
    parser.add_argument("--disable-transition-gate-auto-tune", action="store_true", help="关闭主线迁移门禁小样本自动调参")
    parser.add_argument(
        "--strict-transition-alert-fail",
        action="store_true",
        help="开启后，主线迁移分布告警将阻断复盘快照流程（默认仅告警不阻断）。",
    )
    parser.add_argument("--max-hidden-conflicts", type=int, default=0, help="身份/周期口径冲突 hidden_conflicts 允许上限")
    parser.add_argument("--max-dropped-conflicts", type=int, default=0, help="身份/周期口径冲突 dropped_conflicts 允许上限")
    parser.add_argument("--skip-legacy-entrypoint-gate", action="store_true", help="跳过 legacy 周期入口扫描门禁（仅排障使用）")
    parser.add_argument("--skip-upgrade-identity-trigger", action="store_true", help="跳过非主线升级样本触发的身份增量复核")
    parser.add_argument("--upgrade-identity-trigger-min-count", type=int, default=1, help="非主线升级触发身份复核的最小样本数")
    parser.add_argument("--skip-strong-watch-pipeline", action="store_true", help="跳过强势股池全链路（仅排障使用）")
    parser.add_argument("--skip-w2s-candidate-build", action="store_true", help="跳过弱转强候选构建（仅排障使用）")
    parser.add_argument("--w2s-max-candidates", type=int, default=10, help="弱转强候选池最大落库数量（硬上限10）")
    parser.add_argument(
        "--disable-auto-build-v2-if-missing",
        action="store_true",
        help="禁用v2周期数据缺失时自动补建（默认启用自动补建）",
    )
    parser.add_argument(
        "--strict-v2-cycle-gate",
        action="store_true",
        help="启用严格 v2 门禁（缺失即阻断）。默认缺失只告警并继续，避免整链无快照。",
    )
    return parser


def _run_step(name: str, cmd: list[str]) -> None:
    print(f"[STEP] {name}")
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)


async def _fetch_non_mainline_upgrade_subjects(
    trade_date: date,
    *,
    topn: int = 30,
) -> List[Dict[str, Any]]:
    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        sql = """
        SELECT
            t.subject_key,
            COALESCE(NULLIF(BTRIM(t.theme_name), ''), t.subject_key) AS theme_name,
            COALESCE(NULLIF(BTRIM(t.from_state), ''), '--') AS from_state,
            COALESCE(NULLIF(BTRIM(t.to_state), ''), '--') AS to_state,
            COALESCE(t.confidence, 0) AS confidence
        FROM mainline_state_transition t
        LEFT JOIN mainline_state_daily d
          ON d.trade_date = t.trade_date
         AND d.subject_key = t.subject_key
        WHERE t.trade_date = $1::date
          AND COALESCE(NULLIF(BTRIM(t.transition_type), ''), 'flat') = 'upgrade'
          AND COALESCE(d.is_mainline, FALSE) = FALSE
        ORDER BY COALESCE(t.confidence, 0) DESC, t.subject_key
        LIMIT $2
        """
        rows = await conn.fetch(sql, trade_date, max(1, topn))
        return [dict(r) for r in rows]
    finally:
        await conn.close()


async def _fetch_v2_cycle_readiness(trade_date: date) -> Dict[str, int]:
    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        row = await conn.fetchrow(
            """
            SELECT
                (SELECT COUNT(*)::int FROM theme_cycle_evidence_daily WHERE trade_date = $1::date) AS evidence_cnt,
                (SELECT COUNT(*)::int FROM theme_cycle_judgement_v2 WHERE trade_date = $1::date) AS v2_cnt
            """,
            trade_date,
        )
        return {
            "evidence_cnt": int((row or {}).get("evidence_cnt") or 0),
            "v2_cnt": int((row or {}).get("v2_cnt") or 0),
        }
    finally:
        await conn.close()


async def _assert_v2_cycle_gate_or_raise(trade_date_obj: date, trade_date_text: str) -> int:
    readiness = await _fetch_v2_cycle_readiness(trade_date_obj)
    v2_rows = int(readiness.get("v2_cnt") or 0)
    evidence_rows = int(readiness.get("evidence_cnt") or 0)
    if v2_rows > 0:
        print(
            f"[CHECK] v2_cycle_data_ready trade_date={trade_date_text} "
            f"v2_rows={v2_rows} evidence_rows={evidence_rows}"
        )
        return v2_rows
    raise RuntimeError(
        "v2_cycle_data_missing: theme_cycle_judgement_v2 当日无数据。"
        f"trade_date={trade_date_text}, evidence_rows={evidence_rows}, v2_rows={v2_rows}。"
        "请先完成『主线周期v2证据/判定构建』后再执行盘后复盘快照，"
        "避免在最后一步才失败。"
    )


async def _fetch_mainline_transition_count(trade_date_obj: date) -> int:
    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        row = await conn.fetchrow(
            "SELECT COUNT(*)::int AS c FROM mainline_state_transition WHERE trade_date = $1::date",
            trade_date_obj,
        )
        return int((row or {}).get("c") or 0)
    finally:
        await conn.close()


async def _ensure_v2_cycle_with_optional_autobuild(
    trade_date_obj: date,
    trade_date_text: str,
    *,
    enable_auto_build: bool,
    top_k: int,
    strict_gate: bool,
) -> int:
    readiness = await _fetch_v2_cycle_readiness(trade_date_obj)
    v2_rows = int(readiness.get("v2_cnt") or 0)
    evidence_rows = int(readiness.get("evidence_cnt") or 0)
    if v2_rows > 0:
        print(
            f"[CHECK] v2_cycle_data_ready trade_date={trade_date_text} "
            f"v2_rows={v2_rows} evidence_rows={evidence_rows}"
        )
        return v2_rows

    if enable_auto_build:
        print(
            f"[AUTO] v2_cycle_data_missing_detected trade_date={trade_date_text}, "
            f"evidence_rows={evidence_rows}, start auto-build"
        )
        _run_step(
            "theme_cycle_judgement_v2_build",
            [
                sys.executable,
                str(PROJECT_ROOT / "stock_service" / "scripts" / "build_theme_cycle_judgement_v2.py"),
                "--trade-date",
                trade_date_text,
                "--top-k",
                str(max(1, int(top_k))),
            ],
        )
    readiness = await _fetch_v2_cycle_readiness(trade_date_obj)
    v2_rows = int(readiness.get("v2_cnt") or 0)
    evidence_rows = int(readiness.get("evidence_cnt") or 0)
    if v2_rows > 0:
        return v2_rows
    if strict_gate:
        return await _assert_v2_cycle_gate_or_raise(trade_date_obj, trade_date_text)
    print(
        "[WARN] v2_cycle_data_missing_but_continue "
        f"trade_date={trade_date_text} evidence_rows={evidence_rows} v2_rows={v2_rows}"
    )
    return 0


async def _resolve_next_trade_date(trade_date: date) -> Optional[date]:
    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        row = await conn.fetchrow(
            """
            SELECT MIN(s.trade_date) AS next_trade_date
            FROM subject_stock_daily_snapshot s
            WHERE s.trade_date > $1::date
            """,
            trade_date,
        )
        if not row or row.get("next_trade_date") is None:
            return None
        return date.fromisoformat(str(row["next_trade_date"]))
    finally:
        await conn.close()


def _volume_ratio_from_evidence(evidence: list[str]) -> str:
    return next(
        (item.replace("量比 ", "") for item in evidence if item.startswith("量比 ")),
        "--",
    )


async def _build_abnormal_fallback(args: argparse.Namespace) -> Path:
    service = StockAbnormalSignalService()
    details_root = Path(args.details_root)
    kline_root = Path(args.kline_root)
    rows = load_current_inputs(
        args.trade_date,
        details_root,
        min_turnover_rate=args.min_turnover_rate,
        limit=args.limit,
    )

    close_auction_map: dict[str, dict] = {}
    if args.token or args.force_refresh_tail_auction:
        snapshot_service = TushareAuctionSnapshotService(
            StockServiceConfig(postgres_database=args.postgres_database)
        )
        if args.token:
            snapshot_service = TushareAuctionSnapshotService(
                StockServiceConfig(postgres_database=args.postgres_database, tushare_token=args.token)
            )
            try:
                snapshot_service.fetch_or_cache_stk_auction_c(
                    args.trade_date,
                    {item.stock_id for item in rows},
                    force_refresh=args.force_refresh_tail_auction,
                )
            except Exception as exc:
                print(f"[WARN] stk_auction_c unavailable, fallback without close auction data: {exc}")
        cached = snapshot_service.load_cached_stk_auction_c(args.trade_date)
        for record in (cached.records if cached else []):
            stock_code = _canonical_stock_id(record.get("ts_code") or record.get("stock_id") or "")
            if not stock_code:
                continue
            close_auction_map[stock_code] = {
                "amount": float(record.get("amount") or 0.0),
                "vol": float(record.get("vol") or 0.0),
                "vwap": float(record.get("vwap") or 0.0),
            }

    candidates: list[dict] = []
    for item in rows:
        kline_candidates = sorted(kline_root.glob(f"{_canonical_stock_id(item.stock_id)}.*.jsonl"))
        if not kline_candidates:
            continue
        history = service.load_stock_bars(kline_candidates[0])
        if len(history) < 20:
            continue
        auction_payload = close_auction_map.get(_canonical_stock_id(item.stock_id))
        if auction_payload:
            item.tail_auction_amount = auction_payload.get("amount")
            item.tail_auction_vwap = auction_payload.get("vwap")
        signal = service.build_signal(item, history)
        if signal and signal.abnormal_labels:
            candidates.append(
                {
                    "trade_date": signal.trade_date,
                    "subject_key": signal.subject_key,
                    "theme_name": signal.theme_name,
                    "stock_id": signal.stock_id,
                    "stock_name": signal.stock_name,
                    "abnormal_composite_score": float(signal.abnormal_composite_score or 0.0),
                    "turnover_rate": float(signal.turnover_rate or 0.0),
                    "volume_ratio_to_ma50": float(signal.volume_ratio_to_ma50 or 0.0),
                    "main_net_inflow_rank_in_theme": int(signal.main_net_inflow_rank_in_theme or 0),
                    "hot_money_buy_names": list(signal.hot_money_buy_names or []),
                    "institution_seat_count": int(signal.institution_seat_count or 0),
                    "abnormal_labels": list(signal.abnormal_labels or []),
                    "conclusion": signal.conclusion or "--",
                    "evidence": list(signal.evidence or []),
                }
            )

    candidates.sort(
        key=lambda item: (
            -float(item["abnormal_composite_score"]),
            -float(item["turnover_rate"]),
            -float(item["volume_ratio_to_ma50"]),
            str(item["stock_id"]),
        )
    )
    selected = candidates[: max(args.fallback_top_k, 0)]
    payload = {
        "trade_date": args.trade_date,
        "rows": selected,
    }
    out_json = PROJECT_ROOT / "tmp" / f"stock_abnormal_fallback_{args.trade_date}.json"
    out_md = PROJECT_ROOT / "tmp" / f"stock_abnormal_fallback_{args.trade_date}.md"
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [f"# {args.trade_date} 异动股补充清单", ""]
    for idx, row in enumerate(selected, 1):
        labels = "/".join(row["abnormal_labels"]) if row["abnormal_labels"] else "--"
        volume_ratio = _volume_ratio_from_evidence(row["evidence"])
        md_lines.append(
            f"{idx}. {row['stock_name']}｜{row['theme_name']}｜异动分 {row['abnormal_composite_score']:.2f}｜"
            f"换手率 {row['turnover_rate']:.2f}%｜量比 {volume_ratio}｜成交量/50日均量 {row['volume_ratio_to_ma50']:.2f}｜标签 {labels}"
        )
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    print(f"[OK] fallback_json={out_json}")
    print(f"[OK] fallback_markdown={out_md}")
    print(f"[OK] fallback_rows={len(selected)}")
    return out_json


async def main_async() -> int:
    args = build_parser().parse_args()
    # Force a single DB target across this script and child processes.
    os.environ["POSTGRES_DATABASE"] = args.postgres_database
    trade_date_obj = datetime.strptime(args.trade_date, "%Y-%m-%d").date()
    python = sys.executable
    db = args.postgres_database
    print(f"[INFO] effective_database={db}")

    def cmd(path: str, *extra: str) -> list[str]:
        return [python, str(PROJECT_ROOT / path), *extra]

    token_args = ["--token", args.token] if args.token else []

    auto_build_v2_if_missing = not bool(args.disable_auto_build_v2_if_missing)
    if not args.skip_legacy_entrypoint_gate:
        legacy_gate_cmd = cmd("stock_service/scripts/check_legacy_cycle_entrypoints.py")
        if auto_build_v2_if_missing:
            # 启用自动补建时允许 allow_legacy=True 的补建脚本仅告警，不阻断主流程。
            legacy_gate_cmd.append("--allow-legacy-warn-only")
        _run_step(
            "legacy_cycle_entrypoint_gate",
            legacy_gate_cmd,
        )
    else:
        print("[SKIP] legacy_cycle_entrypoint_gate (--skip-legacy-entrypoint-gate enabled)")

    _run_step(
        "stock_kline_judgements",
        cmd("database_service/scripts/build_stock_kline_judgements.py", "--trade-date", args.trade_date),
    )
    if not args.skip_dragon_tiger:
        dragon_cmd = cmd(
            "database_service/scripts/build_dragon_tiger_object.py",
            "--trade-date",
            args.trade_date,
            "--top-k",
            str(args.top_k),
            *token_args,
        )
        if args.force_refresh_dragon_tiger:
            dragon_cmd.append("--force-refresh")
        _run_step("dragon_tiger_object", dragon_cmd)
    _run_step(
        "market_environment_metrics",
        cmd("database_service/scripts/build_market_environment_metrics.py", "--trade-date", args.trade_date),
    )
    _run_step(
        "market_environment_judgement",
        cmd("database_service/scripts/build_market_environment_judgement.py", "--trade-date", args.trade_date),
    )
    _run_step(
        "theme_leader_candidate",
        cmd(
            "database_service/scripts/build_theme_leader_candidate.py",
            "--trade-date",
            args.trade_date,
            "--top-k",
            str(args.top_k),
        ),
    )
    _run_step(
        "money_flow_enhanced",
        cmd(
            "database_service/scripts/build_money_flow_enhanced.py",
            "--trade-date",
            args.trade_date,
            "--top-k",
            str(args.top_k),
        ),
    )
    run_identity_incremental = not args.skip_mainline_identity
    if run_identity_incremental:
        identity_cmd = cmd(
            "stock_service/scripts/build_mainline_identity_registry.py",
            "--trade-date",
            args.trade_date,
            "--mode",
            args.identity_mode,
            "--lookback-days",
            str(args.identity_lookback_days),
            "--universe-size",
            str(args.identity_universe_size),
            "--top-k",
            str(args.identity_top_k),
            "--deactivate-fade-days",
            str(args.identity_deactivate_fade_days),
        )
        if args.identity_review_existing:
            identity_cmd.append("--review-existing")
        if args.identity_disable_llm:
            identity_cmd.append("--disable-llm")
        if args.identity_allow_llm_fallback:
            identity_cmd.append("--allow-llm-fallback")
        _run_step("mainline_identity_registry", identity_cmd)
    else:
        print("[SKIP] mainline_identity_registry (--skip-mainline-identity enabled)")
    if args.skip_theme_cycle_judgement:
        print("[SKIP] theme_cycle_judgement_v2 gate/build (--skip-theme-cycle-judgement enabled)")
    else:
        await _ensure_v2_cycle_with_optional_autobuild(
            trade_date_obj,
            args.trade_date,
            enable_auto_build=not bool(args.disable_auto_build_v2_if_missing),
            top_k=int(args.top_k),
            strict_gate=bool(args.strict_v2_cycle_gate),
        )
    if not args.skip_v2_identity_prior_enforce:
        _run_step(
            "enforce_v2_identity_prior_gate",
            cmd(
                "stock_service/scripts/enforce_v2_identity_prior_gate.py",
                "--trade-date",
                args.trade_date,
                "--apply",
                "--promote-confirmed-nonfade",
            ),
        )
    if not args.skip_mainline_state_tracking:
        _run_step(
            "mainline_state_tracking",
            cmd(
                "stock_service/scripts/build_mainline_state_tracking.py",
                "--trade-date",
                args.trade_date,
                "--report-topn",
                str(max(0, args.mainline_state_report_topn)),
            ),
        )
    if not args.skip_strong_watch_pipeline:
        _run_step(
            "strong_stock_watch_pipeline",
            cmd(
                "stock_service/scripts/build_strong_stock_watch_pool.py",
                "--trade-date",
                args.trade_date,
            ),
        )
    else:
        print("[SKIP] strong_stock_watch_pipeline (--skip-strong-watch-pipeline enabled)")
    if not args.skip_w2s_candidate_build:
        next_trade_date = await _resolve_next_trade_date(trade_date_obj)
        if next_trade_date is None:
            print(
                "[SKIP] weak_to_strong_candidate_pool "
                f"(no next_trade_date for candidate_trade_date={args.trade_date})"
            )
        else:
            _run_step(
                "weak_to_strong_candidate_pool",
                cmd(
                    "scripts/build_weak_to_strong_candidate_pool.py",
                    "--trade-date",
                    args.trade_date,
                    "--next-trade-date",
                    next_trade_date.isoformat(),
                    "--max-candidates",
                    str(max(1, min(int(args.w2s_max_candidates), 10))),
                    "--skip-legacy-entrypoint-gate",
                ),
            )
    else:
        print("[SKIP] weak_to_strong_candidate_pool (--skip-w2s-candidate-build enabled)")
    if not args.skip_mainline_transition_gate:
        transition_count = await _fetch_mainline_transition_count(trade_date_obj)
        if transition_count <= 0 and not bool(args.strict_mainline_transition_gate):
            print(
                "[WARN] skip_mainline_hard_gate_no_transition_rows "
                f"trade_date={args.trade_date} transition_rows={transition_count}"
            )
        else:
            hard_gate_cmd = cmd(
                "stock_service/scripts/run_mainline_hard_gate.py",
                "--trade-date",
                args.trade_date,
                "--max-hidden-conflicts",
                str(max(0, int(args.max_hidden_conflicts))),
                "--max-dropped-conflicts",
                str(max(0, int(args.max_dropped_conflicts))),
                "--lookback-days",
                str(max(1, args.transition_gate_lookback_days)),
                "--min-total",
                str(max(1, args.transition_gate_min_total)),
                "--single-type-dominance-threshold",
                str(args.transition_gate_single_type_threshold),
                "--downgrade-jump-threshold",
                str(args.transition_gate_downgrade_jump),
                "--fade-jump-threshold",
                str(args.transition_gate_fade_jump),
                "--min-history-days",
                str(max(1, args.transition_gate_min_history_days)),
                "--skip-legacy-entrypoint-gate",
            )
            if args.disable_transition_gate_auto_tune:
                hard_gate_cmd.append("--disable-transition-auto-tune")
            if args.strict_transition_alert_fail:
                hard_gate_cmd.append("--fail-on-transition-alert")
            _run_step("mainline_hard_gate", hard_gate_cmd)
    if not args.skip_upgrade_identity_trigger:
        upgrade_subjects = await _fetch_non_mainline_upgrade_subjects(trade_date_obj, topn=30)
        upgrade_count = len(upgrade_subjects)
        print(
            f"[CHECK] non_mainline_upgrade_count={upgrade_count} "
            f"threshold={max(1, int(args.upgrade_identity_trigger_min_count))}"
        )
        for row in upgrade_subjects[:10]:
            print(
                "[CHECK] non_mainline_upgrade "
                f"subject_key={row.get('subject_key')} "
                f"theme_name={row.get('theme_name')} "
                f"from={row.get('from_state')} to={row.get('to_state')} "
                f"confidence={float(row.get('confidence') or 0.0):.2f}"
            )
        if upgrade_count >= max(1, int(args.upgrade_identity_trigger_min_count)):
            upgrade_subject_file = PROJECT_ROOT / "tmp" / f"mainline_upgrade_subjects_{args.trade_date}.txt"
            upgrade_subject_file.parent.mkdir(parents=True, exist_ok=True)
            upgrade_subject_file.write_text(
                "\n".join(str(r.get("subject_key") or "").strip() for r in upgrade_subjects if str(r.get("subject_key") or "").strip()) + "\n",
                encoding="utf-8",
            )
            identity_trigger_cmd = cmd(
                "stock_service/scripts/build_mainline_identity_registry.py",
                "--trade-date",
                args.trade_date,
                "--mode",
                "incremental",
                "--subject-keys-file",
                str(upgrade_subject_file),
                "--top-k",
                str(args.identity_top_k),
                "--deactivate-fade-days",
                str(args.identity_deactivate_fade_days),
            )
            if args.identity_disable_llm:
                identity_trigger_cmd.append("--disable-llm")
            if args.identity_allow_llm_fallback:
                identity_trigger_cmd.append("--allow-llm-fallback")
            _run_step("mainline_identity_upgrade_trigger", identity_trigger_cmd)
        else:
            print("[SKIP] mainline_identity_upgrade_trigger (insufficient non-mainline upgrades)")
    else:
        print("[SKIP] mainline_identity_upgrade_trigger (--skip-upgrade-identity-trigger enabled)")
    _run_step(
        "theme_environment_judgement",
        cmd(
            "database_service/scripts/build_theme_environment_judgement.py",
            "--trade-date",
            args.trade_date,
            "--top-k",
            str(args.top_k),
        ),
    )
    if not args.skip_abnormal_signal:
        abnormal_cmd = cmd(
            "database_service/scripts/build_stock_abnormal_signal.py",
            "--trade-date",
            args.trade_date,
            "--min-turnover-rate",
            str(args.min_turnover_rate),
            "--min-composite-score",
            str(args.min_composite_score),
            "--max-main-net-rank",
            str(args.max_main_net_rank),
            "--details-root",
            args.details_root,
            "--kline-root",
            args.kline_root,
            *token_args,
        )
        if args.limit > 0:
            abnormal_cmd.extend(["--limit", str(args.limit)])
        if args.force_refresh_tail_auction:
            abnormal_cmd.append("--force-refresh-tail-auction")
        _run_step("stock_abnormal_signal", abnormal_cmd)

    if not args.skip_abnormal_signal and not args.skip_fallback_abnormal:
        print("[STEP] abnormal_fallback")
        await _build_abnormal_fallback(args)

    snapshot_cmd = cmd(
        "scripts/stock_service_generate_report_snapshot.py",
        "--trade-date",
        args.trade_date,
        "--report-type",
        "post_market",
        "--postgres-database",
        db,
    )
    if args.batch_id:
        snapshot_cmd.extend(["--batch-id", args.batch_id])
    _run_step("post_market_snapshot", snapshot_cmd)
    # Persist post-market recap snapshot as DB truth source (not just local json/md files).
    recap_repo = ReportRepository(StockServiceConfig(postgres_database=db))
    await recap_repo.initialize()
    try:
        recap_service = RecapService(recap_repo)
        post_report = await recap_service.build_post_market_report(args.trade_date)
    finally:
        await recap_repo.close()

    batch_id = args.batch_id or f"pm_snapshot_{args.trade_date.replace('-', '')}"
    trace_id = f"build_post_market_recap:{args.trade_date}"
    payload = {
        "report": {
            "report_type": post_report.report_type,
            "trade_date": post_report.trade_date,
            "title": post_report.title,
            "summary": post_report.summary,
            "highlights": list(post_report.highlights or []),
            "sections": [
                {"heading": heading, "items": list(items or [])}
                for heading, items in list(post_report.sections or [])
            ],
            "metadata": dict(getattr(post_report, "metadata", {}) or {}),
        }
    }
    cfg_upsert = StockServiceConfig(postgres_database=db)
    conn_upsert = await asyncpg.connect(
        host=cfg_upsert.postgres_host,
        port=cfg_upsert.postgres_port,
        database=cfg_upsert.postgres_database,
        user=cfg_upsert.postgres_user,
        password=cfg_upsert.postgres_password,
    )
    try:
        await conn_upsert.execute(
            """
            INSERT INTO post_market_recap_snapshot (
                trade_date, snapshot_version, batch_id, trace_id, payload, source_name
            ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
            ON CONFLICT (trade_date) DO UPDATE SET
              snapshot_version = EXCLUDED.snapshot_version,
              batch_id = EXCLUDED.batch_id,
              trace_id = EXCLUDED.trace_id,
              payload = EXCLUDED.payload || post_market_recap_snapshot.payload,
              source_name = EXCLUDED.source_name,
              updated_at = NOW()
            """,
            trade_date_obj,
            f"post_market_recap_v2:{args.trade_date}",
            batch_id,
            trace_id,
            json.dumps(payload, ensure_ascii=False),
            "stock_processing_service",
        )
    finally:
        await conn_upsert.close()
    print(f"[OK] post_market_recap_snapshot_upserted trade_date={args.trade_date} db={db}")
    # Hard verify: recap snapshot row must exist in target DB after successful build.
    cfg = StockServiceConfig(postgres_database=db)
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        row = await conn.fetchrow(
            """
            SELECT snapshot_version
            FROM post_market_recap_snapshot
            WHERE trade_date = $1::date
            ORDER BY updated_at DESC NULLS LAST
            LIMIT 1
            """,
            trade_date_obj,
        )
    finally:
        await conn.close()
    if not row or not str(row.get("snapshot_version") or "").strip():
        raise RuntimeError(
            f"post_market_snapshot_verify_failed: no recap snapshot row in db={db}, trade_date={args.trade_date}"
        )
    print(f"[OK] snapshot_verify_passed trade_date={args.trade_date} snapshot_version={row['snapshot_version']}")
    print(f"[OK] completed post-market recap for trade_date={args.trade_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
