from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.replay import (
    ReplayCase,
    ReplayAssertionService,
    ReplayCaseLoader,
    ReplayInputHashBuilder,
    ReplayLayerManifest,
    ReplayMode,
    ReplayReportWriter,
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
    await store.upsert_layer_manifest(
        ReplayLayerManifest(
            trade_date=date(2026, 4, 22),
            layer_name="identity",
            snapshot_version="replay_v1",
            algorithm_version="identity.v1",
            input_hash="i1",
            row_count=2,
            status="ok",
        )
    )
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
        input_hashes={"identity": "i1", "evidence": "e1", "daily": "d1", "recap": "r1"},
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
    assert {row["layer_name"] for row in store.as_rows()} == {"identity", "evidence", "daily", "recap"}


@pytest.mark.asyncio
async def test_replay_runner_reuses_manifest_when_hash_matches() -> None:
    store = InMemoryReplayManifestStore()
    for layer in ("identity", "evidence", "daily"):
        await store.upsert_layer_manifest(
            ReplayLayerManifest(
                trade_date=date(2026, 4, 7),
                layer_name=layer,
                snapshot_version="replay_v1",
                algorithm_version="v1",
                input_hash=f"{layer}-hash",
                row_count=1,
                status="ok",
            )
        )
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
        input_hashes={
            "identity": "identity-hash",
            "evidence": "evidence-hash",
            "daily": "daily-hash",
            "recap": "same",
        },
    )

    recap_result = next(r for r in report.layer_results if r.layer_name == "recap")
    assert recap_result.action == "skip_rebuild_manifest_reusable"
    assert recap_result.status == "reused"
    assert recap_result.affected_rows == 9
    assert len(recap.calls) == 0


@pytest.mark.asyncio
async def test_replay_runner_reuse_all_missing_manifest_is_not_ok() -> None:
    store = InMemoryReplayManifestStore()
    runner = ReplayRunner(manifest_store=store)
    case = ReplayCase(
        name="missing",
        trade_date=date(2026, 4, 7),
        stock_id="002361.SZ",
    )

    report = await runner.run_case(
        case,
        mode=ReplayMode.REUSE_ALL,
        snapshot_version="replay_v1",
        batch_id="batch",
        trace_id="trace",
        input_hashes={"identity": "i", "evidence": "e", "daily": "d", "recap": "r"},
    )

    assert report.ok is False
    assert {r.status for r in report.layer_results} == {"missing_snapshot"}


@pytest.mark.asyncio
async def test_replay_runner_requires_input_hash_in_strict_mode() -> None:
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
        input_hashes={},
    )

    recap_result = next(r for r in report.layer_results if r.layer_name == "recap")
    assert report.ok is False
    assert recap_result.status == "failed"
    assert recap_result.reason == "input_hash_required"
    assert len(recap.calls) == 0


@pytest.mark.asyncio
async def test_replay_runner_force_rebuild_ignores_reusable_manifest() -> None:
    store = InMemoryReplayManifestStore()
    for layer in ("identity", "evidence", "daily"):
        await store.upsert_layer_manifest(
            ReplayLayerManifest(
                trade_date=date(2026, 4, 7),
                layer_name=layer,
                snapshot_version="replay_v1",
                algorithm_version="v1",
                input_hash=f"{layer}-hash",
                row_count=1,
                status="ok",
            )
        )
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
        input_hashes={
            "identity": "identity-hash",
            "evidence": "evidence-hash",
            "daily": "daily-hash",
            "recap": "same",
        },
        force=True,
    )

    recap_result = next(r for r in report.layer_results if r.layer_name == "recap")
    assert recap_result.action == "rebuilt"
    assert len(recap.calls) == 1


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
    assert by_name["weike_2026_04_23"].expected["layer_d"]["allowed_outcomes"] == [
        {"candidate_level": "formal"},
        {"candidate_level": "observe_only"},
        {"candidate_level": "reject", "reject_reason_contains": "末端跳水"},
    ]


