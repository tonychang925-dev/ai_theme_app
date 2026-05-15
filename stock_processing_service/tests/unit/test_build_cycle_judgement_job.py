from __future__ import annotations

import asyncio
from datetime import date

import pytest

from stock_processing_service.application.jobs.build_cycle_judgement_job import BuildCycleJudgementJob


class _ReadPort:
    def __init__(self, evidence_rows: list[dict] | None = None) -> None:
        self.evidence_rows = evidence_rows or []

    async def get_all_confirmed_mainlines(self) -> list[dict]:
        return [
            {
                "subject_key": "s_main",
                "theme_name": "主线题材",
                "is_main_theme": True,
                "identity_status": "confirmed",
            }
        ]

    async def get_all_prior_alive_cycles(self, trade_date: date) -> list[dict]:
        return []

    async def get_subject_rank_daily(self, trade_date: date, limit: int = 100) -> list[dict]:
        return []

    async def get_subject_cycle_evidence_daily(
        self,
        trade_date: date,
        subject_keys: list[str] | None = None,
    ) -> list[dict]:
        if subject_keys is None:
            return []
        return [r for r in self.evidence_rows if r.get("subject_key") in set(subject_keys)]

    async def get_new_subject_rank_entries(self, trade_date: date) -> list[dict]:
        return []

    async def get_cluster_related_subjects(self, subject_keys: list[str], trade_date: date) -> list[dict]:
        return []


class _WritePort:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    async def upsert_theme_cycle_judgement_v2_rows(self, rows: list[dict]) -> int:
        self.rows.extend(rows)
        return len(rows)


def _evidence_row() -> dict:
    return {
        "subject_key": "s_main",
        "theme_name": "主线题材",
        "event_strength_score": 80,
        "event_continuity_score": 70,
        "leader_alive_score": 70,
        "relay_strength_score": 65,
        "board_score": 70,
        "theme_support_score": 70,
        "leader_breakdown_flag": False,
        "red_ratio": "0.72",
        "big_drop_ratio": "0.05",
        "limit_down_count": 0,
        "front_row_survival_ratio": "0.8",
        "break_start_pivot": False,
        "strong_event_count_7d": 2,
    }


def test_cycle_job_missing_evidence_fail_fast_without_write() -> None:
    async def _run() -> None:
        write = _WritePort()
        job = BuildCycleJudgementJob(_ReadPort(evidence_rows=[]), write)
        with pytest.raises(RuntimeError, match="missing subject cycle evidence"):
            await job.execute(date(2026, 4, 23))
        assert write.rows == []

    asyncio.run(_run())


def test_cycle_job_writes_only_evidence_driven_alive_and_audit_fields() -> None:
    async def _run() -> None:
        write = _WritePort()
        job = BuildCycleJudgementJob(_ReadPort(evidence_rows=[_evidence_row()]), write)
        result = await job.execute(date(2026, 4, 23), batch_id="b1", trace_id="t1")
        assert result.affected_rows == 1
        row = write.rows[0]
        assert row["final_mainline_alive"] is True
        assert row["final_cycle_state"] != "fade_confirmed"
        assert row["decision_path"]
        assert row["evidence_count"] == row["fade_confirmed_evidence_count"]
        assert row["evidence_json"]["decision_path"] == row["decision_path"]
        assert row["batch_id"] == "b1"
        assert row["trace_id"] == "t1"

    asyncio.run(_run())
