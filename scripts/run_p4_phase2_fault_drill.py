#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, UTC
from pathlib import Path
from urllib.request import Request, urlopen


def _probe(url: str, timeout: float = 8.0) -> tuple[bool, str | None, dict | None]:
    req = Request(url, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
            return True, None, data if isinstance(data, dict) else {}
    except Exception as exc:
        return False, str(exc), None


def _probe_sse(url: str, timeout: float = 8.0) -> tuple[bool, str | None]:
    req = Request(url, method="GET", headers={"Accept": "text/event-stream"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            return ("text/event-stream" in ctype), None
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--date", required=True)
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--output-dir", default="tmp/p4_phase2_drill")
    args = p.parse_args()

    base = args.base_url.rstrip("/")
    feed_url = f"{base}/api/v2/intel/feed?date={args.date}&session=all&type=all&limit=20"
    stream_url = f"{base}/api/v2/intel/stream?date={args.date}&session=all&type=all&limit=20"

    started = datetime.now(UTC).isoformat()

    # Case A: baseline
    feed_ok, feed_err, feed_payload = _probe(feed_url)
    sse_ok, sse_err = _probe_sse(stream_url)

    # Case B: simulate upstream unavailable by using invalid base_url port
    broken_base = "http://127.0.0.1:65535"
    broken_feed_url = f"{broken_base}/api/v2/intel/feed?date={args.date}&session=all&type=all&limit=20"
    broken_stream_url = f"{broken_base}/api/v2/intel/stream?date={args.date}&session=all&type=all&limit=20"
    b_feed_ok, b_feed_err, _ = _probe(broken_feed_url)
    b_sse_ok, b_sse_err = _probe_sse(broken_stream_url)

    report = {
        "trade_date": args.date,
        "captured_at": started,
        "cases": {
            "baseline": {
                "feed_ok": feed_ok,
                "stream_ok": sse_ok,
                "feed_count": int((feed_payload or {}).get("count") or 0),
                "feed_error": feed_err,
                "stream_error": sse_err,
            },
            "upstream_unavailable_simulation": {
                "feed_ok": b_feed_ok,
                "stream_ok": b_sse_ok,
                "feed_error": b_feed_err,
                "stream_error": b_sse_err,
            },
        },
        "expected": {
            "baseline": "feed/stream 至少一个成功",
            "upstream_unavailable_simulation": "feed/stream 均失败，前端应进入 fallback 并记录 diagnostics",
        },
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / f"drill_{args.date}.json"
    out_md = out_dir / f"drill_{args.date}.md"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    out_md.write_text(
        "\n".join([
            f"# P4 Phase2 Fault Drill - {args.date}",
            "",
            "## Baseline",
            f"- feed_ok: {report['cases']['baseline']['feed_ok']}",
            f"- stream_ok: {report['cases']['baseline']['stream_ok']}",
            f"- feed_count: {report['cases']['baseline']['feed_count']}",
            f"- feed_error: {report['cases']['baseline']['feed_error']}",
            f"- stream_error: {report['cases']['baseline']['stream_error']}",
            "",
            "## Upstream Unavailable Simulation",
            f"- feed_ok: {report['cases']['upstream_unavailable_simulation']['feed_ok']}",
            f"- stream_ok: {report['cases']['upstream_unavailable_simulation']['stream_ok']}",
            f"- feed_error: {report['cases']['upstream_unavailable_simulation']['feed_error']}",
            f"- stream_error: {report['cases']['upstream_unavailable_simulation']['stream_error']}",
            "",
            "## Acceptance Check",
            "- 前端截图/录屏需补充：fallbackActive=true、fallbackReason 非空、恢复后 streamRecoveredAt 非空",
        ]),
        encoding="utf-8",
    )

    print(str(out_json))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
