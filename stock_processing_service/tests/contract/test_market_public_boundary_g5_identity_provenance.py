from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from stock_processing_service.application.identity import (
    ArtifactDigest,
    ArtifactIdentity,
    BuildIdentity,
    CapturedSourceEvidence,
    CompatibilityLineage,
    EvidencePurpose,
    IdentityBundle,
    MechanicalEvidence,
    ReleaseEvidenceBasis,
    RuntimeInstanceIdentity,
    SemanticReconstruction,
    SourceIdentity,
    validate_compatibility_lineage,
    validate_semantic_reconstruction,
)
from stock_processing_service.application.identity.release_identity_verifier import (
    ReleaseIdentityVerificationError,
    ReleaseIdentityVerifier,
    complete_provenance,
    require_verified_result,
)
from stock_processing_service.application.services.market_event_public_boundary import (
    EVENT_READ_CAPABILITY_ID,
    EVENT_RESOLVE_CAPABILITY_ID,
    MarketEventLineage,
    MarketEventPublicBoundaryService,
    MarketEventReadRequest,
    MarketEventRecord,
    event_provenance_profile,
)
from stock_processing_service.contracts.market_public_boundary import (
    EpistemicClass,
    MarketBoundaryIdentity,
    MarketGovernanceState,
    MarketObjectRef,
    MarketProvenance,
    MarketReleaseIdentity,
    OperationStatus,
    ProvenanceStatus,
    ProvenanceValidationContext,
    ReleaseIdentityEvidenceBasis,
)
from stock_processing_service.infrastructure.gateway_adapters.market_event_public_reader import (
    MarketEventPublicReader,
)
from stock_processing_service.infrastructure.release_identity import (
    ArtifactLocator,
    ManifestLocator,
    calculate_artifact_digest,
    read_canonical_artifact,
    read_canonical_manifest,
)


NOW = datetime(2026, 9, 12, 12, 0, tzinfo=timezone.utc)
PUBLIC_ID = "evt_0192b42d5c6f4a2b9d3f"
OBJECT_REF = MarketObjectRef("market.event", PUBLIC_ID)
SOURCE_ID = "source:market-event:verified:v1"
BUILD_ID = "build:market-event:verified:v1"
ARTIFACT_ID = "artifact:market-event:verified:v1"
ARTIFACT_LOCATOR = "releases/market-event.bin"
RUNTIME_ID = "runtime:market-event:instance:v1"
MANIFEST_REF = "manifest:market-event:verified:v1"
PROFILE_REF = "market-event:reported-claim:v1"
ARTIFACT_BYTES = b"market event canonical bytes\n"
DIGEST = ArtifactDigest("sha256:" + hashlib.sha256(ARTIFACT_BYTES).hexdigest())
IDENTITIES = IdentityBundle(
    source_identity=SourceIdentity(SOURCE_ID),
    build_identity=BuildIdentity(BUILD_ID),
    artifact_identity=ArtifactIdentity(ARTIFACT_ID),
    artifact_digest=DIGEST,
    runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
)


class Reader:
    def __init__(self, record: MarketEventRecord) -> None:
        self.record = record

    async def read_event(self, object_ref: MarketObjectRef) -> MarketEventRecord:
        return self.record

    async def resolve_event(self, object_ref: MarketObjectRef):
        return None


class RealisticDatabaseRowWithoutSourceTrace:
    async def get_event(self, event_id: int) -> dict:
        return {
            "id": event_id,
            "news_id": 987,
            "summary": "Public summary",
            "source": "market-source",
            "publish_time": NOW,
            "updated_at": NOW,
            "processed": True,
            "processing_status": "complete",
        }

    async def get_news_event_for_match(self, event_id: int) -> dict:
        return {
            "id": event_id,
            "title": "Public title",
            "content": "Public content",
            "event_type": "announcement",
            "summary": "Public summary",
        }


class DatabaseRowWithSourceTrace(RealisticDatabaseRowWithoutSourceTrace):
    async def get_event(self, event_id: int) -> dict:
        row = await super().get_event(event_id)
        return {**row, "source_trace_id": "lineage:source:1"}


def _write_canonical_release(root: Path) -> None:
    release_dir = root / "releases"
    release_dir.mkdir(parents=True, exist_ok=True)
    (release_dir / "market-event.bin").write_bytes(ARTIFACT_BYTES)
    manifest = {
        "manifest_ref": MANIFEST_REF,
        "profile_id": PROFILE_REF,
        "source_identity": SOURCE_ID,
        "build_identity": BUILD_ID,
        "artifact_identity": ARTIFACT_ID,
        "artifact_digest": DIGEST.value,
        "artifact_locator": "canonical:" + ARTIFACT_LOCATOR,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )


