#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from database_service.scripts.build_stock_abnormal_signal import (
    _canonical_stock_id,
    load_current_inputs,
)
from stock_service.config import StockServiceConfig
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
    return parser


def _run_step(name: str, cmd: list[str]) -> None:
    print(f"[STEP] {name}")
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), check=True)


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
    python = sys.executable
    db = args.postgres_database

    def cmd(path: str, *extra: str) -> list[str]:
        return [python, str(PROJECT_ROOT / path), *extra]

    token_args = ["--token", args.token] if args.token else []

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
        "theme_mainline_judgement",
        cmd(
            "database_service/scripts/build_theme_mainline_judgement.py",
            "--trade-date",
            args.trade_date,
            "--top-k",
            str(args.top_k),
        ),
    )
    _run_step(
        "theme_cycle_judgement",
        cmd(
            "database_service/scripts/build_theme_cycle_judgement.py",
            "--trade-date",
            args.trade_date,
            "--top-k",
            str(args.top_k),
        ),
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
    print(f"[OK] completed post-market recap for trade_date={args.trade_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
