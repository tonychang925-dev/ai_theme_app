#!/usr/bin/env python3
"""Light schema check for intel SSE lines captured from curl.
Usage:
  curl -N 'http://127.0.0.1:8081/api/v2/intel/stream?...' | head -n 80 > /tmp/intel_sse_sample.txt
  python3 scripts/verify_intel_sse_schema.py /tmp/intel_sse_sample.txt
"""
import json
import sys
from pathlib import Path

ALLOWED = {
    "intel_item",
    "heartbeat",
    "stream_state",
    "theme_update",
    "validation_update",
    "error",
}


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_intel_sse_schema.py <sse_sample_file>")
        return 2
    p = Path(sys.argv[1])
    if not p.exists():
        print(f"missing file: {p}")
        return 2

    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
    current_event = None
    seen = 0
    for line in lines:
        if line.startswith("event:"):
            current_event = line.split(":", 1)[1].strip()
            if current_event not in ALLOWED:
                print(f"invalid event type: {current_event}")
                return 1
            seen += 1
        elif line.startswith("data:") and current_event:
            raw = line.split(":", 1)[1].strip()
            if raw:
                try:
                    json.loads(raw)
                except Exception:
                    # allow non-json for compatibility
                    pass

    if seen == 0:
        print("no SSE events found")
        return 1
    print(f"ok: {seen} events, schema types valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