def _release() -> MarketReleaseIdentity:
    return MarketReleaseIdentity(
        source_identity=SOURCE_ID,
        build_identity=BUILD_ID,
        artifact_identity=ARTIFACT_ID,
        artifact_digest=DIGEST.value,
        release_manifest_ref=MANIFEST_REF,
    )


def _boundary() -> MarketBoundaryIdentity:
    return MarketBoundaryIdentity(
        provider_id="market",
        public_contract_name="market-public-boundary",
        public_contract_version="1.0",
        release_identity=_release(),
        supported_capabilities=(EVENT_READ_CAPABILITY_ID, EVENT_RESOLVE_CAPABILITY_ID),
        supported_object_types=("market.event",),
    )


def _event_record() -> MarketEventRecord:
    return MarketEventRecord(
        object_ref=OBJECT_REF,
        title="Public event title",
        summary="Public event summary",
        content="Public event content",
        event_type="announcement",
        source="market-source",
        occurred_at=NOW,
        data_cutoff=NOW,
        governance_state=MarketGovernanceState.PUBLISHED,
        lineage=MarketEventLineage(source_trace_id="lineage:source:1"),
        source_refs=("market-source",),
        evidence_refs=("evidence:verified:1",),
    )


def _mechanical_release(tmp_path: Path) -> tuple:
    _write_canonical_release(tmp_path)
    manifest = read_canonical_manifest(ManifestLocator(tmp_path, "manifest.json"))
    artifact = read_canonical_artifact(
        ArtifactLocator(tmp_path, ARTIFACT_LOCATOR), manifest.artifact_identity
    )
    digest = calculate_artifact_digest(artifact)
    identity_digest = lambda value: ArtifactDigest(
        "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()
    )
    evidence = (
        MechanicalEvidence(
            EvidencePurpose.MANIFEST,
            ReleaseEvidenceBasis.CLEAN_REPOSITORY_SNAPSHOT,
            manifest.manifest_digest,
            "verifier-output:1",
        ),
        MechanicalEvidence(
            EvidencePurpose.ARTIFACT_IDENTITY,
            ReleaseEvidenceBasis.EXPLICIT_CAPTURED_ARTIFACT,
            identity_digest(manifest.artifact_identity),
            "verifier-output:1",
        ),
        MechanicalEvidence(
            EvidencePurpose.ARTIFACT_DIGEST,
            ReleaseEvidenceBasis.EXPLICIT_CAPTURED_ARTIFACT,
            digest,
            "verifier-output:1",
        ),
        MechanicalEvidence(
            EvidencePurpose.SOURCE_BUILD_LINEAGE,
            ReleaseEvidenceBasis.CLEAN_REPOSITORY_SNAPSHOT,
            identity_digest(SOURCE_ID + "\0" + BUILD_ID),
            "verifier-output:1",
        ),
    )
    return manifest, artifact, digest, evidence


def _verified_release(tmp_path: Path):
    manifest, artifact, digest, evidence = _mechanical_release(tmp_path)
    verified = ReleaseIdentityVerifier().verify(
        attested_release=_release(),
        manifest=manifest,
        artifact=artifact,
        computed_artifact_digest=digest,
        runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
        evidence=evidence,
    )
    return manifest, verified


def _candidate_provenance(
    status: ProvenanceStatus = ProvenanceStatus.PROVENANCE_INCOMPLETE,
):
    return MarketProvenance(
        provenance_status=status,
        market_release_identity=_release(),
        produced_at=NOW,
        source_refs=("market-source",),
        evidence_refs=("evidence:verified:1",),
        public_object_refs=(OBJECT_REF,),
        data_cutoff=NOW,
        capability_call_ref=EVENT_READ_CAPABILITY_ID,
        correlation_id="correlation-g5",
    )


def _context() -> ProvenanceValidationContext:
    return ProvenanceValidationContext(
        capability_id=EVENT_READ_CAPABILITY_ID,
        epistemic_class=EpistemicClass.REPORTED_CLAIM,
        governance_state=MarketGovernanceState.PUBLISHED,
    )


