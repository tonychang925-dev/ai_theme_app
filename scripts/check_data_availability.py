#!/usr/bin/env python3
"""
弱转强 P0 Gate: 数据可用性校验脚本

用途：
1. 校验候选池、竞价窗口、板块联动关键数据是否可用
2. 给出 data_status 级别统计（ok/partial/delayed/missing）
3. 作为 P0 Gate 入场检查工具
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Dict, List, Optional


try:
    import asyncpg
except Exception:  # pragma: no cover
    asyncpg = None


@dataclass
class CheckResult:
    trade_date: str
    total_candidates: int
    ok_count: int
    partial_count: int
    delayed_count: int
    missing_count: int
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "total_candidates": self.total_candidates,
            "ok_count": self.ok_count,
            "partial_count": self.partial_count,
            "delayed_count": self.delayed_count,
            "missing_count": self.missing_count,
            "warnings": self.warnings,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check weak-to-strong data availability for P0 gate.")
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument(
        "--dsn",
        default=os.getenv("POSTGRES_DSN", ""),
        help="Postgres DSN, e.g. postgresql://user:pass@host:5432/dbname",
    )
    parser.add_argument(
        "--latency-threshold-ms",
        type=int,
        default=2000,
        help="Latency threshold for delayed status",
    )
    parser.add_argument(
        "--output",
        default="",
        help="Optional output JSON file path",
    )
    return parser.parse_args()


def _validate_trade_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


async def _fetch_count(conn: Any, sql: str, *params: Any) -> int:
    value = await conn.fetchval(sql, *params)
    return int(value or 0)


async def run_check(trade_date: date, dsn: str, latency_threshold_ms: int) -> CheckResult:
    warnings: List[str] = []

    if asyncpg is None:
        raise RuntimeError("asyncpg is not installed. Please run with project virtualenv.")
    if not dsn:
        raise RuntimeError("Missing DSN. Please set --dsn or POSTGRES_DSN.")

    conn = await asyncpg.connect(dsn=dsn)
    try:
        # 1) 候选池记录数（前置）
        candidate_sql = """
        SELECT COUNT(*)
        FROM weak_to_strong_candidate_pool
        WHERE next_trade_date = $1::date
        """
        try:
            total_candidates = await _fetch_count(conn, candidate_sql, trade_date)
            if total_candidates <= 0:
                warnings.append("No candidate records for next_trade_date.")
        except Exception as e:
            # P0阶段允许缺表，按 missing 处理，避免脚本崩溃
            total_candidates = 0
            warnings.append(f"Candidate pool table unavailable: {e}")

        # 2) 竞价窗口可用性（使用原始快照表做近似检查）
        auction_sql = """
        SELECT COUNT(DISTINCT split_part(stock_id, '.', 1))
        FROM subject_stock_daily_snapshot
        WHERE trade_date = $1::date
          AND stock_id IS NOT NULL
          AND stock_id <> ''
        """
        available_snapshot_stocks = await _fetch_count(conn, auction_sql, trade_date)
        if available_snapshot_stocks <= 0:
            warnings.append("No stock snapshots found for trade_date.")

        # 3) 板块联动可用性
        plate_sql = """
        SELECT COUNT(*)
        FROM theme_mainline_judgement
        WHERE trade_date = $1::date
        """
        plate_count = await _fetch_count(conn, plate_sql, trade_date)
        if plate_count <= 0:
            warnings.append("No theme_mainline_judgement records for trade_date.")

        # 4) 简化 data_status 统计（P0阶段，按数据面分层）
        # 说明：
        # - 该脚本在 P0 主要判断“是否可判定”，并不给单票最终分级
        # - 更细粒度的 per-candidate status 在 P2 服务侧输出
        if total_candidates <= 0:
            missing_count = 1
            ok_count = partial_count = delayed_count = 0
        elif available_snapshot_stocks <= 0 or plate_count <= 0:
            # 有候选但关键数据缺失 -> missing
            missing_count = total_candidates
            ok_count = partial_count = delayed_count = 0
        else:
            # P0 阶段无实时延迟源，先以“可用”归类为 ok
            # latency_threshold_ms 参数保留给后续接实时数据源
            _ = latency_threshold_ms
            ok_count = total_candidates
            partial_count = delayed_count = missing_count = 0

        return CheckResult(
            trade_date=trade_date.isoformat(),
            total_candidates=total_candidates,
            ok_count=ok_count,
            partial_count=partial_count,
            delayed_count=delayed_count,
            missing_count=missing_count,
            warnings=warnings,
        )
    finally:
        await conn.close()


def main() -> int:
    args = parse_args()
    trade_date = _validate_trade_date(args.trade_date)
    result = asyncio.run(
        run_check(
            trade_date=trade_date,
            dsn=args.dsn,
            latency_threshold_ms=max(int(args.latency_threshold_ms), 0),
        )
    )

    payload = result.to_dict()
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")

    # Gate 建议：若 missing_count > 0 或无候选，则返回非零
    if result.missing_count > 0 or result.total_candidates <= 0:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
