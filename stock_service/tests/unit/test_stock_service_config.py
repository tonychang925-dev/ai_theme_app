from __future__ import annotations

from pathlib import Path

from stock_service.config import resolve_tushare_token


def test_resolve_tushare_token_falls_back_to_env_file(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    (tmp_path / ".env.theme").write_text("TUSHARE_TOKEN=test-token-from-file\n", encoding="utf-8")

    token = resolve_tushare_token(tmp_path)

    assert token == "test-token-from-file"