def test_g5_at01_identity_channels_are_mechanically_distinct() -> None:
    values = (
        IDENTITIES.source_identity.value,
        IDENTITIES.build_identity.value,
        IDENTITIES.artifact_identity.value,
        IDENTITIES.artifact_digest.value,
        IDENTITIES.runtime_instance_identity.value,
    )
    assert len(set(values)) == 5
    with pytest.raises(ValueError, match="wrong identity type"):
        IdentityBundle(
            source_identity=BuildIdentity(SOURCE_ID),
            build_identity=IDENTITIES.build_identity,
            artifact_identity=IDENTITIES.artifact_identity,
            artifact_digest=IDENTITIES.artifact_digest,
            runtime_instance_identity=IDENTITIES.runtime_instance_identity,
        )
    collision_bundle = IdentityBundle(
        source_identity=SourceIdentity("source:collision"),
        build_identity=BuildIdentity("build:collision"),
        artifact_identity=ArtifactIdentity("artifact:collision"),
        artifact_digest=DIGEST,
        runtime_instance_identity=RuntimeInstanceIdentity("runtime:collision"),
    )
    for field_name in (
        "source_identity",
        "build_identity",
        "artifact_identity",
        "artifact_digest",
        "runtime_instance_identity",
    ):
        collision_type = {
            "source_identity": SourceIdentity,
            "build_identity": BuildIdentity,
            "artifact_identity": ArtifactIdentity,
            "artifact_digest": ArtifactDigest,
            "runtime_instance_identity": RuntimeInstanceIdentity,
        }[field_name]
        collision_digest = ArtifactDigest("sha256:" + "a" * 64)
        collision_value = collision_type(
            collision_digest.value if field_name == "artifact_digest" else DIGEST.value
        )
        with pytest.raises(ValueError, match="must all differ"):
            replace(
                (
                    collision_bundle
                    if field_name != "artifact_digest"
                    else replace(
                        collision_bundle,
                        source_identity=SourceIdentity(collision_digest.value),
                    )
                ),
                **{field_name: collision_value},
            )
    with pytest.raises(ValueError):
        ArtifactDigest("sha512:" + "0" * 64)


def test_g5_at02_attestation_alone_cannot_become_verification(tmp_path: Path) -> None:
    manifest, artifact, digest, evidence = _mechanical_release(tmp_path)
    verifier = ReleaseIdentityVerifier()
    with pytest.raises(ValueError, match="provider attestation"):
        MechanicalEvidence(
            EvidencePurpose.MANIFEST,
            ReleaseEvidenceBasis.PROVIDER_ATTESTED,
            manifest.manifest_digest,
            "declared-verification:1",
        )
    with pytest.raises(ValueError, match="release evidence basis has the wrong type"):
        MechanicalEvidence(
            EvidencePurpose.MANIFEST,
            ReleaseIdentityEvidenceBasis.UNKNOWN,
            manifest.manifest_digest,
            "unknown-declaration:1",
        )
    with pytest.raises(ReleaseIdentityVerificationError, match="evidence is missing"):
        verifier.verify(
            attested_release=_release(),
            manifest=manifest,
            artifact=artifact,
            computed_artifact_digest=digest,
            runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
            evidence=(),
        )
    wrong_subject = (
        replace(evidence[0], subject_digest=ArtifactDigest("sha256:" + "0" * 64)),
        *evidence[1:],
    )
    with pytest.raises(ReleaseIdentityVerificationError, match="different subject"):
        verifier.verify(
            attested_release=_release(),
            manifest=manifest,
            artifact=artifact,
            computed_artifact_digest=digest,
            runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
            evidence=wrong_subject,
        )
    other_attested = replace(_release(), source_identity="source:other:v1")
    with pytest.raises(ReleaseIdentityVerificationError, match="does not match"):
        verifier.verify(
            attested_release=other_attested,
            manifest=manifest,
            artifact=artifact,
            computed_artifact_digest=digest,
            runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
            evidence=evidence,
        )
    with pytest.raises(ReleaseIdentityVerificationError, match="missing"):
        verifier.verify_provenance(
            profile=event_provenance_profile(),
            provenance=_candidate_provenance(),
            context=_context(),
            verified_identity=None,
            expected_profile_ref=PROFILE_REF,
        )
    verified = verifier.verify(
        attested_release=_release(),
        manifest=manifest,
        artifact=artifact,
        computed_artifact_digest=digest,
        runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
        evidence=evidence,
    )
    assert verified.source_identity != verified.verifier_output_id
    assert verified.artifact_digest == DIGEST


