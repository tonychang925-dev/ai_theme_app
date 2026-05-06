from __future__ import annotations

from stock_processing_service.application.replay.cycle_decision_trace_report import CycleDecisionTraceReportBuilder


def test_cycle_decision_trace_detects_persisted_alive_mismatch() -> None:
    report = CycleDecisionTraceReportBuilder().build(
        trade_date="2026-04-15",
        stock_id="605060.SH",
        subject_key="9064286",
        evidence={
            "subject_key": "9064286",
            "leader_alive_score": "100.000",
            "event_strength_score": "0",
            "event_continuity_score": "43",
            "strong_event_count_7d": 0,
            "red_ratio": "0.32",
            "big_drop_ratio": "0",
            "theme_support_score": "0",
            "break_start_pivot": False,
            "snapshot_version": "replay_2026-04-15_liande_layerb_v2",
            "evidence_json": {
                "leader_layer": {
                    "leader_score_source": "db_pool_fields_inferred",
                    "leader_stock_id": "301232.SZ",
                    "leader_limit_up": True,
                },
                "kline_layer": {"kline_quality": "minimal"},
            },
        },
        cycle={
            "subject_key": "9064286",
            "mainline_strength_score": "63.368",
            "divergence_score": "96.450",
            "repair_score": "63.646",
            "fade_watch_score": "33.400",
            "fade_confirmed_score": "19.040",
            "final_cycle_state": "divergence",
            "final_mainline_alive": False,
            "source_version": "old_cycle",
            "state_machine_version": "v2",
        },
    ).to_dict()

    assert report["final_state"]["recomputed_alive_from_current_policy"] is True
    assert report["final_state"]["final_mainline_alive"] is False
    assert report["consistency"]["persisted_vs_recomputed_alive"]["mismatch"] is True
    assert report["consistency"]["version_alignment_status"] == "cycle_snapshot_version_missing"
    trace = {row["rule"]: row for row in report["alive_decision_trace"]}
    assert trace["mainline_strength"]["passed"] is True
    assert trace["leader_alive"]["passed"] is True
    assert trace["event_continuity_or_strong_event"]["passed"] is True
    assert trace["mainline_alive_rule"]["passed"] is True
    assert trace["final_state_policy"]["passed"] is True
    assert trace["persisted_alive_matches_current_policy"]["passed"] is False


def test_cycle_decision_trace_keeps_event_weak_divergence_alive_under_legacy_policy() -> None:
    report = CycleDecisionTraceReportBuilder().build(
        trade_date="2026-04-15",
        stock_id="605060.SH",
        subject_key="9064286",
        evidence={
            "subject_key": "9064286",
            "leader_alive_score": "100.000",
            "event_continuity_score": "18",
            "strong_event_count_7d": 0,
            "theme_support_score": "0",
            "break_start_pivot": True,
        },
        cycle={
            "subject_key": "9064286",
            "mainline_strength_score": "63.368",
            "final_cycle_state": "divergence",
            "final_mainline_alive": False,
        },
    ).to_dict()

    trace = {row["rule"]: row for row in report["alive_decision_trace"]}
    assert trace["event_continuity_or_strong_event"]["passed"] is False
    assert trace["mainline_alive_rule"]["passed"] is False
    assert report["final_state"]["recomputed_alive_from_current_policy"] is True
    assert report["consistency"]["persisted_vs_recomputed_alive"]["mismatch"] is True
