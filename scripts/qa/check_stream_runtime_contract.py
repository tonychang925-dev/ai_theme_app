#!/usr/bin/env python3
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "tmp" / "p3_stream_runtime_contract_report.json"
REQUIRED_FIELDS = [
    "event_id",
    "event_name",
    "trade_date",
    "batch_id",
    "trace_id",
    "producer",
    "occurred_at",
    "payload_version",
    "payload",
]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stock_processing_service.contracts.events.event_envelope import StockProcessingEventEnvelope


def main() -> int:
    parser = argparse.ArgumentParser(description="P3 stream runtime contract checker")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="json report path")
    parser.add_argument("--strict", action="store_true", help="exit non-zero on contract mismatch")
    args = parser.parse_args()

    actual_fields = [f.name for f in dataclasses.fields(StockProcessingEventEnvelope)]
    missing = [name for name in REQUIRED_FIELDS if name not in actual_fields]
    extra = [name for name in actual_fields if name not in REQUIRED_FIELDS]

    report = {
        "task": "P3.phase1-T09",
        "required_fields": REQUIRED_FIELDS,
        "actual_fields": actual_fields,
        "missing": missing,
        "extra": extra,
        "compatible": len(missing) == 0,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[stream-contract] compatible={report['compatible']} missing={len(missing)} extra={len(extra)}")
    print(f"[stream-contract] report={output}")
    if args.strict and not report["compatible"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
