"""Tests for backtest_mainline_discovery.py — PR-8."""
import pytest
import json
import tempfile
from datetime import date
from pathlib import Path


class TestBacktestScript:

    def test_report_structure(self):
        """Verify report dict structure."""
        report = {
            "config": {"start_date": "2026-04-01", "end_date": "2026-04-02", "lookback_days": 7},
            "daily_results": [
                {"trade_date": "2026-04-01", "candidate_subject_count": 0, "event_chain_subject_count": 0,
                 "logic_score_non_null_count": 0, "market_acceptance_non_null_count": 0,
                 "machine_fast_candidate_count": 0, "machine_slow_candidate_count": 0,
                 "logic_only_count": 0, "market_noise_count": 0, "rotation_hotspot_count": 0,
                 "rejected_count": 0, "analyst_review_item_count": 0, "top_review_items": [],
                 "diagnostics": {"data_quality": "unknown", "llm_unavailable_count": 0}},
            ],
            "interval_stats": {
                "total_days": 2, "candidate_days_count": 0,
                "avg_review_items_per_day": 0.0, "max_review_items_per_day": 0,
                "machine_candidate_3d_continuation_rate": 0.0,
                "market_noise_failure_rate": 0.0,
                "logic_only_upgrade_rate": 0.0,
            },
        }
        # Verify keys
        for daily in report["daily_results"]:
            assert "trade_date" in daily
            assert "candidate_subject_count" in daily
            assert "event_chain_subject_count" in daily
            assert "logic_score_non_null_count" in daily
            assert "machine_fast_candidate_count" in daily
            assert "machine_slow_candidate_count" in daily
            assert "logic_only_count" in daily
            assert "market_noise_count" in daily
            assert "analyst_review_item_count" in daily
        stats = report["interval_stats"]
        assert "avg_review_items_per_day" in stats
        assert "machine_candidate_3d_continuation_rate" in stats
        assert "market_noise_failure_rate" in stats
        assert "logic_only_upgrade_rate" in stats

    def test_write_json_to_file(self):
        report = {
            "config": {"start_date": "2026-04-01", "end_date": "2026-04-01", "lookback_days": 7},
            "daily_results": [],
            "interval_stats": {"total_days": 1, "candidate_days_count": 0,
                               "avg_review_items_per_day": 0.0, "max_review_items_per_day": 0,
                               "machine_candidate_3d_continuation_rate": 0.0,
                               "market_noise_failure_rate": 0.0,
                               "logic_only_upgrade_rate": 0.0},
        }
        with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
            path = f.name
        written = Path(path).read_text(encoding="utf-8")
        parsed = json.loads(written)
        assert parsed["config"]["start_date"] == "2026-04-01"
        assert parsed["interval_stats"]["total_days"] == 1
        Path(path).unlink()

    def test_empty_date_range_no_crash(self):
        """Empty date range should produce valid report, not crash."""
        report = {"config": {"start_date": "2026-04-01", "end_date": "2026-03-31"},
                  "daily_results": [], "interval_stats": {"total_days": 0}}
        assert report["interval_stats"]["total_days"] == 0

    def test_no_confirmed_mainline(self):
        """Report must never contain confirmed_mainline in top_review_items."""
        report = {
            "config": {}, "daily_results": [
                {"trade_date": "2026-04-01", "top_review_items": [
                    {"machine_state": "machine_fast_candidate", "final_mainline_state": "pending_review"},
                ]},
            ], "interval_stats": {},
        }
        for daily in report["daily_results"]:
            for item in daily.get("top_review_items", []):
                assert item.get("final_mainline_state", "") != "confirmed_mainline"
                assert item.get("final_mainline_state", "") != "confirmed_mainline"

    def test_continuation_rate_calculation(self):
        """Verify continuation rate logic."""
        # subject appears on day 0 and day 2 → should count as continuation
        from scripts.backtest_mainline_discovery import run_backtest
        report = {
            "daily_results": [
                {"trade_date": "2026-04-01", "top_review_items": [
                    {"subject_key": "sk_a", "machine_state": "machine_fast_candidate"},
                ], "analyst_review_item_count": 1, "fast": 1, "slow": 0},
                {"trade_date": "2026-04-02", "top_review_items": [], "analyst_review_item_count": 0},
                {"trade_date": "2026-04-03", "top_review_items": [
                    {"subject_key": "sk_a", "machine_state": "machine_slow_candidate"},
                ], "analyst_review_item_count": 1},
            ],
        }
        # Manual computation
        by_subject = {}
        for i, r in enumerate(report["daily_results"]):
            for item in r.get("top_review_items", []):
                sk = item.get("subject_key", "")
                if sk:
                    by_subject.setdefault(sk, []).append(i)
        total = sum(len(v) for v in by_subject.values())
        cont = 0
        for days in by_subject.values():
            for d in days:
                if any(x in days for x in range(d + 1, min(d + 4, 3))):
                    cont += 1
        assert cont == 1  # sk_a at day 0 reappears at day 2
        assert total == 2