def test_g5_at03_digest_uses_only_selected_canonical_artifact_bytes(
    tmp_path: Path,
) -> None:
    manifest, artifact, digest, evidence = _mechanical_release(tmp_path)
    missing = ArtifactLocator(tmp_path / "missing-root", ARTIFACT_LOCATOR)
    with pytest.raises(ValueError, match="does not select"):
        read_canonical_artifact(missing, manifest.artifact_identity)
    assert calculate_artifact_digest(artifact) == manifest.artifact_digest
    wrong_locator = replace(artifact, artifact_locator="releases/other.bin")
    with pytest.raises(ReleaseIdentityVerificationError, match="locator mismatch"):
        ReleaseIdentityVerifier().verify(
            attested_release=_release(),
            manifest=manifest,
            artifact=wrong_locator,
            computed_artifact_digest=manifest.artifact_digest,
            runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
            evidence=evidence,
        )
    changed = replace(artifact, bytes_=b"noncanonical bytes")
    assert calculate_artifact_digest(changed) != manifest.artifact_digest
    with pytest.raises(ValueError):
        ArtifactDigest("sha256:" + "not-hex")


def test_g5_at04_provenance_complete_requires_mechanical_success(
    tmp_path: Path,
) -> None:
    _, verified = _verified_release(tmp_path)
    verifier = ReleaseIdentityVerifier()
    result = verifier.verify_provenance(
        profile=event_provenance_profile(),
        provenance=_candidate_provenance(),
        context=_context(),
        verified_identity=verified,
        expected_profile_ref=PROFILE_REF,
    )
    completed = complete_provenance(result)
    assert completed.provenance_status is ProvenanceStatus.PROVENANCE_COMPLETE
    producer_declared = _candidate_provenance(ProvenanceStatus.PROVENANCE_COMPLETE)
    incomplete = replace(producer_declared, source_refs=())
    with pytest.raises(ReleaseIdentityVerificationError, match="predicates failed"):
        verifier.verify_provenance(
            profile=event_provenance_profile(),
            provenance=incomplete,
            context=_context(),
            verified_identity=verified,
            expected_profile_ref=PROFILE_REF,
        )
    with pytest.raises(ReleaseIdentityVerificationError, match="profile reference"):
        verifier.verify_provenance(
            profile=event_provenance_profile(),
            provenance=producer_declared,
            context=_context(),
            verified_identity=verified,
            expected_profile_ref="market-public-boundary:standard",
        )


async def test_g5_at05_source_trace_is_compatibility_only_not_identity() -> None:
    lineage = validate_compatibility_lineage(
        CompatibilityLineage("lineage:source:1"), IDENTITIES
    )
    assert lineage.source_trace_id not in (
        IDENTITIES.source_identity.value,
        IDENTITIES.build_identity.value,
        IDENTITIES.artifact_identity.value,
        IDENTITIES.artifact_digest.value,
        IDENTITIES.runtime_instance_identity.value,
    )
    with pytest.raises(ValueError, match="not release identity"):
        validate_compatibility_lineage(CompatibilityLineage(SOURCE_ID), IDENTITIES)
    reader = MarketEventPublicReader(
        RealisticDatabaseRowWithoutSourceTrace(), {PUBLIC_ID: 123}
    )
    record = await reader.read_event(OBJECT_REF)
    assert record is not None
    assert record.lineage.source_trace_id is None
    preserving_reader = MarketEventPublicReader(
        DatabaseRowWithSourceTrace(), {PUBLIC_ID: 123}
    )
    preserved_record = await preserving_reader.read_event(OBJECT_REF)
    assert preserved_record is not None
    assert preserved_record.lineage.source_trace_id == "lineage:source:1"
    postgres_manager_source = (
        Path(__file__).parents[3]
        / "database_service"
        / "managers"
        / "postgres_manager.py"
    ).read_text(encoding="utf-8")
    get_event_start = postgres_manager_source.index("    async def get_event(")
    get_event_end = postgres_manager_source.index(
        "    async def ", get_event_start + len("    async def get_event(")
    )
    get_event_source = postgres_manager_source[get_event_start:get_event_end]
    assert "source_trace_id" not in get_event_source


def test_g5_at06_dirty_and_runtime_evidence_stay_noncanonical(tmp_path: Path) -> None:
    bases = (
        ReleaseEvidenceBasis.DIRTY_TRACKED_CONTENT,
        ReleaseEvidenceBasis.UNTRACKED_CONTENT,
        ReleaseEvidenceBasis.RUNTIME_CAPTURE,
    )
    captures = tuple(
        CapturedSourceEvidence(
            f"capture:{basis.value.lower()}",
            basis,
            ArtifactDigest(
                "sha256:" + hashlib.sha256(basis.value.encode()).hexdigest()
            ),
        )
        for basis in bases
    )
    assert [capture.basis for capture in captures] == list(bases)
    assert all(
        capture.content_digest.value.startswith("sha256:") for capture in captures
    )
    reconstruction = SemanticReconstruction("reconstruction:runtime", captures)
    assert not reconstruction.canonical_source
    with pytest.raises(ValueError, match="noncanonical: DIRTY_TRACKED_CONTENT"):
        validate_semantic_reconstruction(reconstruction, require_canonical_source=True)
    manifest, artifact, digest, evidence = _mechanical_release(tmp_path)
    runtime_evidence = tuple(
        replace(
            item,
            basis=ReleaseEvidenceBasis.RUNTIME_CAPTURE,
            verifier_output_id="runtime-declaration:1",
        )
        for item in evidence
    )
    with pytest.raises(ReleaseIdentityVerificationError, match="runtime capture"):
        ReleaseIdentityVerifier().verify(
            attested_release=_release(),
            manifest=manifest,
            artifact=artifact,
            computed_artifact_digest=digest,
            runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
            evidence=runtime_evidence,
        )


