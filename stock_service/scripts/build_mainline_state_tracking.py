#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from datetime import date, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.services.mainline_state_transition_service import MainlineStateTransitionService


def _parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception as exc:
        raise ValueError(f"invalid --trade-date: {value}") from exc


def _slice_items(items: list[dict], topn: int) -> list[dict]:
    if topn <= 0:
        return items
    return items[:topn]


async def _run(
    trade_date: date,
    skip_snapshot: bool,
    skip_transition: bool,
    skip_report: bool,
    report_topn: int,
) -> int:
    service = MainlineStateTransitionService()
    try:
        snapshot_count = 0
        transition_count = 0
        report: dict = {
            "upgrade_list": [],
            "downgrade_list": [],
            "fade_list": [],
            "flat_list": [],
        }

        if not skip_snapshot:
            snapshot_count = await service.build_daily_snapshot(trade_date)
            print(f"[OK] mainline_state.snapshot trade_date={trade_date} count={snapshot_count}")
        else:
            print("[SKIP] mainline_state.snapshot")

        if not skip_transition:
            transition_count = await service.build_transition(trade_date)
            print(f"[OK] mainline_state.transition trade_date={trade_date} count={transition_count}")
        else:
            print("[SKIP] mainline_state.transition")

        if not skip_report:
            report = await service.generate_daily_report(trade_date)
            print(
                "[OK] mainline_state.report "
                f"upgrade={len(report['upgrade_list'])} "
                f"downgrade={len(report['downgrade_list'])} "
                f"fade={len(report['fade_list'])} "
                f"flat={len(report['flat_list'])}"
            )
            display = {
                "upgrade_list": _slice_items(report["upgrade_list"], report_topn),
                "downgrade_list": _slice_items(report["downgrade_list"], report_topn),
                "fade_list": _slice_items(report["fade_list"], report_topn),
                "flat_list": _slice_items(report["flat_list"], report_topn),
            }
            print(json.dumps(display, ensure_ascii=False, indent=2))
        else:
            print("[SKIP] mainline_state.report")

        print(
            "[SUMMARY] mainline_state_tracking "
            f"trade_date={trade_date} snapshot_count={snapshot_count} "
            f"transition_count={transition_count} "
            f"upgrade={len(report['upgrade_list'])} "
            f"downgrade={len(report['downgrade_list'])} "
            f"fade={len(report['fade_list'])} "
            f"flat={len(report['flat_list'])}"
        )
        return 0
    finally:
        await service.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build mainline state daily snapshot + transition + report"
    )
    parser.add_argument("--trade-date", required=True, help="Trade date in YYYY-MM-DD")
    parser.add_argument("--skip-snapshot", action="store_true", help="Skip snapshot stage")
    parser.add_argument("--skip-transition", action="store_true", help="Skip transition stage")
    parser.add_argument("--skip-report", action="store_true", help="Skip report stage")
    parser.add_argument(
        "--report-topn",
        type=int,
        default=10,
        help="Show top N rows for each transition bucket in report output",
    )
    parser.add_argument(
        "--skip-legacy-entrypoint-gate",
        action="store_true",
        help="Skip legacy cycle entrypoint gate (for temporary diagnostics only)",
    )
    args = parser.parse_args()

    if not args.skip_legacy_entrypoint_gate:
        gate_cmd = [
            sys.executable,
            str(PROJECT_ROOT / "stock_service" / "scripts" / "check_legacy_cycle_entrypoints.py"),
        ]
        subprocess.run(gate_cmd, cwd=str(PROJECT_ROOT), check=True)
    else:
        print("[SKIP] legacy_cycle_entrypoint_gate (--skip-legacy-entrypoint-gate enabled)")

    trade_date = _parse_date(args.trade_date)
    return asyncio.run(
        _run(
            trade_date=trade_date,
            skip_snapshot=args.skip_snapshot,
            skip_transition=args.skip_transition,
            skip_report=args.skip_report,
            report_topn=max(0, args.report_topn),
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
