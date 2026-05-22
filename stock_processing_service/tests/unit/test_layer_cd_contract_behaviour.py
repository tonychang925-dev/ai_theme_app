from datetime import date

from stock_processing_service.application.use_cases.build_weak_to_strong_candidate import (
    BuildWeakToStrongCandidateUseCase,
)
from stock_processing_service.domain.services.strong_stock_tracking_service import (
    StrongStockTrackingService,
)


def test_layer_c_two_board_requires_at_least_two_hard_gate_hits() -> None:
    failed = StrongStockTrackingService._evaluate_strong_pool_hard_gate(
        recent_limit_up_count=1,
        final_mainline_alive=False,
        board_effect_confirmed=False,
        current_flag_today=0,
        broken_board=True,
        volume_pattern_status="",
        pullback_status="",
        ma_status="",
        pattern_labels=[],
        breakout_status="",
        position_label="",
        trend_strength_score=0.0,
        has_two_board=True,
    )
    passed = StrongStockTrackingService._evaluate_strong_pool_hard_gate(
        recent_limit_up_count=1,
        final_mainline_alive=False,
        board_effect_confirmed=False,
        current_flag_today=2,
        broken_board=False,
        volume_pattern_status="",
        pullback_status="",
        ma_status="",
        pattern_labels=[],
        breakout_status="",
        position_label="",
        trend_strength_score=0.0,
        has_two_board=True,
    )

    assert failed["pass_count"] == 1
    assert failed["passed"] is False
    assert passed["pass_count"] >= 2
    assert passed["passed"] is True


def test_layer_d_rejects_limit_up_day_before_weak_to_strong_confirmation() -> None:
    use_case = BuildWeakToStrongCandidateUseCase(read_ports=object(), write_ports=object())  # type: ignore[arg-type]

    rows = use_case.build_candidates(
        trade_date=date(2026, 5, 20),
        d1_input_rows=[
            {
                "stock_id": "000001.SZ",
                "stock_name": "样例股",
                "subject_key": "s1",
                "theme_name": "样例题材",
                "pct_chg": 9.9,
                "limit_up": True,
                "is_leader": True,
                "rank_order": 1,
                "recent_limit_up_count": 2,
                "prior7_limitup_days": 1,
                "prior7_strong_days": 1,
                "prev_day_pct_chg": 4.5,
                "watch_score": 80,
                "mainline_strength_score": 70,
                "watch_labels_json": {
                    "strong_grade": "A",
                    "support_type": "gap_support",
                    "support_score": 60,
                },
            }
        ],
    )

    assert rows == []
    assert use_case._diagnostics["d1_fail_pct_gate"] == 1
