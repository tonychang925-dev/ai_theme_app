#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--output-dir", default="tmp/p4_phase2_rollback")
    p.add_argument("--rto-target-minutes", type=int, default=5)
    args = p.parse_args()

    started = now_iso()

    # 模板化回滚矩阵，执行人可填实际耗时与结果。
    matrix = [
        {
            "scenario": "entry_rollback",
            "description": "入口回滚（/intel -> 稳定入口）",
            "steps": [
                "切换入口路由开关到稳定入口",
                "刷新页面并确认核心页面可访问",
                "验证回滚后无白屏/死链",
            ],
            "result": "pending",
            "rto_minutes": None,
        },
        {
            "scenario": "sse_to_feed_only",
            "description": "SSE回滚（stream -> feed-only）",
            "steps": [
                "关闭 SSE 开关",
                "确认 fallbackActive=true 且列表仍可刷新",
                "恢复 SSE 开关并确认 streamRecoveredAt 非空",
            ],
            "result": "pending",
            "rto_minutes": None,
        },
        {
            "scenario": "three_column_toggle",
            "description": "三栏开关回滚（ThreeColumnLayout）",
            "steps": [
                "关闭三栏开关，降级为稳定布局",
                "检查主题雷达/情报流/市场验证展示完整",
                "恢复三栏开关并验证联动",
            ],
            "result": "pending",
            "rto_minutes": None,
        },
    ]

    report = {
        "trade_date": args.date,
        "captured_at": started,
        "rto_target_minutes": args.rto_target_minutes,
        "matrix": matrix,
        "summary": {
            "all_passed": False,
            "max_rto_minutes": None,
            "note": "请在演练后回填 result/rto_minutes，并更新 all_passed/max_rto_minutes。",
        },
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"rollback_{args.date}.json"
    out_md = out_dir / f"rollback_{args.date}.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        f"# P4 Phase2 Rollback Drill - {args.date}",
        "",
        f"- RTO Target: <= {args.rto_target_minutes} minutes",
        f"- Captured At: {started}",
        "",
        "## Matrix",
    ]
    for idx, row in enumerate(matrix, 1):
        lines.append(f"### {idx}. {row['scenario']}")
        lines.append(f"- Description: {row['description']}")
        lines.append(f"- Result: {row['result']}")
        lines.append(f"- RTO Minutes: {row['rto_minutes']}")
        lines.append("- Steps:")
        for step in row["steps"]:
            lines.append(f"  - {step}")
        lines.append("")

    lines.extend([
        "## Acceptance",
        "- 要求：3个场景全部 `passed`，且 `max_rto_minutes <= 5`。",
    ])
    out_md.write_text("\n".join(lines), encoding="utf-8")

    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
