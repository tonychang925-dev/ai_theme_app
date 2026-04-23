#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="统一执行盘后复盘所需日采集：久赢恒丰题材日采集 + Tushare 日K线同步"
    )
    parser.add_argument("--trade-date", required=True, help="交易日 YYYY-MM-DD")
    parser.add_argument("--jyhf-token", default=os.getenv("JYHF_AUTH_TOKEN", ""), help="久赢 token，可为空时走环境变量/mitmproxy 捕获文件")
    parser.add_argument("--tushare-token", default=os.getenv("TUSHARE_TOKEN", ""), help="Tushare token")
    parser.add_argument("--months", type=int, default=6, help="Tushare K线回溯月数，默认 6")
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 个题材/股票，便于验证")
    parser.add_argument("--pause-seconds", type=float, default=0.2, help="Tushare 单股票下载节流秒数")
    parser.add_argument("--resume", action="store_true", help="Tushare K线同步启用断点续跑")
    parser.add_argument("--skip-existing", action="store_true", help="Tushare K线已存在则跳过")
    parser.add_argument("--write-cursor", action="store_true", help="久赢采集后更新本地 cursor 快照")
    parser.add_argument("--skip-jyhf", action="store_true", help="跳过久赢股票快照采集")
    parser.add_argument("--skip-tushare", action="store_true", help="跳过 Tushare 日K线同步")
    parser.add_argument("--skip-legacy-entrypoint-gate", action="store_true", help="跳过 legacy 周期入口扫描门禁（仅排障使用）")
    return parser


def _run_step(name: str, cmd: list[str], env: dict[str, str] | None = None) -> None:
    print(f"[STEP] {name}")
    print(f"[CMD] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=str(PROJECT_ROOT), env=env, check=True)


def main() -> int:
    args = build_parser().parse_args()
    python = str(PROJECT_ROOT / ".venv" / "bin" / "python")

    env = os.environ.copy()
    if args.jyhf_token:
        env["JYHF_AUTH_TOKEN"] = args.jyhf_token
    if args.tushare_token:
        env["TUSHARE_TOKEN"] = args.tushare_token

    if not args.skip_legacy_entrypoint_gate:
        gate_cmd = [
            python,
            str(PROJECT_ROOT / "stock_service" / "scripts" / "check_legacy_cycle_entrypoints.py"),
        ]
        _run_step("legacy_cycle_entrypoint_gate", gate_cmd, env=env)
    else:
        print("[SKIP] legacy_cycle_entrypoint_gate (--skip-legacy-entrypoint-gate enabled)")

    if not args.skip_jyhf:
        list_cmd = [
            python,
            str(PROJECT_ROOT / "sync_jyhf_to_local.py"),
            "--types",
            "lists",
        ]
        _run_step("jyhf_lists_sync", list_cmd, env=env)

        jyhf_cmd = [
            python,
            str(PROJECT_ROOT / "sync_jyhf_to_local.py"),
            "--use-latest-list-subjects",
            "--types",
            "stock_details",
            "--trade-date",
            args.trade_date,
        ]
        if args.limit > 0:
            jyhf_cmd.extend(["--limit", str(args.limit)])
        if args.write_cursor:
            jyhf_cmd.append("--write-cursor")
        _run_step("jyhf_stock_daily_sync", jyhf_cmd, env=env)

    if not args.skip_tushare:
        tushare_cmd = [
            python,
            str(PROJECT_ROOT / "scripts" / "sync_tushare_kline_local.py"),
            "--token",
            args.tushare_token or env.get("TUSHARE_TOKEN", ""),
            "--from-jyhf-universe",
            "--end-date",
            args.trade_date,
            "--months",
            str(args.months),
            "--pause-seconds",
            str(args.pause_seconds),
        ]
        if args.limit > 0:
            tushare_cmd.extend(["--limit", str(args.limit)])
        if args.resume:
            tushare_cmd.append("--resume")
        if args.skip_existing:
            tushare_cmd.append("--skip-existing")
        _run_step("tushare_kline_sync", tushare_cmd, env=env)

    print(f"[OK] completed source collection for trade_date={args.trade_date}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
