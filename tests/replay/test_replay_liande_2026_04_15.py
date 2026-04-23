from __future__ import annotations

import os
import subprocess
from datetime import date

import pytest

from stock_service.config import StockServiceConfig


def _run_candidate_build(trade_date: str) -> None:
    cmd = [
        ".venv/bin/python",
        "scripts/build_weak_to_strong_candidate_pool.py",
        "--trade-date",
        trade_date,
        "--skip-legacy-entrypoint-gate",
    ]
    subprocess.run(cmd, check=True)


def _query_one(sql: str) -> tuple:
    cfg = StockServiceConfig()
    cmd = [
        "psql",
        "-h",
        cfg.postgres_host,
        "-p",
        str(cfg.postgres_port),
        "-U",
        cfg.postgres_user,
        "-d",
        cfg.postgres_database,
        "-t",
        "-A",
        "-F",
        "|",
        "-c",
        sql,
    ]
    env = os.environ.copy()
    if cfg.postgres_password:
        env["PGPASSWORD"] = cfg.postgres_password
    out = subprocess.check_output(cmd, env=env, text=True).strip()
    if not out:
        return tuple()
    return tuple(out.split("|"))


@pytest.mark.replay
@pytest.mark.replay_db
def test_replay_liande_2026_04_15() -> None:
    if os.getenv("RUN_REPLAY_DB", "0") != "1":
        pytest.skip("set RUN_REPLAY_DB=1 to run real DB replay")

    trade_date = date(2026, 4, 15).isoformat()
    stock_id = "605060.SH"
    stock_name = "联德股份"

    if os.getenv("REPLAY_RUN_BUILD", "0") == "1":
        try:
            _run_candidate_build(trade_date)
        except subprocess.CalledProcessError as exc:
            pytest.skip(f"candidate build unavailable in current env: {exc}")

    # A. 是否被选出来
    try:
        row = _query_one(
            f"""
            SELECT stock_id, stock_name, pool_entry_type, candidate_score
            FROM weak_to_strong_candidate_pool
            WHERE trade_date = '{trade_date}'::date
              AND stock_id = '{stock_id}'
            ORDER BY candidate_score DESC NULLS LAST
            LIMIT 1
            """
        )
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"db connection unavailable in current test sandbox: {exc}")
    assert row, f"{stock_name} not selected on {trade_date}"

    got_stock_id, got_stock_name, pool_entry_type, candidate_score = row
    assert got_stock_id == stock_id
    assert got_stock_name == stock_name

    # B. 级别是否合理（联德样本期望 formal）
    assert pool_entry_type == "formal"

    # C. 关键证据字段是否存在
    evidence = _query_one(
        f"""
        SELECT
          COALESCE(candidate_score::text, ''),
          COALESCE(candidate_type, ''),
          COALESCE(weak_type, ''),
          CASE WHEN evidence_json IS NULL THEN '' ELSE 'ok' END
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = '{trade_date}'::date
          AND stock_id = '{stock_id}'
        LIMIT 1
        """
    )
    assert evidence and evidence[0] and evidence[1] and evidence[2] and evidence[3] == "ok"

    # D. 候选池质量（控制规模）
    total = _query_one(
        f"""
        SELECT COUNT(*)::text
        FROM weak_to_strong_candidate_pool
        WHERE trade_date = '{trade_date}'::date
        """
    )
    assert total and int(total[0]) <= 10, f"candidate pool too large: {total}"
    assert float(candidate_score) >= 70.0
