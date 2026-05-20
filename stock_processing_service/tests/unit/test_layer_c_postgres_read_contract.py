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
    assert "OR COALESCE(cb.has_two_board, FALSE) = TRUE" in method


def test_layer_c_refresh_sql_does_not_replay_pool_rows_without_layer_b_or_two_board() -> None:
    method = _method_source("get_strong_watch_refresh_rows")

    assert "LEFT JOIN theme_cycle_judgement_v2 v2" in method
    assert "v2.subject_key = p.subject_key" in method
    assert "p.labels_json->>'has_two_board'" in method
    assert "COALESCE(v2.final_mainline_alive, FALSE) = TRUE" in method
    assert "COALESCE(v2.fade_confirmed, FALSE) = FALSE" in method
