#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List

import asyncpg

from stock_service.config import StockServiceConfig


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="导出主线证据清单（主线/升级/降级/退潮）")
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--limit", type=int, default=200, help="每类最多导出条数")
    parser.add_argument("--output", default="", help="输出markdown文件路径（可选）")
    return parser.parse_args()


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def _as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []
    return []


async def _fetch_rows(conn: asyncpg.Connection, trade_date: date, limit: int) -> List[asyncpg.Record]:
    sql = """
    SELECT
      d.subject_key,
      d.theme_name,
      d.state,
      d.state_score,
      d.is_mainline,
      d.mainline_strength_score,
      d.fade_watch_score,
      d.fade_confirmed_score,
      d.divergence_score,
      d.repair_score,
      d.evidence_json,
      t.from_state,
      t.to_state,
      t.transition_type,
      t.confidence,
      t.trigger_flags
    FROM mainline_state_daily d
    LEFT JOIN mainline_state_transition t
      ON t.trade_date = d.trade_date
     AND t.subject_key = d.subject_key
    WHERE d.trade_date = $1::date
    ORDER BY
      CASE COALESCE(t.transition_type, 'flat')
        WHEN 'fade' THEN 0
        WHEN 'downgrade' THEN 1
        WHEN 'upgrade' THEN 2
        ELSE 3
      END,
      d.state_score DESC,
      d.subject_key
    LIMIT $2::int
    """
    return await conn.fetch(sql, trade_date, limit)


def _format_section(title: str, rows: List[Dict[str, Any]]) -> List[str]:
    lines = [f"## {title}", ""]
    if not rows:
        lines.append("- 无")
        lines.append("")
        return lines
    for r in rows:
        lines.append(
            "- `{subject_key}` {theme_name} | state={state} | transition={transition_type} | "
            "score={state_score:.2f} | conf={confidence:.2f} | kline_support_hold={kline_support_hold} | "
            "one_day_tour_kline={one_day_tour_kline_flag} | platform_breakout={platform_breakout_flag}".format(**r)
        )
        if r["trigger_flags"]:
            lines.append(f"  - trigger_flags: {', '.join(r['trigger_flags'])}")
        lines.append(
            "  - mainline_strength={mainline_strength_score:.2f}, divergence={divergence_score:.2f}, "
            "repair={repair_score:.2f}, fade_watch={fade_watch_score:.2f}, fade_confirmed={fade_confirmed_score:.2f}".format(**r)
        )
    lines.append("")
    return lines


def _normalize_row(row: asyncpg.Record) -> Dict[str, Any]:
    evidence = _as_dict(row.get("evidence_json"))
    identity_evidence = _as_dict(evidence.get("identity_evidence"))
    return {
        "subject_key": str(row.get("subject_key") or ""),
        "theme_name": str(row.get("theme_name") or row.get("subject_key") or ""),
        "state": str(row.get("state") or ""),
        "state_score": float(row.get("state_score") or 0.0),
        "transition_type": str(row.get("transition_type") or "flat"),
        "from_state": str(row.get("from_state") or "") if row.get("from_state") is not None else None,
        "to_state": str(row.get("to_state") or ""),
        "confidence": float(row.get("confidence") or 0.0),
        "trigger_flags": [str(x) for x in _as_list(row.get("trigger_flags"))],
        "mainline_strength_score": float(row.get("mainline_strength_score") or 0.0),
        "fade_watch_score": float(row.get("fade_watch_score") or 0.0),
        "fade_confirmed_score": float(row.get("fade_confirmed_score") or 0.0),
        "divergence_score": float(row.get("divergence_score") or 0.0),
        "repair_score": float(row.get("repair_score") or 0.0),
        "is_mainline": bool(row.get("is_mainline") or False),
        "kline_support_hold": bool(identity_evidence.get("kline_support_hold") or False),
        "one_day_tour_kline_flag": bool(identity_evidence.get("one_day_tour_kline_flag") or False),
        "platform_breakout_flag": bool(identity_evidence.get("platform_breakout_flag") or False),
    }


async def main_async() -> int:
    args = parse_args()
    trade_date = _parse_date(args.trade_date)
    cfg = StockServiceConfig()
    conn = await asyncpg.connect(
        host=cfg.postgres_host,
        port=cfg.postgres_port,
        database=cfg.postgres_database,
        user=cfg.postgres_user,
        password=cfg.postgres_password,
    )
    try:
        rows = await _fetch_rows(conn, trade_date, int(args.limit))
    finally:
        await conn.close()

    normalized = [_normalize_row(r) for r in rows]
    mainline_rows = [r for r in normalized if r["is_mainline"]]
    upgrade_rows = [r for r in normalized if r["transition_type"] == "upgrade"]
    downgrade_rows = [r for r in normalized if r["transition_type"] == "downgrade"]
    fade_rows = [r for r in normalized if r["transition_type"] == "fade"]

    lines: List[str] = []
    lines.append(f"# 主线证据清单 {trade_date.isoformat()}")
    lines.append("")
    lines.append(f"- 总样本：{len(normalized)}")
    lines.append(f"- 主线：{len(mainline_rows)}")
    lines.append(f"- 升级：{len(upgrade_rows)}")
    lines.append(f"- 降级：{len(downgrade_rows)}")
    lines.append(f"- 退潮：{len(fade_rows)}")
    lines.append("")
    lines.extend(_format_section("主线清单", mainline_rows))
    lines.extend(_format_section("升级清单", upgrade_rows))
    lines.extend(_format_section("降级清单", downgrade_rows))
    lines.extend(_format_section("退潮清单", fade_rows))

    output_text = "\n".join(lines)
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(output_text, encoding="utf-8")
        print(f"[OK] written={out_path}")
    else:
        print(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