def test_g5_at07_semantic_reconstruction_preserves_provenance() -> None:
    explicit = CapturedSourceEvidence(
        "capture:explicit",
        ReleaseEvidenceBasis.EXPLICIT_CAPTURED_ARTIFACT,
        DIGEST,
    )
    runtime = CapturedSourceEvidence(
        "capture:runtime",
        ReleaseEvidenceBasis.RUNTIME_CAPTURE,
        DIGEST,
    )
    canonical = validate_semantic_reconstruction(
        SemanticReconstruction("reconstruction:canonical", (explicit,)),
        require_canonical_source=True,
    )
    noncanonical = SemanticReconstruction("reconstruction:runtime", (runtime,))
    assert canonical.canonical_source
    assert noncanonical.evidence_bases == (ReleaseEvidenceBasis.RUNTIME_CAPTURE,)
    assert not noncanonical.canonical_source
    with pytest.raises(ValueError, match="noncanonical: RUNTIME_CAPTURE"):
        validate_semantic_reconstruction(noncanonical, require_canonical_source=True)
    with pytest.raises(ValueError, match="explicit captured evidence"):
        SemanticReconstruction("reconstruction:empty", ())


async def test_g5_at08_verified_identity_path_gates_g2a_without_substitution(
    tmp_path: Path,
) -> None:
    service = MarketEventPublicBoundaryService(Reader(_event_record()), _boundary())
    envelope = await service.read_event(
        MarketEventReadRequest(object_ref=OBJECT_REF, correlation_id="correlation-g5")
    )
    assert envelope.operation_status is OperationStatus.SUCCESS
    assert envelope.provenance.provenance_status is ProvenanceStatus.PROVENANCE_COMPLETE
    verifier = ReleaseIdentityVerifier()
    with pytest.raises(ReleaseIdentityVerificationError, match="missing"):
        require_verified_result(
            envelope,
            profile=event_provenance_profile(),
            context=_context(),
            verified_identity=None,
            expected_profile_ref=PROFILE_REF,
        )
    with pytest.raises(ReleaseIdentityVerificationError, match="missing"):
        verifier.verify_provenance(
            profile=event_provenance_profile(),
            provenance=envelope.provenance,
            context=_context(),
            verified_identity=None,
            expected_profile_ref=PROFILE_REF,
        )
    _, _, _, evidence = _mechanical_release(tmp_path)
    (tmp_path / "releases" / "market-event.bin").write_bytes(b"corrupt verifier input")
    manifest = read_canonical_manifest(ManifestLocator(tmp_path, "manifest.json"))
    artifact = read_canonical_artifact(
        ArtifactLocator(tmp_path, ARTIFACT_LOCATOR), manifest.artifact_identity
    )
    with pytest.raises(ReleaseIdentityVerificationError, match="digest mismatch"):
        ReleaseIdentityVerifier().verify(
            attested_release=_release(),
            manifest=manifest,
            artifact=artifact,
            computed_artifact_digest=calculate_artifact_digest(artifact),
            runtime_instance_identity=RuntimeInstanceIdentity(RUNTIME_ID),
            evidence=evidence,
        )
    _, verified = _verified_release(tmp_path)
    result = verifier.verify_provenance(
        profile=event_provenance_profile(),
        provenance=envelope.provenance,
        context=_context(),
        verified_identity=verified,
        expected_profile_ref=PROFILE_REF,
    )
    assert result.evaluated_predicates == (
        "source_refs_non_empty",
        "market_release_identity_required",
        "data_cutoff_required_for_epistemic_classes",
    )
    production_files = tuple(
        Path().glob("stock_processing_service/application/identity/*.py")
    ) + tuple(
        Path().glob("stock_processing_service/infrastructure/release_identity/*.py")
    )
    for path in production_files:
        source = path.read_text(encoding="utf-8").lower()
        assert "fallback" not in source
        assert "mock" not in source
        assert "legacy" not in source
