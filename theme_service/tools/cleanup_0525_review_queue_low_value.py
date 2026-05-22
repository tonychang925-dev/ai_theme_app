from __future__ import annotations

import argparse
import asyncio
import json
import os
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import asyncpg


LOW_VALUE_DROP_REASON_CODES = {
    "low_value_event_match_blocked",
    "low_value_regulatory_event_blocked",
    "ordinary_earnings_low_value",
    "clarification_risk_notice_low_value",
    "weather_disaster_low_value",
    "ordinary_ipo_low_value",
    "duplicate_news_low_value",
    "low_value_event_dropped",
    "rule_low_value_regulatory",
    "rule_low_value_clarification",
    "rule_low_value_disaster",
    "rule_low_value_earnings",
    "rule_low_value_disclosure",
    "rule_low_value_ordinary_personnel",
    "rule_low_value_ordinary_ipo",
}
LOW_VALUE_TERMS = (
    "行政监管措施",
    "行政监管",
    "监管措施决定书",
    "监管函",
    "警示函",
    "责令改正",
    "问询函",
    "关注函",
    "审核问询函",
    "澄清",
    "风险提示",
    "交易异动",
    "连续涨停",
    "连板",
    "无注入",
    "不涉及",
    "无算力计划",
    "天气预警",
    "山洪",
    "暴雨",
    "地震",
    "列车停运",
    "第一季度",
    "一季度",
    "Q1",
    "财报",
    "营收",
    "净利润",
    "回购",
    "减持",
    "权益变动",
    "触及1%整数倍",
    "投资者接待日",
    "集体接待日",
    "业绩说明会",
    "任命",
    "辞任",
    "选举",
    "IPO",
    "上市聆讯",
)


def _database_dsn(db_name: str | None) -> str:
    raw = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if raw:
        return raw
    db = db_name or os.getenv("PG_DATABASE") or os.getenv("DB_NAME") or os.getenv("POSTGRES_DATABASE") or "stock_data_test"
    user = os.getenv("PGUSER") or os.getenv("POSTGRES_USER") or "postgres"
    password = os.getenv("PGPASSWORD") or os.getenv("POSTGRES_PASSWORD") or ""
    host = os.getenv("PGHOST") or os.getenv("POSTGRES_HOST") or "127.0.0.1"
    port = os.getenv("PGPORT") or os.getenv("POSTGRES_PORT") or "5432"
    auth = f"{user}:{password}@" if password else f"{user}@"
    return f"postgresql://{auth}{host}:{port}/{db}"


def _event_text(row: dict[str, Any]) -> str:
    return " ".join(str(row.get(field) or "") for field in ("title", "summary", "reason", "theme_name"))


def _drop_reason(row: dict[str, Any]) -> str | None:
    reason = str(row.get("reason") or row.get("reason_code") or "")
    text = _event_text(row)
    for term in LOW_VALUE_TERMS:
        if term in text:
            if term in {"行政监管措施", "行政监管", "监管措施决定书", "监管函", "警示函", "责令改正", "问询函", "关注函", "审核问询函"}:
                return "low_value_regulatory_event_blocked"
            if term in {"第一季度", "一季度", "Q1", "财报", "营收", "净利润"}:
                return "ordinary_earnings_low_value"
            if term in {"澄清", "风险提示", "交易异动", "连续涨停", "连板", "无注入", "不涉及", "无算力计划"}:
                return "clarification_risk_notice_low_value"
            if term in {"天气预警", "山洪", "暴雨", "地震", "列车停运"}:
                return "weather_disaster_low_value"
            if term in {"IPO", "上市聆讯"}:
                return "ordinary_ipo_low_value"
            return "low_value_event_dropped"
    if reason in LOW_VALUE_DROP_REASON_CODES:
        return reason
    return None


