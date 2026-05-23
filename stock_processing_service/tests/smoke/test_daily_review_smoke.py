"""DailyReview 重构第一阶段 smoke test。

覆盖：
- /api/v1/theme_workspace/{sk} 双路径
- /api/v2/daily-review?date=YYYY-MM-DD
- theme_reviews length <= 20
- diagnostics.coverage.snapshot_status
"""

import subprocess
import json
import sys

SPS_BASE = "http://127.0.0.1:8090"
WEBAPP_BASE = "http://127.0.0.1:8000"
SUBJECT_KEY = "9019807"
TRADE_DATE = "2026-05-22"


def _get_json(url: str) -> dict:
    result = subprocess.run(
        ["curl", "-s", url],
        capture_output=True, text=True, timeout=15,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"curl failed for {url}: {result.stderr}")
    return json.loads(result.stdout)


def test_theme_workspace_with_underscore():
    url = f"{SPS_BASE}/api/v1/theme_workspace/{SUBJECT_KEY}"
    data = _get_json(url)
    assert data.get("subject_key") == SUBJECT_KEY, f"bad subject_key: {data}"
    diag = data.get("diagnostics") or {}
    assert diag.get("partial") is False, f"partial=True: {diag}"


def test_theme_workspace_without_underscore():
    url = f"{SPS_BASE}/api/v1/theme/workspace/{SUBJECT_KEY}"
    data = _get_json(url)
    assert data.get("subject_key") == SUBJECT_KEY, f"bad subject_key: {data}"


def test_daily_review_theme_count():
    url = f"{WEBAPP_BASE}/api/v2/daily-review?date={TRADE_DATE}"
    data = _get_json(url)
    trs = data.get("theme_reviews") or []
    assert len(trs) <= 20, f"theme_reviews count {len(trs)} exceeds 20"
    assert len(trs) > 0, "theme_reviews is empty"


def test_daily_review_coverage():
    url = f"{WEBAPP_BASE}/api/v2/daily-review?date={TRADE_DATE}"
    data = _get_json(url)
    cov = (data.get("diagnostics") or {}).get("coverage") or {}
    status = cov.get("snapshot_status")
    assert status in ("complete", "partial"), f"bad snapshot_status: {status}"
    assert isinstance(cov.get("cycle_joined_count"), int)
    assert isinstance(cov.get("missing_cycle_subject_keys"), list)


def test_daily_review_fields():
    url = f"{WEBAPP_BASE}/api/v2/daily-review?date={TRADE_DATE}"
    data = _get_json(url)
    trs = data.get("theme_reviews") or []
    if not trs:
        return
    t = trs[0]
    required = [
        "subject_key", "theme_name", "theme_stage",
        "mainline_strength_score", "fade_risk_score",
        "final_cycle_state", "final_mainline_alive",
        "leader_stocks", "event_chain", "diagnostics",
    ]
    for field in required:
        assert field in t, f"missing field '{field}' in theme_review"


def test_theme_workspace_leader_stocks_enriched():
    url = f"{SPS_BASE}/api/v1/theme_workspace/{SUBJECT_KEY}"
    data = _get_json(url)
    ls = (data.get("analytics") or {}).get("leader_stocks") or []
    if ls:
        stock = ls[0]
        enriched_fields = [
            "stock_name", "pct_chg", "main_net_inflow",
        ]
        for f in enriched_fields:
            assert f in stock, f"leader_stock missing '{f}'"


if __name__ == "__main__":
    failures = []
    for name, fn in list(globals().items()):
        if not name.startswith("test_"):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as e:
            print(f"FAIL {name}: {e}")
            failures.append(name)

    if failures:
        print(f"\n{failures}")
        sys.exit(1)
    else:
        print("\nAll smoke tests passed.")
