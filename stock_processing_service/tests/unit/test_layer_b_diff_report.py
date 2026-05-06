from __future__ import annotations

from stock_processing_service.application.replay.layer_b_diff_report import LayerBDiffReportBuilder


def _evidence(subject_key: str, *, leader: str, support: str = "50", red: str = "0.7") -> dict:
    return {
        "subject_key": subject_key,
        "theme_name": f"theme-{subject_key}",
        "event_strength_score": "60",
        "event_continuity_score": "45",
        "strong_event_count_7d": 1,
        "event_count_3d": 1,
        "event_count_7d": 2,
        "event_recency_days": 1,
        "leader_alive_score": leader,
        "leader_breakdown_flag": False,
        "relay_strength_score": "55",
        "front_row_survival_ratio": "1",
        "limit_up_count": 2,
        "limit_down_count": 0,
        "red_ratio": red,
        "big_drop_ratio": "0",
        "front_row_strength_score": "50",
        "theme_support_score": support,
        "break_start_pivot": False,
        "evidence_json": {
            "leader_layer": {
                "leader_score_source": "db_pool_fields_inferred",
                "front_row_limit_up_count": 2,
            },
            "kline_layer": {
                "above_ma10": True,
                "above_ma20": True,
                "kline_quality": "ok",
                "theme_ret_3d": "1.2",
                "theme_ret_5d": "2.1",
                "theme_ret_10d": "3.2",
            },
        },
    }


def _cycle(subject_key: str, *, strength: str, alive: bool, state: str = "divergence") -> dict:
    return {
        "subject_key": subject_key,
        "mainline_strength_score": strength,
        "fade_watch_score": "30",
        "fade_confirmed_score": "20",
        "divergence_score": "75",
        "repair_score": "45",
        "final_cycle_state": state,
        "final_mainline_alive": alive,
    }


def test_layer_b_diff_report_groups_alive_and_dead_subjects() -> None:
    report = LayerBDiffReportBuilder().build(
        trade_date="2026-04-15",
        stock_id="605060.SH",
        evidence_rows=[
            _evidence("alive", leader="100"),
            _evidence("leader_alive_dead", leader="80", support="20", red="0.3"),
            _evidence("leader_dead", leader="15"),
        ],
        cycle_rows=[
            _cycle("alive", strength="65", alive=True),
            _cycle("leader_alive_dead", strength="35", alive=False),
            _cycle("leader_dead", strength="20", alive=False),
        ],
    ).to_dict()

    assert report["summary"]["category_counts"] == {"A": 1, "B": 1, "C": 1}
    assert report["summary"]["best_alive_subject"]["subject_key"] == "alive"
    rows = {row["subject_key"]: row for row in report["subject_rows"]}
    assert rows["alive"]["category"] == "A"
    assert rows["leader_alive_dead"]["category"] == "B"
    assert rows["leader_dead"]["category"] == "C"
    assert "kline_support_weak" in rows["leader_alive_dead"]["diagnostic_hints"]
    assert "board_structure_weak" in rows["leader_alive_dead"]["diagnostic_hints"]
    assert rows["alive"]["leader_score_source"] == "db_pool_fields_inferred"
