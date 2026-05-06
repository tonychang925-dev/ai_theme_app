from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Protocol

from stock_processing_service.application.replay.replay_assertion_service import ReplayAssertionService
from stock_processing_service.application.replay.replay_cases import ReplayCase
from stock_processing_service.application.replay.replay_manifest import (
    ReplayLayerManifest,
    ReplayManifestStore,
)
from stock_processing_service.contracts.dto import BuildResult


class ReplayMode(str, Enum):
    REUSE_ALL = "reuse_all"
    REBUILD_OUTPUT = "rebuild_output"
    REBUILD_POOL = "rebuild_pool"
    REBUILD_FEATURE = "rebuild_feature"
    FULL_REBUILD = "full_rebuild"


class ReplayJob(Protocol):
    async def execute(
        self,
        trade_date: date,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
    ) -> BuildResult: ...


@dataclass(frozen=True)
class ReplayLayerResult:
    layer_name: str
    action: str
    status: str
    affected_rows: int = 0
    reason: str = ""


@dataclass(frozen=True)
class ReplayRunReport:
    case_name: str
    trade_date: date
    stock_id: str
    mode: ReplayMode
    snapshot_version: str
    layer_results: list[ReplayLayerResult] = field(default_factory=list)
    assertions: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        allowed = {"ok", "rebuilt", "reused", "skipped_idempotent"}
        layer_ok = all(r.status in allowed for r in self.layer_results)
        assertions_ok = bool(self.assertions.get("passed", True))
        return layer_ok and assertions_ok


class ReplayRunner:
    """Layer-aware replay orchestrator.

    v0.1 focuses on rebuild/reuse routing and manifest writes. Layer assertions
    are deliberately separated so tests and DB-backed runners can evolve without
    changing production Jobs.
    """

    LAYER_ORDER = ("identity", "evidence", "daily", "recap")
    MODE_REBUILD_LAYERS: dict[ReplayMode, tuple[str, ...]] = {
        ReplayMode.REUSE_ALL: (),
        ReplayMode.REBUILD_OUTPUT: ("recap",),
        # Strong-watch pool is currently built inside BuildPostMarketRecapJob.
        ReplayMode.REBUILD_POOL: ("recap",),
        ReplayMode.REBUILD_FEATURE: ("evidence", "daily", "recap"),
        ReplayMode.FULL_REBUILD: ("identity", "evidence", "daily", "recap"),
    }

    def __init__(
        self,
        *,
        manifest_store: ReplayManifestStore,
        jobs: dict[str, ReplayJob] | None = None,
        algorithm_versions: dict[str, str] | None = None,
        assertion_service: ReplayAssertionService | None = None,
        strict_reuse: bool = True,
        require_input_hash: bool = True,
    ) -> None:
        self._manifest_store = manifest_store
        self._jobs = jobs or {}
        self._algorithm_versions = algorithm_versions or {}
        self._assertion_service = assertion_service
        self._strict_reuse = strict_reuse
        self._require_input_hash = require_input_hash

    def layers_for_mode(self, mode: ReplayMode) -> tuple[str, ...]:
        return self.MODE_REBUILD_LAYERS[mode]

    async def run_case(
        self,
        case: ReplayCase,
        *,
        mode: ReplayMode,
        snapshot_version: str,
        batch_id: str,
        trace_id: str,
        input_hashes: dict[str, str] | None = None,
        force: bool = False,
    ) -> ReplayRunReport:
        rebuild_layers = set(self.layers_for_mode(mode))
        input_hashes = input_hashes or {}
        layer_results: list[ReplayLayerResult] = []

        for layer_name in self.LAYER_ORDER:
            algorithm_version = self._algorithm_versions.get(layer_name, "v1")
            input_hash = input_hashes.get(layer_name, "")
            manifest = await self._manifest_store.get_layer_manifest(
                trade_date=case.trade_date,
                layer_name=layer_name,
                snapshot_version=snapshot_version,
                algorithm_version=algorithm_version,
            )
            missing_hash = self._require_input_hash and not input_hash

            if layer_name not in rebuild_layers:
                if manifest and manifest.reusable_for(input_hash=input_hash, strict=self._strict_reuse):
                    layer_results.append(
                        ReplayLayerResult(
                            layer_name=layer_name,
                            action="reuse_manifest",
                            status="reused",
                            affected_rows=manifest.row_count,
                        )
                    )
                else:
                    strict_missing = mode == ReplayMode.REUSE_ALL or self._strict_reuse
                    layer_results.append(
                        ReplayLayerResult(
                            layer_name=layer_name,
                            action="reuse_existing_snapshot",
                            status="missing_snapshot" if strict_missing else "skipped_idempotent",
                            reason="input_hash_missing" if missing_hash else "manifest_missing_or_input_changed",
                        )
                    )
                continue

            existing = (
                (not force)
                and manifest is not None
                and manifest.reusable_for(input_hash=input_hash, strict=self._strict_reuse)
            )
            if existing:
                layer_results.append(
                    ReplayLayerResult(
                        layer_name=layer_name,
                        action="skip_rebuild_manifest_reusable",
                        status="reused",
                        affected_rows=manifest.row_count if manifest else 0,
                    )
                )
                continue

            if missing_hash and not force:
                layer_results.append(
                    ReplayLayerResult(
                        layer_name=layer_name,
                        action="blocked_rebuild",
                        status="failed",
                        reason="input_hash_required",
                    )
                )
                continue

            job = self._jobs.get(layer_name)
            if job is None:
                raise RuntimeError(f"ReplayRunner missing job for rebuild layer: {layer_name}")

            result = await job.execute(
                trade_date=case.trade_date,
                snapshot_version=snapshot_version,
                batch_id=batch_id,
                trace_id=trace_id,
            )
            await self._manifest_store.upsert_layer_manifest(
                ReplayLayerManifest(
                    trade_date=case.trade_date,
                    layer_name=layer_name,
                    snapshot_version=snapshot_version,
                    algorithm_version=algorithm_version,
                    input_hash=input_hash,
                    output_hash=str(result.metrics.get("output_hash") or ""),
                    row_count=int(result.affected_rows or 0),
                    status=result.status,
                    batch_id=batch_id,
                    trace_id=trace_id,
                )
            )
            layer_results.append(
                ReplayLayerResult(
                    layer_name=layer_name,
                    action="rebuilt",
                    status=result.status,
                    affected_rows=result.affected_rows,
                )
            )

        assertions: dict[str, Any] = {"expected": case.expected}
        if self._assertion_service is not None:
            assertion_report = await self._assertion_service.assert_case(case)
            assertions = assertion_report

        return ReplayRunReport(
            case_name=case.name,
            trade_date=case.trade_date,
            stock_id=case.stock_id,
            mode=mode,
            snapshot_version=snapshot_version,
            layer_results=layer_results,
            assertions=assertions,
        )
