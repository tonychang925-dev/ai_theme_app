from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.replay import (
    ReplayCase,
    ReplayCaseLoader,
    ReplayLayerManifest,
    ReplayMode,
    ReplayRunner,
)
from stock_processing_service.application.replay.replay_manifest import InMemoryReplayManifestStore
from stock_processing_service.contracts.dto import BuildResult
from stock_processing_service.infrastructure.gateway_adapters.replay_manifest_gateway_adapter import (
    ReplayManifestGatewayAdapter,
)


class _FakeJob:
    def __init__(self, name: str, affected_rows: int = 1) -> None:
        self.name = name
        self.affected_rows = affected_rows
        self.calls: list[tuple[date, str, str, str]] = []

    async def execute(self, trade_date: date, snapshot_version: str, batch_id: str, trace_id: str) -> BuildResult:
        self.calls.append((trade_date, snapshot_version, batch_id, trace_id))
        return BuildResult(
            name=self.name,
            trade_date=trade_date.isoformat(),
            affected_rows=self.affected_rows,
            status="ok",
            batch_id=batch_id,
            trace_id=trace_id,
        )


@pytest.mark.asyncio
async def test_replay_runner_rebuild_feature_runs_only_evidence_daily_recap() -> None:
    store = InMemoryReplayManifestStore()
    identity = _FakeJob("identity")
    evidence = _FakeJob("evidence", affected_rows=3)
    daily = _FakeJob("daily", affected_rows=5)
    recap = _FakeJob("recap", affected_rows=1)
    runner = ReplayRunner(
        manifest_store=store,
        jobs={
            "identity": identity,
            "evidence": evidence,
            "daily": daily,
            "recap": recap,
        },
        algorithm_versions={
            "identity": "identity.v1",
            "evidence": "evidence.v1",
            "daily": "daily.v1",
            "recap": "recap.v1",
        },
    )
    case = ReplayCase(
        name="weike_2026_04_22",
        trade_date=date(2026, 4, 22),
        stock_id="600152.SH",
    )

    report = await runner.run_case(
        case,
        mode=ReplayMode.REBUILD_FEATURE,
        snapshot_version="replay_v1",
        batch_id="batch",
        trace_id="trace",
        input_hashes={"evidence": "e1", "daily": "d1", "recap": "r1"},
    )

    assert report.ok is True
    assert [r.layer_name for r in report.layer_results if r.action == "rebuilt"] == [
        "evidence",
        "daily",
        "recap",
    ]
    assert len(identity.calls) == 0
    assert len(evidence.calls) == 1
    assert len(daily.calls) == 1
    assert len(recap.calls) == 1
    assert {row["layer_name"] for row in store.as_rows()} == {"evidence", "daily", "recap"}


@pytest.mark.asyncio
async def test_replay_runner_reuses_manifest_when_hash_matches() -> None:
    store = InMemoryReplayManifestStore()
    await store.upsert_layer_manifest(
        ReplayLayerManifest(
            trade_date=date(2026, 4, 7),
            layer_name="recap",
            snapshot_version="replay_v1",
            algorithm_version="recap.v1",
            input_hash="same",
            row_count=9,
            status="ok",
        )
    )
    recap = _FakeJob("recap")
    runner = ReplayRunner(
        manifest_store=store,
        jobs={"recap": recap},
        algorithm_versions={"recap": "recap.v1"},
    )
    case = ReplayCase(
        name="shenjian_2026_04_07",
        trade_date=date(2026, 4, 7),
        stock_id="002361.SZ",
    )

    report = await runner.run_case(
        case,
        mode=ReplayMode.REBUILD_OUTPUT,
        snapshot_version="replay_v1",
        batch_id="batch",
        trace_id="trace",
        input_hashes={"recap": "same"},
    )

    recap_result = next(r for r in report.layer_results if r.layer_name == "recap")
    assert recap_result.action == "skip_rebuild_manifest_reusable"
    assert recap_result.status == "reused"
    assert recap_result.affected_rows == 9
    assert len(recap.calls) == 0


def test_replay_case_loader_reads_fixed_yaml_cases() -> None:
    cases = ReplayCaseLoader.load("stock_processing_service/tests/replay/cases/weak_to_strong_cases.yaml")
    by_name = {case.name: case for case in cases}

    assert sorted(by_name) == [
        "liande_2026_04_15",
        "shenjian_2026_04_07",
        "weike_2026_04_22",
        "weike_2026_04_23",
    ]
    assert by_name["liande_2026_04_15"].expected["layer_d"]["candidate_level"] == "observe_only"
    assert by_name["weike_2026_04_22"].expected["layer_d"]["candidate_level_in"] == [
        "formal",
        "observe_only",
    ]


@pytest.mark.asyncio
async def test_replay_manifest_gateway_adapter_round_trips_manifest() -> None:
    class _Db:
        def __init__(self) -> None:
            self.row = None

        async def get_replay_snapshot_manifest(
            self,
            trade_date,
            layer_name,
            snapshot_version,
            algorithm_version,
        ):
            return self.row

        async def upsert_replay_snapshot_manifest(self, row):
            self.row = dict(row)
            return 1

    db = _Db()
    adapter = ReplayManifestGatewayAdapter(db)
    manifest = ReplayLayerManifest(
        trade_date=date(2026, 4, 7),
        layer_name="recap",
        snapshot_version="replay_v1",
        algorithm_version="recap.v1",
        input_hash="abc",
        output_hash="def",
        row_count=10,
        status="ok",
        batch_id="batch",
        trace_id="trace",
    )

    assert await adapter.upsert_layer_manifest(manifest) == 1
    loaded = await adapter.get_layer_manifest(
        trade_date=date(2026, 4, 7),
        layer_name="recap",
        snapshot_version="replay_v1",
        algorithm_version="recap.v1",
    )

    assert loaded == manifest