@pytest.mark.asyncio
async def test_replay_assertion_service_asserts_recap_outputs() -> None:
    class _Read:
        async def get_existing_post_market_recap_snapshot(self, trade_date):
            return {
                "trade_date": trade_date,
                "snapshot_version": "v1",
                "recap_doc": {
                    "top_candidates": [
                        {
                            "stock_id": "002361.SZ",
                            "candidate_level": "formal",
                            "support_type": "gap_support",
                            "gap_hit": True,
                        }
                    ],
                    "strong_watch_input_7d_preview": [{"stock_id": "002361.SZ"}],
                },
            }

    svc = ReplayAssertionService(_Read())
    case = ReplayCase(
        name="shenjian_2026_04_07",
        trade_date=date(2026, 4, 7),
        stock_id="002361.SZ",
        expected={
            "layer_c": {"present_in_promoted_pool": True},
            "layer_d": {
                "present_in_top_candidates": True,
                "support_type": "gap_support",
                "gap_hit": True,
            },
        },
    )

    report = await svc.assert_case(case)

    assert report["passed"] is True
    assert report["layer_results"]["layer_d.support_type"]["actual"] == "gap_support"


def test_replay_input_hash_builder_is_stable() -> None:
    h1 = ReplayInputHashBuilder.build(
        trade_date=date(2026, 4, 7),
        layer="recap",
        algorithm_version="recap.v1",
        input_row_count=3,
        extra={"b": 2, "a": [1, 2]},
    )
    h2 = ReplayInputHashBuilder.build(
        trade_date=date(2026, 4, 7),
        layer="recap",
        algorithm_version="recap.v1",
        input_row_count=3,
        extra={"a": [1, 2], "b": 2},
    )
    h3 = ReplayInputHashBuilder.build(
        trade_date=date(2026, 4, 7),
        layer="recap",
        algorithm_version="recap.v2",
        input_row_count=3,
        extra={"a": [1, 2], "b": 2},
    )

    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 64


def test_replay_report_writer_outputs_json_and_markdown(tmp_path) -> None:
    report = {
        "case_name": "shenjian_2026_04_07",
        "trade_date": "2026-04-07",
        "stock_id": "002361.SZ",
        "mode": "full_rebuild",
        "ok": True,
        "layer_results": [{"layer_name": "recap", "status": "ok"}],
        "assertions": {
            "passed": False,
            "layer_results": {
                "layer_d.support_type": {
                    "expected": "gap_support",
                    "actual": "prev_low_support",
                    "passed": False,
                }
            },
        },
    }
    paths = ReplayReportWriter(root=tmp_path).write_matrix(
        trade_date=date(2026, 4, 7),
        reports=[report],
    )

    assert paths["json"].endswith("20260407/replay_matrix.json")
    assert paths["md"].endswith("20260407/replay_matrix.md")
    md = (tmp_path / "20260407" / "replay_matrix.md").read_text()
    assert "shenjian_2026_04_07" in md
    assert "Failed Assertions" in md
    assert "prev_low_support" in md


@pytest.mark.asyncio
async def test_replay_assertion_service_supports_layer_a_b_expected_fields() -> None:
    class _Read:
        async def get_existing_post_market_recap_snapshot(self, trade_date):
            return {
                "trade_date": trade_date,
                "snapshot_version": "v1",
                "recap_doc": {
                    "top_candidates": [
                        {
                            "stock_id": "002361.SZ",
                            "subject_key": "s1",
                            "candidate_level": "formal",
                        }
                    ],
                },
            }

        async def get_mainline_identity_by_subject_keys(self, subject_keys, trade_date):
            return [{"subject_key": "s1", "identity_status": "confirmed", "is_main_theme": True}]

        async def get_mainline_cycle_by_subject_keys(self, subject_keys, trade_date):
            return [{"subject_key": "s1", "final_cycle_state": "repair", "final_mainline_alive": True}]

        async def get_subject_cycle_evidence_daily(self, trade_date, subject_keys=None):
            return [
                {
                    "subject_key": "s1",
                    "theme_support_score": "78",
                    "break_start_pivot": False,
                    "evidence_json": {"kline_layer": {"kline_quality": "ok"}},
                }
            ]

    svc = ReplayAssertionService(_Read())
    report = await svc.assert_case(
        ReplayCase(
            name="ab_case",
            trade_date=date(2026, 4, 7),
            stock_id="002361.SZ",
            expected={
                "layer_a": {"identity_status": "confirmed", "is_main_theme": True},
                "layer_b": {
                    "final_cycle_state_in": ["repair", "divergence"],
                    "final_mainline_alive": True,
                    "kline_quality": "ok",
                },
            },
        )
    )

    assert report["passed"] is True
    assert report["layer_results"]["layer_a.identity_status"]["passed"] is True
    assert report["layer_results"]["layer_b.final_cycle_state_in"]["actual"] == "repair"
    assert report["diagnostics"]["candidate_miss"]["selection"]["not_selected_reason"] == "selected"
    assert report["diagnostics"]["layer_b_summary"]["layer_b"]["cycle"]["final_cycle_state"] == "repair"


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
