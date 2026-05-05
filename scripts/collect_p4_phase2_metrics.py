#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get_json(url: str, timeout: float = 10.0) -> dict:
    req = Request(url, method="GET")
    with urlopen(req, timeout=timeout) as resp:
        data = resp.read().decode("utf-8")
    obj = json.loads(data)
    return obj if isinstance(obj, dict) else {}


def _check_sse(url: str, timeout: float = 8.0) -> tuple[bool, str | None]:
    req = Request(url, method="GET", headers={"Accept": "text/event-stream"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            ctype = resp.headers.get("Content-Type", "")
            ok = "text/event-stream" in ctype
            return ok, None if ok else f"invalid content-type: {ctype}"
    except Exception as exc:
        return False, str(exc)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--date", required=True)
    p.add_argument("--session", default="all")
    p.add_argument("--type", default="all")
    p.add_argument("--output-dir", default="tmp/p4_phase2_metrics")
    args = p.parse_args()

    base = args.base_url.rstrip("/")
    q = urlencode({"date": args.date, "session": args.session, "type": args.type, "limit": "20"})
    feed_url = f"{base}/api/v2/intel/feed?{q}"
    stream_url = f"{base}/api/v2/intel/stream?{q}"

    started = datetime.utcnow().isoformat() + "Z"
    feed_ok = False
    feed_count = 0
    feed_err = None
    try:
        feed = _get_json(feed_url)
        feed_count = int(feed.get("count") or 0)
        feed_ok = True
    except Exception as exc:
        feed_err = str(exc)

    stream_ok, stream_err = _check_sse(stream_url)

    fallback_count = 0 if stream_ok else 1
    first_screen_ms = None
    linkage_pass_rate = None

    report = {
        "trade_date": args.date,
        "captured_at": started,
        "base_url": base,
        "metrics": {
            "feed_success_rate": 1.0 if feed_ok else 0.0,
            "stream_success_rate": 1.0 if stream_ok else 0.0,
            "fallback_count": fallback_count,
            "first_screen_ms": first_screen_ms,
            "linkage_pass_rate": linkage_pass_rate,
            "feed_count": feed_count,
        },
        "errors": {
            "feed_error": feed_err,
            "stream_error": stream_err,
        },
    }

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"metrics_{args.date}.json"
    out_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_file = out_dir / f"daily_{args.date}.md"
    md_file.write_text(
        "\n".join([
            f"# P4 Phase2 Daily Metrics - {args.date}",
            "",
            f"- feed_success_rate: {report['metrics']['feed_success_rate']}",
            f"- stream_success_rate: {report['metrics']['stream_success_rate']}",
            f"- fallback_count: {report['metrics']['fallback_count']}",
            f"- first_screen_ms: {report['metrics']['first_screen_ms']}",
            f"- linkage_pass_rate: {report['metrics']['linkage_pass_rate']}",
            f"- feed_count: {report['metrics']['feed_count']}",
            "",
            "## Errors",
            f"- feed_error: {report['errors']['feed_error']}",
            f"- stream_error: {report['errors']['stream_error']}",
        ]),
        encoding="utf-8",
    )

    print(str(out_file))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
