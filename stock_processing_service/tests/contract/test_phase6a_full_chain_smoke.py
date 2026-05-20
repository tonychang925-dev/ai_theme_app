#!/usr/bin/env python3
"""Phase 6A strict full-chain smoke entrypoint.

ThemeProcessor and DecisionExecutor must be running before this check. The
base smoke now fails if intel events do not reach event_subject_map.
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from stock_processing_service.tests.contract.test_phase6a_smoke import main


if __name__ == "__main__":
    main()
