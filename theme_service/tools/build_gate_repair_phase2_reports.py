from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gate_quality_audit import b_p0_reasons

SHORT_NAME_REGION_HINTS = {
    "房地产",
    "风电",
    "大豆",
    "养殖业",
    "全国文旅",
    "外贸出口",
    "东盟自贸区",
    "中俄贸易",
}
PRODUCT_NEIGHBOR_HINTS = {
    "水电站设备",
    "太空光伏",
    "工业母机",
    "充电桩",
    "氢能源",
    "固体氧化物燃料电池",
    "麦角硫因",
    "电子材料涨价",
    "电子布Low-DK",
}
COMPANY_EVENT_MARKERS = ("IPO", "重组", "供货商", "大会", "手机", "阿里云", "小米", "努比亚", "禾赛", "超聚变", "乐聚")
BROAD_THEME_MARKERS = ("五大核心", "科技类", "年报预增", "美好中国", "改革", "九大核心", "产业链")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


async def _load_v2_statuses(db_name: str) -> dict[str, dict[str, str]]:
    conn = await asyncpg.connect(
        host=os.getenv("POSTGRES_HOST", os.getenv("DB_HOST", "localhost")),
        port=int(os.getenv("POSTGRES_PORT", os.getenv("DB_PORT", "5432"))),
        user=os.getenv("POSTGRES_USER", os.getenv("DB_USER", "postgres")),
        password=os.getenv("POSTGRES_PASSWORD", os.getenv("DB_PASSWORD", "postgres")),
        database=db_name,
    )
    try:
        rows = await conn.fetch(
            """
            SELECT subject_key, subject_name, status
            FROM theme_profile_v2
            ORDER BY subject_key, updated_at DESC NULLS LAST
            """
        )
    finally:
        await conn.close()

    by_key: dict[str, dict[str, str]] = {}
    for row in rows:
        key = str(row["subject_key"])
        current = by_key.setdefault(
            key,
            {"subject_key": key, "subject_name": str(row["subject_name"] or key), "statuses": ""},
        )
        statuses = [item for item in current["statuses"].split(",") if item]
        status = str(row["status"] or "")
        if status and status not in statuses:
            statuses.append(status)
        current["statuses"] = ",".join(statuses)
    return by_key