def _classify_review_events(review_events: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    kept: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for row in review_events:
        reason = _drop_reason(row)
        if reason:
            item = dict(row)
            item["action"] = "drop_event"
            item["review_required"] = False
            item["drop_reason_code"] = reason
            dropped.append(item)
        else:
            kept.append(row)
    return kept, dropped


def _filter_risk_alerts(risk_alerts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for alert in risk_alerts:
        text = json.dumps(alert, ensure_ascii=False)
        if any(code in text for code in LOW_VALUE_DROP_REASON_CODES) or any(term in text for term in LOW_VALUE_TERMS):
            continue
        out.append(alert)
    return out


def _metrics(dropped: list[dict[str, Any]], original_review_count: int, kept_review_count: int) -> dict[str, int]:
    return {
        "original_review_event_count": original_review_count,
        "kept_review_event_count": kept_review_count,
        "dropped_event_count": len(dropped),
        "low_value_dropped_count": len(dropped),
        "duplicate_dropped_count": sum(1 for row in dropped if "duplicate" in str(row.get("drop_reason_code") or "")),
        "regulatory_notice_dropped_count": sum(1 for row in dropped if row.get("drop_reason_code") == "low_value_regulatory_event_blocked"),
        "ordinary_earnings_dropped_count": sum(1 for row in dropped if row.get("drop_reason_code") == "ordinary_earnings_low_value"),
    }


async def _load_snapshot(conn: asyncpg.Connection, trade_date: date) -> dict[str, Any]:
    row = await conn.fetchrow(
        """
        SELECT trade_date, snapshot_version, payload
        FROM pre_market_brief_snapshot
        WHERE trade_date = $1
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        trade_date,
    )
    if not row:
        raise RuntimeError(f"pre_market_brief_snapshot not found: trade_date={trade_date}")
    payload = row["payload"]
    if isinstance(payload, str):
        payload = json.loads(payload)
    return {"trade_date": row["trade_date"], "snapshot_version": row["snapshot_version"], "payload": payload}


async def _write_snapshot(conn: asyncpg.Connection, trade_date: date, snapshot_version: str, payload: dict[str, Any]) -> None:
    await conn.execute(
        """
        UPDATE pre_market_brief_snapshot
        SET payload = $3::jsonb, updated_at = NOW()
        WHERE trade_date = $1 AND snapshot_version = $2
        """,
        trade_date,
        snapshot_version,
        json.dumps(payload, ensure_ascii=False, default=str),
    )


def _write_outputs(out_dir: Path, detail: list[dict[str, Any]], metrics: dict[str, int], apply: bool) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    detail_path = out_dir / "review_events_detail.jsonl"
    report_path = out_dir / "review_cleanup_report.md"
    detail_path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in detail) + ("\n" if detail else ""),
        encoding="utf-8",
    )
    lines = [
        "# 5/25 Review Queue Low-Value Cleanup",
        "",
        f"- apply: `{str(apply).lower()}`",
        f"- generated_at: `{datetime.now(timezone.utc).isoformat()}`",
        "",
    ]
    for key, value in metrics.items():
        lines.append(f"- {key}: {value}")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_snapshot_backup(out_dir: Path, payload: dict[str, Any]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "pre_cleanup_snapshot_payload.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Classify and optionally remove 2026-05-25 low-value review events from pre-market snapshot.")
    parser.add_argument("--trade-date", default="2026-05-25")
    parser.add_argument("--out-dir", default="tmp/product_runtime_0525_review_cleanup")
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--apply", action="store_true", help="Update snapshot payload after writing reports.")
    args = parser.parse_args()

    trade_date = date.fromisoformat(args.trade_date)
    conn = await asyncpg.connect(_database_dsn(args.db_name))
    try:
        snapshot = await _load_snapshot(conn, trade_date)
        payload = deepcopy(snapshot["payload"])
        sections = payload.setdefault("sections", {})
        diagnostics = payload.setdefault("diagnostics", {})
        review_events = list(sections.get("review_events") or [])
        kept, dropped = _classify_review_events(review_events)
        sections["review_events"] = kept
        sections["risk_alerts"] = _filter_risk_alerts(list(sections.get("risk_alerts") or []))
        dropped_metrics = _metrics(dropped, len(review_events), len(kept))
        diagnostics.update(dropped_metrics)
        diagnostics["review_cleanup_last_run_at"] = datetime.now(timezone.utc).isoformat()
        diagnostics["review_cleanup_apply"] = bool(args.apply)

        _write_outputs(Path(args.out_dir), dropped, dropped_metrics, args.apply)
        if args.apply:
            _write_snapshot_backup(Path(args.out_dir), snapshot["payload"])
            await _write_snapshot(conn, trade_date, str(snapshot["snapshot_version"]), payload)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
