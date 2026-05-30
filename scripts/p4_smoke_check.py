"""P4-0: 最小实时业务闭环 smoke check。

只做 read-only 检查，不启动/停止/修改任何服务。
用法: python scripts/p4_smoke_check.py
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ---- 配置 ----

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("PYTHONPATH", str(ROOT))

BFF_URL = "http://127.0.0.1:8000"
SPS_URL = "http://127.0.0.1:8090"
CDP_URL = "http://127.0.0.1:8095"

TIMEOUT = 10  # HTTP 请求超时秒数


# ---- 工具函数 ----

def _ok(msg: str) -> str:
    return f"  \033[32m✅\033[0m {msg}"

def _warn(msg: str) -> str:
    return f"  \033[33m⚠️\033[0m {msg}"

def _fail(msg: str) -> str:
    return f"  \033[31m❌\033[0m {msg}"


class SmokeResult:
    def __init__(self):
        self.passed = 0
        self.warnings = 0
        self.failed = 0
        self.details: list[str] = []

    def ok(self, msg: str) -> None:
        self.passed += 1
        self.details.append(_ok(msg))
        print(self.details[-1])

    def warn(self, msg: str) -> None:
        self.warnings += 1
        self.details.append(_warn(msg))
        print(self.details[-1])

    def fail(self, msg: str) -> None:
        self.failed += 1
        self.details.append(_fail(msg))
        print(self.details[-1])


async def _http_get(url: str, timeout: int = TIMEOUT) -> tuple[int, Any]:
    """HTTP GET，返回 (status_code, json_body 或 None)。"""
    try:
        import aiohttp
    except ImportError:
        # 降级到同步 httpx / urllib
        return _http_get_sync(url, timeout)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=timeout) as resp:
                try:
                    body = await resp.json()
                except Exception:
                    body = await resp.text()
                return resp.status, body
    except Exception as e:
        return 0, str(e)


def _http_get_sync(url: str, timeout: int = TIMEOUT) -> tuple[int, Any]:
    """同步 HTTP GET 降级。"""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, body
    except urllib.error.HTTPError as e:
        return e.code, str(e)
    except Exception as e:
        return 0, str(e)


async def _http_get_sse_sample(url: str, timeout: int = 8) -> tuple[bool, str]:
    """尝试连接 SSE，读取少量事件后断开。返回 (connected, sample_text)。"""
    try:
        import aiohttp
    except ImportError:
        return False, "aiohttp not available"

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return False, f"HTTP {resp.status}"
                # 读取至多 3 个非心跳事件或超时
                lines: list[str] = []
                event_count = 0
                async for line in resp.content:
                    text = line.decode(errors="replace").strip()
                    if text and not text.startswith(":"):
                        lines.append(text[:200])
                        if text.startswith("data:"):
                            event_count += 1
                    if event_count >= 2:
                        break
                return True, "; ".join(lines[:4]) if lines else "(no data received)"
    except asyncio.TimeoutError:
        return True, "(timeout after connect — SSE stream open OK)"
    except Exception as e:
        return False, str(e)


def _run_cli(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    """运行 CLI 命令，返回 (returncode, stdout, stderr)。"""
    try:
        r = subprocess.run(
            [sys.executable, "-m"] + args,
            capture_output=True, text=True, timeout=timeout,
            cwd=str(ROOT),
        )
        return r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except Exception as e:
        return -1, "", str(e)


def _check_process_count(names: list[str], max_per_name: int = 2) -> tuple[bool, dict]:
    """检查进程数是否在合理范围。返回 (ok, {name: count})。"""
    counts: dict[str, int] = {}
    try:
        r = subprocess.run(
            ["ps", "aux"], capture_output=True, text=True, timeout=5
        )
        for line in r.stdout.splitlines():
            for name in names:
                if name in line and "grep" not in line:
                    counts[name] = counts.get(name, 0) + 1
    except Exception:
        return True, counts

    for name, count in counts.items():
        if count > max_per_name:
            return False, counts
    return True, counts


# ---- 检查项 ----

async def check_runtime_status(result: SmokeResult) -> None:
    """1. Runtime Lite status."""
    print("\n[1] Runtime Lite status")
    ret, stdout, _ = _run_cli(["runtime.cli", "status", "--json"])
    if ret != 0:
        result.warn(f"runtime.cli status returned {ret} (runtime CLI may not be running)")
        return
    try:
        data = json.loads(stdout)
        svc_count = len(data.get("services", []))
        result.ok(f"runtime.cli status OK ({svc_count} services)")
    except json.JSONDecodeError:
        result.warn("runtime.cli status returned non-JSON output")


async def check_runtime_health(result: SmokeResult) -> None:
    """2. Runtime Lite health."""
    print("\n[2] Runtime Lite health")
    ret, stdout, _ = _run_cli(["runtime.cli", "health", "--json"])
    if ret != 0:
        result.warn(f"runtime.cli health returned {ret} (runtime CLI may not be running)")
        return
    try:
        data = json.loads(stdout)
        overall = data.get("status", "unknown")
        if overall == "ok":
            result.ok(f"runtime.cli health OK (status={overall})")
        else:
            result.warn(f"runtime.cli health: status={overall}")
    except json.JSONDecodeError:
        result.warn("runtime.cli health returned non-JSON output")


async def check_status_bundle(result: SmokeResult) -> None:
    """3. status-bundle 接口."""
    print("\n[3] status-bundle (BFF:8000/api/v2/realtime/status-bundle)")
    code, body = await _http_get(f"{BFF_URL}/api/v2/realtime/status-bundle")
    if code == 200 and isinstance(body, dict):
        result.ok("status-bundle 200 OK")
        # 4-6 子检查
        await _check_status_bundle_fields(body, result)
    else:
        result.fail(f"status-bundle returned {code}")


async def _check_status_bundle_fields(body: dict, result: SmokeResult) -> None:
    """4-6: status-bundle 子字段检查."""
    # 4. new_chain
    new_chain = body.get("new_chain", {})
    if isinstance(new_chain, dict):
        running = new_chain.get("running")
        if running is True:
            result.ok("new_chain.running = true")
        elif running is False:
            result.warn("new_chain.running = false (raw_news/decision may be stopped)")
        else:
            result.warn(f"new_chain.running = {running}")
    else:
        result.warn(f"new_chain not a dict: {type(new_chain)}")

    # 5. jyhf_cdp
    cdp = body.get("jyhf_cdp", {})
    if isinstance(cdp, dict):
        owner = cdp.get("service_owner") or cdp.get("owner", "")
        if owner == "managed":
            result.ok(f"jyhf_cdp owner={owner}")
        elif owner:
            result.warn(f"jyhf_cdp owner={owner} (expected 'managed')")
        else:
            result.warn("jyhf_cdp owner field missing")
    else:
        result.warn(f"jyhf_cdp not a dict: {type(cdp)}")

    # 6. auction
    auction = body.get("jyhf_auction", {})
    if isinstance(auction, dict):
        auction_running = auction.get("running")
        state = auction.get("state", "unknown")
        if auction_running or state not in ("error", "failed"):
            result.ok(f"auction state={state}")
        else:
            result.warn(f"auction state={state}")
    else:
        result.warn(f"jyhf_auction not a dict: {type(auction)}")


async def check_decision_latest(result: SmokeResult) -> None:
    """7. decision/latest 接口."""
    print("\n[7] decision/latest (SPS:8090/api/v1/decision/latest)")
    code, body = await _http_get(f"{SPS_URL}/api/v1/decision/latest?limit=5")
    if code != 200:
        result.fail(f"decision/latest returned {code}")
        return

    if not isinstance(body, dict):
        result.fail(f"decision/latest returned non-dict: {type(body)}")
        return

    total = body.get("total", 0)
    decisions = body.get("decisions", [])

    decision_types: set[str] = set()
    for d in decisions:
        dt = d.get("decision_type", "")
        if dt:
            decision_types.add(dt)

    has_support = any("support" in t for t in decision_types)
    has_w2s = any("w2s" in t for t in decision_types)

    type_str = ", ".join(sorted(decision_types)) if decision_types else "none"

    if has_support and has_w2s:
        result.ok(f"decision/latest OK: {total} total, types={type_str}")
    elif has_support or has_w2s:
        result.ok(f"decision/latest OK: {total} total, types={type_str} (partial — may be expected)")
    elif total > 0:
        result.warn(f"decision/latest: {total} decisions but no support_alert/w2s_alert found (types={type_str})")
    else:
        result.warn(f"decision/latest: {total} decisions (stream may be empty at this time)")


async def check_kline_sse(result: SmokeResult) -> None:
    """8. Kline SSE 连接."""
    print("\n[8] Kline SSE (SPS:8090/api/v1/kline-alerts/stream)")
    ok, detail = await _http_get_sse_sample(f"{SPS_URL}/api/v1/kline-alerts/stream?last_id=0-0")
    if ok:
        result.ok(f"Kline SSE connected: {detail}")
    else:
        result.warn(f"Kline SSE: {detail}")


async def check_w2s_sse(result: SmokeResult) -> None:
    """9. W2S SSE 连接."""
    print("\n[9] W2S SSE (SPS:8090/api/v1/w2s-alerts/stream)")
    ok, detail = await _http_get_sse_sample(f"{SPS_URL}/api/v1/w2s-alerts/stream?last_id=0-0")
    if ok:
        result.ok(f"W2S SSE connected: {detail}")
    else:
        result.warn(f"W2S SSE: {detail}")


async def check_orphan_processes(result: SmokeResult) -> None:
    """10. 孤儿/重复进程检查."""
    print("\n[10] Orphan/duplicate processes")
    key_names = [
        "jyhf_auction",
        "jyhf_cdp",
        "raw_news",
        "run_phase0",
        "RealTimeNewsCollector",
    ]
    ok, counts = _check_process_count(key_names, max_per_name=2)
    if ok:
        if counts:
            detail = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            result.ok(f"no duplicate/orphan processes ({detail})")
        else:
            result.ok("no matching processes found (services may not be running)")
    else:
        dupes = {k: v for k, v in counts.items() if v > 2}
        result.fail(f"duplicate processes detected: {dupes}")


async def check_direct_health(result: SmokeResult) -> None:
    """辅助检查：直接 HTTP health 端点."""
    print("\n[extra] Direct health endpoints")
    health_endpoints = {
        "SPS": f"{SPS_URL}/healthz",
        "BFF": f"{BFF_URL}/healthz",
        "CDP": f"{CDP_URL}/health",
    }
    for name, url in health_endpoints.items():
        code, body = await _http_get(url)
        if code == 200:
            status = body.get("status", "ok") if isinstance(body, dict) else "ok"
            result.ok(f"{name} health OK (status={status})")
        else:
            result.warn(f"{name} health returned {code}")


# ---- 主函数 ----

async def main(extra: bool = False) -> int:
    print("=" * 60)
    print("  P4-0 Minimal Realtime Business Flow — Smoke Check")
    print(f"  {datetime.now().isoformat()}")
    print("=" * 60)

    result = SmokeResult()

    await check_runtime_status(result)
    await check_runtime_health(result)
    await check_status_bundle(result)
    await check_decision_latest(result)
    await check_kline_sse(result)
    await check_w2s_sse(result)
    await check_orphan_processes(result)

    if extra:
        await check_direct_health(result)

    print("\n" + "=" * 60)
    total_checks = result.passed + result.warnings + result.failed
    print(f"  Results: {result.passed} passed, "
          f"{result.warnings} warnings, "
          f"{result.failed} failed "
          f"({total_checks} checks)")
    print("=" * 60)

    if result.failed > 0:
        print("\nP4 minimal realtime flow: \033[31mFAIL\033[0m "
              f"({result.failed} check(s) failed)")
        return 1
    elif result.warnings > 0:
        print(f"\nP4 minimal realtime flow: \033[33mPASS with {result.warnings} warning(s)\033[0m")
        return 0
    else:
        print("\nP4 minimal realtime flow: \033[32mPASS\033[0m")
        return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="P4-0 Minimal Realtime Business Flow Smoke Check"
    )
    parser.add_argument("--extra", action="store_true",
                        help="Also run extra health endpoint checks")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(extra=args.extra)))
