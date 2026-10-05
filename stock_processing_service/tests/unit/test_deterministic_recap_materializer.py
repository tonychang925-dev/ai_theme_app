from __future__ import annotations

import asyncio
import unittest
from datetime import date
from types import SimpleNamespace

from stock_processing_service.application.services.deterministic_recap_materializer import (
    DeterministicRecapMaterializer,
)


class _FakeJob:
    def __init__(self) -> None:
        self.calls = []
        self.last_materialized_snapshot = SimpleNamespace(recap_doc={"daily_review_v2": {}})

    async def execute(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            status="ok",
            affected_rows=1,
            metrics={"module_coverage": 10},
            warnings=[],
        )


class DeterministicRecapMaterializerTests(unittest.TestCase):
    def test_dry_run_is_single_date_read_only(self):
        job = _FakeJob()
        result = asyncio.run(
            DeterministicRecapMaterializer(job).materialize(
                date(2026, 9, 24), dry_run=True
            )
        )
        self.assertEqual(result["status"], "dry_run")
        self.assertEqual(result["write_scope"], [])
        self.assertFalse(result["llm_call"])
        self.assertFalse(result["derived_rebuild"])
        self.assertEqual(job.calls[0]["write_snapshot"], False)
        self.assertEqual(job.calls[0]["deterministic_only"], True)
        self.assertEqual(job.calls[0]["skip_prereqs"], True)
        self.assertEqual(job.calls[0]["skip_layer_c"], True)

    def test_write_scope_is_only_recap_snapshot(self):
        job = _FakeJob()
        result = asyncio.run(
            DeterministicRecapMaterializer(job).materialize(date(2026, 9, 23))
        )
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["write_scope"], ["post_market_recap_snapshot"])
        self.assertEqual(job.calls[0]["write_snapshot"], True)

    def test_required_source_failure_stays_fail_closed(self):
        job = _FakeJob()

        async def failed_execute(**kwargs):
            job.calls.append(kwargs)
            return SimpleNamespace(
                status="failed_precondition",
                affected_rows=0,
                metrics={"missing_tables": ["theme_cycle_judgement_v2"]},
                warnings=["required source missing"],
            )

        job.execute = failed_execute
        result = asyncio.run(
            DeterministicRecapMaterializer(job).materialize(date(2026, 9, 23))
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "failed_precondition")
        self.assertEqual(result["affected_rows"], 0)
        self.assertEqual(result["write_scope"], [])

    def test_idempotent_result_is_not_reported_as_new_success(self):
        job = _FakeJob()

        async def skipped_execute(**kwargs):
            job.calls.append(kwargs)
            return SimpleNamespace(
                status="skipped_idempotent",
                affected_rows=0,
                metrics={"job_key": "already-completed"},
                warnings=["idempotency_key_already_completed"],
            )

        job.execute = skipped_execute
        result = asyncio.run(
            DeterministicRecapMaterializer(job).materialize(date(2026, 9, 23))
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "skipped_idempotent")
        self.assertEqual(result["affected_rows"], 0)


if __name__ == "__main__":
    unittest.main()