async def build_runtime_source_rows(
    *,
    db_name: str,
    v1_rows: list[dict[str, Any]],
    v2_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    v2_statuses = await _load_v2_statuses(db_name)
    v1_by_key = {str(row["subject_key"]): row for row in v1_rows}
    v2_by_key = {str(row["subject_key"]): row for row in v2_rows}
    keys = sorted(set(v1_by_key) | set(v2_by_key) | set(v2_statuses))
    rows: list[dict[str, Any]] = []
    for key in keys:
        v1 = v1_by_key.get(key)
        accepted_v2 = v2_by_key.get(key)
        status_row = v2_statuses.get(key) or {}
        statuses = [item for item in str(status_row.get("statuses") or "").split(",") if item]
        runtime_source = "v2_accepted" if accepted_v2 else "v1_fallback"
        active = accepted_v2 or v1 or {}
        rows.append(
            {
                "subject_key": key,
                "subject_name": str(
                    active.get("subject_name")
                    or status_row.get("subject_name")
                    or (v1 or {}).get("subject_name")
                    or key
                ),
                "runtime_source": runtime_source,
                "has_v2": bool(statuses),
                "v2_status": "accepted_candidate" if accepted_v2 else (",".join(statuses) or None),
                "v1_risk_level": (v1 or {}).get("risk_level"),
                "v2_risk_level": (accepted_v2 or {}).get("risk_level"),
                "active_runtime_risk_level": active.get("risk_level"),
                "risk_flags": active.get("risk_flags") or [],
                "suggested_action": active.get("suggested_action"),
            }
        )
    rows.sort(
        key=lambda row: (
            {"A": 0, "B": 1, "C": 2, "D": 3}.get(str(row.get("active_runtime_risk_level")), 9),
            0 if row["runtime_source"] == "v1_fallback" else 1,
            row["subject_key"],
        )
    )
    return rows


def write_b_p0_plan(path: Path, sources: list[tuple[str, list[dict[str, Any]]]]) -> None:
    rows: list[tuple[str, dict[str, Any], list[str]]] = []
    for source, source_rows in sources:
        for row in source_rows:
            reasons = b_p0_reasons(row)
            if row.get("risk_level") == "B" and reasons:
                rows.append((source, row, reasons))

    rows.sort(key=lambda item: (-float(item[1].get("confusability_score") or 0.0), item[0], item[1]["subject_key"]))
    lines = [
        "# Gate Repair Phase 2 B-P0 Plan",
        "",
        f"- B-P0 count: `{len(rows)}`",
        "",
    ]
    for source, row, reasons in rows:
        lines.extend(
            [
                f"- `{source}` `{row['subject_key']}` `{row['subject_name']}`",
                f"  - reasons: `{','.join(reasons)}`",
                f"  - risk_flags: `{','.join(row.get('risk_flags') or [])}`",
                f"  - confusability: `{row.get('confusability_score')}` false_positive_count: `{row.get('false_positive_count')}`",
                f"  - action: `{row.get('suggested_action')}`",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _b_p0_repair_group(row: dict[str, Any]) -> tuple[str, str, str, str]:
    name = str(row.get("subject_name") or "")
    flags = set(row.get("risk_flags") or [])
    reasons = b_p0_reasons(row)
    confusability = float(row.get("confusability_score") or 0.0)
    if name in SHORT_NAME_REGION_HINTS or (len(name) <= 3 and "TITLE_NOT_ALIGNED" in flags):
        return (
            "short_name_region",
            "P0" if "MUST_TOO_COMMON" in flags or confusability >= 0.10 else "P1",
            "short or regional theme needs a defined trading story instead of a bare title hit",
            "replace bare-title anchors with accepted core-story combinations and reject-only-hit rules",
        )
    if name in PRODUCT_NEIGHBOR_HINTS:
        return (
            "product_neighbor",
            "P0" if confusability >= 0.10 else "P1",
            "product/material theme can collide with neighbor applications or broad supply-chain terms",
            "add application anchors plus neighbor negatives and reject-domain boundaries",
        )
    if any(marker in name for marker in COMPANY_EVENT_MARKERS):
        return (
            "company_event",
            "P0" if "MUST_TOO_COMMON" in flags else "P1",
            "company or event theme must bind entity and event action together",
            "require named entity plus event-action anchors and reject generic company-news hits",
        )
    if any(marker in name for marker in BROAD_THEME_MARKERS):
        return (
            "broad_theme",
            "P1",
            "broad theme can steal primary position from a narrower candidate",
            "demote generic evidence, add accepted scope, and keep specific-child boundaries explicit",
        )
    if reasons == ["WEAK_GATE_WITH_EMPTY_NOT"]:
        return (
            "weak_boundary_only",
            "P2",
            "current P0 marker comes from an empty weak boundary without observed high-risk collision",
            "defer until positive and negative cases define the missing semantic boundary",
        )
    return (
        "weak_boundary_only",
        "P1",
        "weak boundary needs semantic evidence before mechanical negative-term edits",
        "add hard anchors and one positive/negative case before changing boundary terms",
    )


def build_b_p0_semantic_group_rows(sources: list[tuple[str, list[dict[str, Any]]]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source, source_rows in sources:
        for row in source_rows:
            reasons = b_p0_reasons(row)
            if row.get("risk_level") != "B" or not reasons:
                continue
            group, priority, reason, mode = _b_p0_repair_group(row)
            rows.append(
                {
                    "source": source,
                    "subject_key": str(row["subject_key"]),
                    "subject_name": str(row["subject_name"]),
                    "risk_flags": row.get("risk_flags") or [],
                    "b_p0_reasons": reasons,
                    "repair_group": group,
                    "repair_priority": priority,
                    "reason": reason,
                    "suggested_repair_mode": mode,
                }
            )
    rows.sort(
        key=lambda row: (
            {"P0": 0, "P1": 1, "P2": 2}.get(row["repair_priority"], 9),
            row["repair_group"],
            row["source"],
            row["subject_key"],
        )
    )
    return rows


def write_b_p0_semantic_groups(path: Path, rows: list[dict[str, Any]]) -> None:
    counts: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["repair_priority"], row["repair_group"])
        counts[key] = counts.get(key, 0) + 1
    lines = ["# Gate Repair Phase 3 B-P0 Semantic Groups", "", f"- total: `{len(rows)}`", ""]
    for priority in ("P0", "P1", "P2"):
        priority_rows = [row for row in rows if row["repair_priority"] == priority]
        if not priority_rows:
            continue
        lines.extend([f"## {priority}", ""])
        for group in ("short_name_region", "product_neighbor", "company_event", "broad_theme", "weak_boundary_only"):
            group_rows = [row for row in priority_rows if row["repair_group"] == group]
            if not group_rows:
                continue
            lines.extend([f"### {group} ({counts[(priority, group)]})", ""])
            for row in group_rows:
                lines.extend(
                    [
                        f"- `{row['source']}` `{row['subject_key']}` `{row['subject_name']}`",
                        f"  - risk_flags: `{','.join(row['risk_flags'])}`",
                        f"  - reason: {row['reason']}",
                        f"  - repair: {row['suggested_repair_mode']}",
                    ]
                )
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Build Gate Repair Phase 2 runtime-source and B-P0 reports.")
    parser.add_argument("--db-name", default=os.getenv("READ_DB_NAME", "stock_data_test"))
    parser.add_argument("--v1-audit", type=Path, required=True)
    parser.add_argument("--v2-audit", type=Path, required=True)
    parser.add_argument("--runtime-out", type=Path, default=Path("tmp/gate_quality_audit_runtime/profile_runtime_source_report.jsonl"))
    parser.add_argument("--b-p0-out", type=Path, default=Path("tmp/gate_quality_audit_b_p0/b_p0_repair_plan.md"))
    parser.add_argument("--b-p0-semantic-jsonl-out", type=Path, default=Path("tmp/gate_quality_audit_b_p0/b_p0_semantic_groups.jsonl"))
    parser.add_argument("--b-p0-semantic-md-out", type=Path, default=Path("tmp/gate_quality_audit_b_p0/b_p0_semantic_groups.md"))
    args = parser.parse_args()

    v1_rows = _read_jsonl(args.v1_audit)
    v2_rows = _read_jsonl(args.v2_audit)
    runtime_rows = await build_runtime_source_rows(db_name=args.db_name, v1_rows=v1_rows, v2_rows=v2_rows)
    _write_jsonl(args.runtime_out, runtime_rows)
    write_b_p0_plan(args.b_p0_out, [("subject_gates", v1_rows), ("theme_profile_v2", v2_rows)])
    semantic_rows = build_b_p0_semantic_group_rows([("subject_gates", v1_rows), ("theme_profile_v2", v2_rows)])
    _write_jsonl(args.b_p0_semantic_jsonl_out, semantic_rows)
    write_b_p0_semantic_groups(args.b_p0_semantic_md_out, semantic_rows)
    print(
        json.dumps(
            {
                "runtime_count": len(runtime_rows),
                "runtime_out": str(args.runtime_out),
                "b_p0_out": str(args.b_p0_out),
                "b_p0_semantic_jsonl_out": str(args.b_p0_semantic_jsonl_out),
                "b_p0_semantic_md_out": str(args.b_p0_semantic_md_out),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
