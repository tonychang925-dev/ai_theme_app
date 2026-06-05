from pathlib import Path


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_POSTGRES_MANAGER = _PROJECT_ROOT / "database_service" / "managers" / "postgres_manager.py"


def _method_source(method_name: str) -> str:
    source = _POSTGRES_MANAGER.read_text(encoding="utf-8")
    marker = f"    async def {method_name}("
    start = source.index(marker)
    next_method = source.find("\n    async def ", start + len(marker))
    return source[start:] if next_method == -1 else source[start:next_method]


def test_layer_c_seed_sql_requires_layer_b_alive_for_mainline_path() -> None:
    method = _method_source("get_strong_watch_seed_rows")

    assert "LEFT JOIN theme_cycle_judgement_v2 v2" in method
    assert "COALESCE(v2.final_mainline_alive, FALSE) = TRUE" in method
    assert "COALESCE(v2.fade_confirmed, FALSE) = FALSE" in method
    assert "OR COALESCE(tb.stock_code IS NOT NULL, FALSE) = TRUE" in method
    assert "recent_two_trade_days" in method
    assert "two_board_stocks" in method
    assert "two_board_recent" in method
    assert "stock_daily_snapshot" in method
    assert "mainline_registry mr2" not in method
    assert "OR COALESCE(is_main_theme, FALSE) = TRUE" not in method
    assert "确认主线跟踪池" not in method


def test_layer_c_refresh_sql_does_not_replay_pool_rows_without_layer_b_or_two_board() -> None:
    method = _method_source("get_strong_watch_refresh_rows")

    assert "LEFT JOIN theme_cycle_judgement_v2 v2" in method
    assert "v2.subject_key = p.subject_key" in method
    assert "p.labels_json->>'has_two_board'" in method
    assert "COALESCE(NULLIF(LOWER(p.source_tag), ''), '') NOT IN ('tracking_only', 'mainline_tracking')" in method
    assert "COALESCE(v2.final_mainline_alive, FALSE) = TRUE" in method
    assert "COALESCE(v2.fade_confirmed, FALSE) = FALSE" in method


def test_layer_d_sql_uses_layer_b_truth_without_recomputing_alive_state() -> None:
    method = _method_source("get_w2s_candidate_inputs")

    assert "COALESCE(mr.is_main_theme, FALSE) AS is_main_theme" in method
    assert "COALESCE(v2.fade_confirmed, w.fade_confirmed, FALSE) AS fade_confirmed" in method


def test_legacy_layer_c_read_sql_does_not_recompute_alive_state() -> None:
    method = _method_source("get_legacy_strong_watch_candidate_inputs")

    assert "COALESCE(mr.is_main_theme, FALSE) AS is_main_theme" in method
    assert "COALESCE(v2.fade_confirmed, p.fade_confirmed, FALSE) AS fade_confirmed" in method


def test_strong_watch_window_view_reads_layer_c_history_by_trade_date() -> None:
    method = _method_source("get_strong_stock_watch_view_rows")

    assert "FROM strong_stock_watch_history p" in method
    assert "p.trade_date::text AS trade_date" in method
    assert "WHERE p.trade_date IN (SELECT trade_date FROM selected_trade_dates)" in method
    assert "FROM strong_stock_watch_pool p" not in method
    assert "p.watch_start_date::text AS trade_date" not in method


def test_post_market_report_context_uses_layer_b_truth_not_state_daily() -> None:
    method = _method_source("get_post_market_report_context")

    assert "v2.final_mainline_alive" in method


def test_post_market_report_context_carries_leader_scores_for_recap_strong_section() -> None:
    method = _method_source("get_post_market_report_context")

    assert "LEFT JOIN theme_leader_candidate l" in method
    assert "l.composite_score AS leader_composite_score" in method
    assert "l.capital_score AS leader_capital_score" in method
