"""P1 Runtime Lite CLI: status / health 命令。

用法:
    python -m runtime.cli status [--profile realtime]
    python -m runtime.cli health [--profile realtime]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime


def main():
    p = argparse.ArgumentParser(description="AlphaPilot Runtime Lite")
    p.add_argument("command", choices=["status", "health"])
    p.add_argument("--profile", default="realtime")
    p.add_argument("--json", action="store_true", help="输出 JSON 格式")
    args = p.parse_args()

    if args.command == "health":
        from runtime.health import health as run_health

        result = asyncio.run(run_health(args.profile))

        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Profile: {result['profile']}")
            print(f"Status:  {result['status']}")
            print("-" * 50)
            for name, check in result["checks"].items():
                icon = "OK" if check["status"] == "ok" else "!!"
                err = f" — {check.get('error', '')}" if check["status"] != "ok" else ""
                detail = ""
                if "pids" in check:
                    detail = f" (pids={','.join(check['pids'])})"
                elif "http_code" in check:
                    detail = f" (HTTP {check['http_code']})"
                elif "port" in check:
                    detail = f" ({check.get('host')}:{check.get('port')})"
                print(f"  [{icon}] {name}{detail}{err}")
        sys.exit(0 if result["status"] == "ok" else 1)

    elif args.command == "status":
        from runtime.health import health as run_health, load_profile

        profile = load_profile(args.profile)
        health_result = asyncio.run(run_health(args.profile))

        if args.json:
            output = {
                "profile": args.profile,
                "timestamp": datetime.now().isoformat(),
                "services": [
                    {
                        "name": svc["name"],
                        "type": svc.get("type"),
                        "required": svc.get("required", False),
                        "health": health_result["checks"].get(svc["name"], {}),
                    }
                    for svc in profile["services"]
                ],
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(f"AlphaPilot Runtime Status")
            print(f"Profile: {args.profile}")
            print(f"Time:    {datetime.now().isoformat()}")
            print("=" * 60)
            running = 0
            total = 0
            for svc in profile["services"]:
                total += 1
                check = health_result["checks"].get(svc["name"], {})
                ok = check.get("status") == "ok"
                if ok:
                    running += 1
                icon = "🟢" if ok else "🔴" if svc.get("required") else "⚪"
                req = "(必)" if svc.get("required") else ""
                print(f"  {icon} {svc['name']} {req}")
                if not ok and check.get("error"):
                    print(f"     ↳ {check['error']}")
            print("=" * 60)
            print(f"Running: {running}/{total}")
        sys.exit(0 if running == total else 1)


if __name__ == "__main__":
    main()
