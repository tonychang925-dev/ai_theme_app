#!/usr/bin/env python3
"""Phase 6A producer-level smoke entrypoint.

This verifies collection, raw/structured intel persistence, stream production,
and raw company announcement rendering. It intentionally does not satisfy the
full-chain gate; use test_phase6a_full_chain_smoke.py for that.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from stock_processing_service.tests.contract.test_phase6a_smoke import main as _base_main


if __name__ == "__main__":
    if "--producer-only" not in sys.argv:
        sys.argv.append("--producer-only")
    _base_main()
