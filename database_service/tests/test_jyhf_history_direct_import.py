from datetime import date
import sys
import types

import pytest

from cdp_jyhf_collector import get_existing_db_counts
from database_service.scripts.import_jyhf_history_incremental import build_rows_from_records


def test_build_rows_from_cdp_snake_case_records_generates_stable_rank_id():
    records = [
        {
            "subject_key": "9012345",
            "subject_name": "机器人",
            "rank_date": "2026-05-30",
            "description": "入选 4 次",
            "heat": 4,
            "heat_name": "热",
            "pct_chg": 0,
            "his_pct_chg": 0,
            "source_type": "jyhf_history",
            "source_system": "jyhf",
            "batch_id": "cdp_jyhf_20260530",
        }
    ]

    history_rows, rank_rows = build_rows_from_records(records, "cdp_jyhf_20260530")
    history_rows_again, _ = build_rows_from_records(records, "cdp_jyhf_20260530")

    assert len(history_rows) == 1
    assert len(rank_rows) == 1
    assert history_rows[0][0] == "9012345"
    assert history_rows[0][1] == history_rows_again[0][1]
    assert history_rows[0][2] == date(2026, 5, 30)
    assert history_rows[0][11] == "jyhf_history"
    assert rank_rows[0][0] == "9012345"
    assert rank_rows[0][1] == date(2026, 5, 30)
    assert rank_rows[0][8] == "jyhf"


def test_build_rows_from_legacy_camel_case_records_keeps_source_rank_id():
    records = [
        {
            "subjectId": "9012345",
            "subjectRankId": 998877,
            "rankDate": "2026-05-30",
            "subjectName": "机器人",
            "description": "legacy",
            "heat": 2,
            "heatName": "温",
            "pctChg": 1.25,
            "hisPctChg": 0.5,
            "red": True,
            "sort": 3,
        }
    ]

    history_rows, rank_rows = build_rows_from_records(records, "legacy_batch")

    assert history_rows[0][0] == "9012345"
    assert history_rows[0][1] == 998877
    assert history_rows[0][3] == "机器人"
    assert history_rows[0][7] == 1.25
    assert history_rows[0][10] == 3
    assert rank_rows[0][2] == 2


@pytest.mark.asyncio
async def test_get_existing_db_counts_checks_database_only(monkeypatch):
    queries = []

    class _Conn:
        async def fetchval(self, sql, *args):
            queries.append(sql)
            if "subject_rank_daily') IS NOT NULL" in sql:
                return True
            if "subject_history_staging') IS NOT NULL" in sql:
                return True
            if "FROM subject_rank_daily" in sql:
                return 7
            if "FROM subject_history_staging" in sql:
                return 11
            return None

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class _Pool:
        def acquire(self):
            return _Acquire()

    class _Manager:
        def __init__(self, config):
            self.pool = _Pool()

        async def connect(self):
            return None

        async def disconnect(self):
            return None

    fake_postgres_manager = types.ModuleType("database_service.managers.postgres_manager")
    fake_postgres_manager.PostgresDatabaseManager = _Manager
    monkeypatch.setitem(sys.modules, "database_service.managers.postgres_manager", fake_postgres_manager)

    counts = await get_existing_db_counts("2026-05-29")

    assert counts == {"rank_rows": 7, "history_rows": 11}
    assert not any("theme_data_complete" in sql for sql in queries)
