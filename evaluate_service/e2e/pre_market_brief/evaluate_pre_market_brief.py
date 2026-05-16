from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[3]))
    from evaluate_service.e2e.pre_market_brief.common import read_jsonl, write_json
else:
    from .common import read_jsonl, write_json

ALIAS_MAP: dict[str, list[str]] = {
    "AI/AR眼镜": ["AI/AR眼镜", "AI智能眼镜", "AR眼镜", "智能眼镜", "XR眼镜"],
    "SpaceX": ["SpaceX", "星链", "商业航天", "卫星互联网", "星舰"],
    "可控核聚变": ["可控核聚变", "核聚变", "人造太阳"],
    "对日制裁": ["对日制裁", "中日关系", "出口管制", "反制日本"],
    "稀土永磁": ["稀土永磁", "稀土", "中重稀土", "稀土出口管制"],
}


def _matches_gold(gold: str, candidate: str | None) -> bool:
    if not gold or not candidate:
        return False
    aliases = ALIAS_MAP.get(gold, [gold])
    return any(alias and (alias in candidate or candidate in alias) for alias in aliases)


def _load_snapshot(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "payload" in payload and isinstance(payload["payload"], dict):
        return payload["payload"]
    return payload if isinstance(payload, dict) else {}


def evaluate(
    *,
    gold_path: Path,
    trace_path: Path,
    snapshot_path: Path | None,
    out_dir: Path,
) -> dict[str, Any]:
    gold_rows = read_jsonl(gold_path)
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    snapshot = _load_snapshot(snapshot_path)
    gold_by_case = {row["case_id"]: row["gold_theme_name"] for row in gold_rows}

    evaluated_rows: list[dict[str, Any]] = []
    primary_hits = 0
    related_hits = 0
    recall3_hits = 0
    recall5_hits = 0
    human_review_count = 0
    unknown_count = 0

    for row in trace.get("rows", []):
        case_id = row.get("case_id")
        gold = gold_by_case.get(case_id)
        if not gold:
            continue
        primary_name = row.get("primary_theme_name")
        related_names = [name for name in row.get("related_theme_names", []) if name]
        theme_names = [name for name in [primary_name, *related_names] if name]
        primary_hit = _matches_gold(gold, primary_name)
        related_hit = any(_matches_gold(gold, name) for name in related_names)
        recall3_hit = any(_matches_gold(gold, name) for name in theme_names[:3])
        recall5_hit = any(_matches_gold(gold, name) for name in theme_names[:5])
        status = "unknown"
        if primary_hit:
            status = "exact_or_alias_primary"
        elif related_hit:
            status = "alias_related"
        elif row.get("review_status"):
            status = "human_review"
            human_review_count += 1
        elif not theme_names:
            unknown_count += 1
        primary_hits += int(primary_hit)
        related_hits += int(related_hit)
        recall3_hits += int(recall3_hit)
        recall5_hits += int(recall5_hit)
        evaluated_rows.append(
            {
                "case_id": case_id,
                "gold_theme_name": gold,
                "primary_theme_name": primary_name,
                "related_theme_names": related_names,
                "status": status,
            }
        )

    total = len(evaluated_rows)
    sections = snapshot.get("sections") or {}
    diagnostics = snapshot.get("diagnostics") or {}
    accuracy_report = {
        "total": total,
        "primary_hit_count": primary_hits,
        "related_hit_count": related_hits,
        "theme_set_recall_at_3_count": recall3_hits,
        "theme_set_recall_at_5_count": recall5_hits,
        "primary_hit_rate": _rate(primary_hits, total),
        "related_hit_rate": _rate(related_hits, total),
        "theme_set_recall@3": _rate(recall3_hits, total),
        "theme_set_recall@5": _rate(recall5_hits, total),
        "human_review_count": human_review_count,
        "unknown_count": unknown_count,
        "brief_major_event_count": len(sections.get("major_events") or []),
        "brief_theme_count": len(sections.get("matched_themes") or []),
        "brief_opportunity_count": len(sections.get("event_driven_opportunities") or []),
        "diagnostics": diagnostics,
    }
    stock_report = {
        "brief_opportunity_count": accuracy_report["brief_opportunity_count"],
        "opportunity_count": diagnostics.get("opportunity_count", accuracy_report["brief_opportunity_count"]),
    }
    write_json(out_dir / "accuracy_report.json", accuracy_report)
    write_json(out_dir / "stock_candidate_report.json", stock_report)
    _write_confusion(out_dir / "confusion_matrix.csv", evaluated_rows)
    _write_summary(out_dir / "summary.md", accuracy_report, trace.get("counts", {}))
    return accuracy_report


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def _write_confusion(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["case_id", "gold_theme_name", "primary_theme_name", "related_theme_names", "status"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "related_theme_names": "|".join(row.get("related_theme_names") or [])})


def _write_summary(path: Path, report: dict[str, Any], trace_counts: dict[str, Any]) -> None:
    lines = [
        "# 盘前必读 E2E Summary",
        "",
        f"- 测试库: stock_data",
        f"- 注入/期望数量: {trace_counts.get('expected_input_count', 0)}",
        f"- news_raw_count: {trace_counts.get('news_raw_count', 0)}",
        f"- news_event_count: {trace_counts.get('news_event_count', 0)}",
        f"- event_subject_map_count: {trace_counts.get('event_subject_map_count', trace_counts.get('event_theme_map_count', 0))}",
        f"- review_queue_count: {trace_counts.get('review_queue_count', 0)}",
        f"- primary_hit_rate: {report['primary_hit_rate']}",
        f"- related_hit_rate: {report['related_hit_rate']}",
        f"- theme_set_recall@5: {report['theme_set_recall@5']}",
        f"- brief_theme_count: {report['brief_theme_count']}",
        f"- brief_opportunity_count: {report['brief_opportunity_count']}",
        f"- 是否通过基础门禁: {_base_gate_passed(report, trace_counts)}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _base_gate_passed(report: dict[str, Any], trace_counts: dict[str, Any]) -> bool:
    expected = int(trace_counts.get("expected_input_count") or 0)
    return (
        expected > 0
        and int(trace_counts.get("news_raw_count") or 0) >= expected
        and int(trace_counts.get("news_event_count") or 0) >= max(1, int(expected * 0.95))
        and report.get("brief_theme_count", 0) > 0
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="评估盘前必读 E2E 题材召回与报告快照质量。")
    parser.add_argument("--gold-labels", required=True)
    parser.add_argument("--trace", required=True)
    parser.add_argument("--snapshot")
    parser.add_argument("--out-dir", required=True)
    args = parser.parse_args()

    result = evaluate(
        gold_path=Path(args.gold_labels),
        trace_path=Path(args.trace),
        snapshot_path=Path(args.snapshot) if args.snapshot else None,
        out_dir=Path(args.out_dir),
    )
    print(result)


if __name__ == "__main__":
    main()
