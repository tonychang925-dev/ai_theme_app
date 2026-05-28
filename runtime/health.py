"""P1 Runtime Lite: 健康检查。"""
from __future__ import annotations

import asyncio
import socket
import subprocess
from typing import Any

import httpx
import yaml


def load_profile(name: str) -> dict[str, Any]:
    path = __import__("pathlib").Path(__file__).resolve().parent / "profiles" / f"{name}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Profile not found: {path}")
    return yaml.safe_load(path.read_text())


async def check_tcp(host: str, port: int, timeout: float = 3.0) -> dict:
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
        writer.close()
        await writer.wait_closed()
        return {"status": "ok", "host": host, "port": port}
    except Exception as exc:
        return {"status": "error", "host": host, "port": port, "error": str(exc)}


async def check_http(url: str, timeout: float = 5.0) -> dict:
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as c:
            r = await c.get(url)
            return {"status": "ok", "url": url, "http_code": r.status_code}
    except Exception as exc:
        return {"status": "error", "url": url, "error": str(exc)}


async def check_process(pattern: str) -> dict:
    try:
        result = subprocess.run(
            ["pgrep", "-f", pattern], capture_output=True, text=True, timeout=5
        )
        pids = [p for p in result.stdout.strip().split("\n") if p]
        if pids:
            return {"status": "ok", "pattern": pattern, "pids": pids}
        return {"status": "error", "pattern": pattern, "error": "no matching process"}
    except Exception as exc:
        return {"status": "error", "pattern": pattern, "error": str(exc)}


async def check_service(svc: dict) -> dict:
    hc = svc.get("health", {})
    htype = hc.get("type", "tcp")

    if htype == "tcp":
        result = await check_tcp(hc["host"], hc["port"])
    elif htype == "http":
        result = await check_http(hc["url"])
    elif htype == "process":
        result = await check_process(hc["pattern"])
    else:
        result = {"status": "unknown", "error": f"unknown health type: {htype}"}

    result["service"] = svc["name"]
    result["required"] = svc.get("required", False)
    return result


async def health(profile_name: str = "realtime") -> dict:
    profile = load_profile(profile_name)
    tasks = [check_service(svc) for svc in profile["services"]]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    checks = {}
    all_ok = True
    for r in results:
        if isinstance(r, Exception):
            continue
        name = r.pop("service", "unknown")
        required = r.pop("required", False)
        checks[name] = r
        if required and r["status"] != "ok":
            all_ok = False

    return {
        "profile": profile_name,
        "status": "ok" if all_ok else "degraded",
        "checks": checks,
    }
