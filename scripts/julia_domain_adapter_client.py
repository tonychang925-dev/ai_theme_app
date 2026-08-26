#!/usr/bin/env python3
"""Standalone HTTP client for ai_theme_app Julia Domain Adapter.

Uses only Python stdlib. Does not import Julia Core or ai_theme_app packages.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Call ai_theme_app Julia Domain Adapter HTTP endpoint")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="ai_theme_app base URL")
    parser.add_argument("--operation", default="market.snapshot", choices=("market.snapshot", "market.alerts"))
    parser.add_argument("--trade-date", default="")
    parser.add_argument("--correlation-id", default="standalone-corr-001")
    args = parser.parse_args()

    request = {
        "operation": args.operation,
        "arguments": {"trade_date": args.trade_date} if args.trade_date else {},
        "correlation_id": args.correlation_id,
        "idempotency_key": "standalone-idem-001",
        "requested_at": "",
        "schema_version": "1.0",
        "trace_metadata": {},
    }
    data = json.dumps(request).encode("utf-8")
    http_request = urllib.request.Request(
        args.base_url.rstrip("/") + "/adapter/v1/execute",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_request, timeout=10) as response:  # noqa: S310 - caller-provided local service URL
        sys.stdout.write(response.read().decode("utf-8"))
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
