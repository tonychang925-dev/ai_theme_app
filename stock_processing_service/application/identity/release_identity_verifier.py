"""Fail-closed mechanical release identity verification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from stock_processing_service.contracts.market_public_boundary import (
    MarketResultEnvelope,
    MarketProvenance,
    MarketProvenanceProfile,
    MarketReleaseIdentity,
    OperationStatus,
    ProvenanceStatus,
    ProvenanceValidationContext,
    validate_provenance_profile,
)

from .models import (
    ArtifactDigest,
    ArtifactIdentity,
    BuildIdentity,
    EvidencePurpose,
    IdentityBundle,
    MechanicalEvidence,
    ReleaseEvidenceBasis,
    RuntimeInstanceIdentity,
    SourceIdentity,
)


class ReleaseIdentityVerificationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CanonicalReleaseManifest:
    manifest_ref: str
    profile_id: str
    source_identity: str
    build_identity: str
    artifact_identity: str
    artifact_digest: ArtifactDigest
    artifact_locator: str
    manifest_digest: ArtifactDigest


@dataclass(frozen=True, slots=True)
class CanonicalArtifact:
    artifact_identity: str
    artifact_locator: str
    bytes_: bytes


@dataclass(frozen=True, slots=True)
class VerifiedReleaseIdentity:
    source_identity: str
    build_identity: str
    artifact_identity: str
    artifact_digest: ArtifactDigest
    manifest_ref: str
    runtime_instance_identity: str
    verifier_output_id: str
    verified_at: datetime
    evidence: tuple[MechanicalEvidence, ...]


@dataclass(frozen=True, slots=True)
class VerifiedProvenance:
    profile_id: str
    verified_release_identity: VerifiedReleaseIdentity
    evaluated_predicates: tuple[str, ...]
    provenance: MarketProvenance


class ReleaseIdentityVerifier:
    """Bind an attested release to exact manifest, artifact, digest, and lineage evidence."""

    REQUIRED_PURPOSES = frozenset(
        {
            EvidencePurpose.MANIFEST,
            EvidencePurpose.ARTIFACT_IDENTITY,
            EvidencePurpose.ARTIFACT_DIGEST,
            EvidencePurpose.SOURCE_BUILD_LINEAGE,
        }
    )

    def verify(
        self,
        *,
        attested_release: MarketReleaseIdentity,
        manifest: CanonicalReleaseManifest,
        artifact: CanonicalArtifact,
        computed_artifact_digest: ArtifactDigest,
        runtime_instance_identity: RuntimeInstanceIdentity,
        evidence: Iterable[MechanicalEvidence],
    ) -> VerifiedReleaseIdentity:
        evidence_tuple = tuple(evidence)
        self._verify_evidence_closure(evidence_tuple)
        IdentityBundle(
            source_identity=SourceIdentity(manifest.source_identity),
            build_identity=BuildIdentity(manifest.build_identity),
            artifact_identity=ArtifactIdentity(manifest.artifact_identity),
            artifact_digest=manifest.artifact_digest,
            runtime_instance_identity=runtime_instance_identity,
        )
        expected = (
            manifest.manifest_ref,
            manifest.source_identity,
            manifest.build_identity,
            manifest.artifact_identity,
            manifest.artifact_digest.value,
        )
        attested = (
            attested_release.release_manifest_ref,
            attested_release.source_identity,
            attested_release.build_identity,
            attested_release.artifact_identity,
            attested_release.artifact_digest,
        )
        if expected != attested:
            raise ReleaseIdentityVerificationError(
                "attested release does not match canonical manifest"
            )
        if artifact.artifact_identity != manifest.artifact_identity:
            raise ReleaseIdentityVerificationError(
                "canonical artifact identity mismatch"
            )
        if artifact.artifact_locator != manifest.artifact_locator:
            raise ReleaseIdentityVerificationError(
                "canonical artifact locator mismatch"
            )
        if computed_artifact_digest != manifest.artifact_digest:
            raise ReleaseIdentityVerificationError("canonical artifact digest mismatch")
        self._verify_evidence_claims(evidence_tuple, manifest, computed_artifact_digest)

        output_ids = {item.verifier_output_id for item in evidence_tuple}
        if len(output_ids) != 1:
            raise ReleaseIdentityVerificationError(
                "verifier outputs are not one mechanical transaction"
            )
        return VerifiedReleaseIdentity(
            source_identity=manifest.source_identity,
            build_identity=manifest.build_identity,
            artifact_identity=manifest.artifact_identity,
            artifact_digest=manifest.artifact_digest,
            manifest_ref=manifest.manifest_ref,
            runtime_instance_identity=runtime_instance_identity.value,
            verifier_output_id=next(iter(output_ids)),
            verified_at=datetime.now(timezone.utc),
            evidence=evidence_tuple,
        )

    def verify_provenance(
        self,
        *,
        profile: MarketProvenanceProfile,
        provenance: MarketProvenance,
        context: ProvenanceValidationContext,
        verified_identity: VerifiedReleaseIdentity | None,
        expected_profile_ref: str,
    ) -> VerifiedProvenance:
        if not isinstance(profile, MarketProvenanceProfile):
            raise ReleaseIdentityVerificationError("provenance profile is invalid")
        if not isinstance(provenance, MarketProvenance):
            raise ReleaseIdentityVerificationError("provenance is invalid")
        if not isinstance(context, ProvenanceValidationContext):
            raise ReleaseIdentityVerificationError("provenance context is invalid")
        if profile.profile_id != expected_profile_ref:
            raise ReleaseIdentityVerificationError(
                "provenance profile reference is unresolved"
            )
        if verified_identity is None:
            raise ReleaseIdentityVerificationError(
                "verified release identity evidence is missing"
            )
        declared = provenance.market_release_identity
        if (
            declared.source_identity != verified_identity.source_identity
            or declared.build_identity != verified_identity.build_identity
            or declared.artifact_identity != verified_identity.artifact_identity
            or declared.artifact_digest != verified_identity.artifact_digest.value
            or declared.release_manifest_ref != verified_identity.manifest_ref
        ):
            raise ReleaseIdentityVerificationError(
                "provenance release claim differs from verified release"
            )
        profile_result = validate_provenance_profile(profile, provenance, context)
        if not profile_result.complete:
            failed = ",".join(profile_result.failed_predicates)
            raise ReleaseIdentityVerificationError(
                f"mechanical provenance predicates failed: {failed}"
            )
        return VerifiedProvenance(
            profile_id=profile.profile_id,
            verified_release_identity=verified_identity,
            evaluated_predicates=profile_result.evaluated_predicates,
            provenance=provenance,
        )

    @staticmethod
    def _verify_evidence_closure(evidence: tuple[MechanicalEvidence, ...]) -> None:
        if not evidence:
            raise ReleaseIdentityVerificationError("verifier evidence is missing")
        purposes: list[EvidencePurpose] = []
        for item in evidence:
            if not isinstance(item, MechanicalEvidence):
                raise ReleaseIdentityVerificationError(
                    "verifier evidence has the wrong type"
                )
            if item.basis is ReleaseEvidenceBasis.DIRTY_TRACKED_CONTENT:
                raise ReleaseIdentityVerificationError(
                    "dirty tracked content cannot verify canonical release identity"
                )
            if item.basis is ReleaseEvidenceBasis.UNTRACKED_CONTENT:
                raise ReleaseIdentityVerificationError(
                    "untracked content cannot verify canonical release identity"
                )
            if item.basis is ReleaseEvidenceBasis.RUNTIME_CAPTURE:
                raise ReleaseIdentityVerificationError(
                    "runtime capture cannot verify canonical release identity"
                )
            purposes.append(item.purpose)
        missing = ReleaseIdentityVerifier.REQUIRED_PURPOSES.difference(purposes)
        if missing:
            names = ",".join(
                purpose.value
                for purpose in sorted(missing, key=lambda value: value.value)
            )
            raise ReleaseIdentityVerificationError(
                f"mechanical evidence purposes missing: {names}"
            )
        if len(purposes) != len(set(purposes)):
            raise ReleaseIdentityVerificationError(
                "mechanical evidence purposes are ambiguous"
            )

    @staticmethod
    def _verify_evidence_claims(
        evidence: tuple[MechanicalEvidence, ...],
        manifest: CanonicalReleaseManifest,
        computed_artifact_digest: ArtifactDigest,
    ) -> None:
        source_build_digest = ArtifactDigest(
            "sha256:"
            + hashlib.sha256(
                f"{manifest.source_identity}\0{manifest.build_identity}".encode("utf-8")
            ).hexdigest()
        )
        artifact_identity_digest = ArtifactDigest(
            "sha256:"
            + hashlib.sha256(manifest.artifact_identity.encode("utf-8")).hexdigest()
        )
        expected_by_purpose = {
            EvidencePurpose.MANIFEST: manifest.manifest_digest,
            EvidencePurpose.ARTIFACT_IDENTITY: artifact_identity_digest,
            EvidencePurpose.ARTIFACT_DIGEST: computed_artifact_digest,
            EvidencePurpose.SOURCE_BUILD_LINEAGE: source_build_digest,
        }
        for item in evidence:
            if item.subject_digest != expected_by_purpose[item.purpose]:
                raise ReleaseIdentityVerificationError(
                    f"mechanical {item.purpose.value} evidence claims a different subject"
                )


def complete_provenance(
    verified: VerifiedProvenance,
) -> MarketProvenance:
    provenance = verified.provenance
    return MarketProvenance(
        provenance_status=ProvenanceStatus.PROVENANCE_COMPLETE,
        market_release_identity=provenance.market_release_identity,
        produced_at=provenance.produced_at,
        source_refs=provenance.source_refs,
        evidence_refs=provenance.evidence_refs,
        public_object_refs=provenance.public_object_refs,
        data_cutoff=provenance.data_cutoff,
        capability_call_ref=provenance.capability_call_ref,
        correlation_id=provenance.correlation_id,
        governance_ref=provenance.governance_ref,
    )


def require_verified_result(
    envelope: MarketResultEnvelope,
    *,
    profile: MarketProvenanceProfile,
    context: ProvenanceValidationContext,
    verified_identity: VerifiedReleaseIdentity | None,
    expected_profile_ref: str,
) -> MarketResultEnvelope:
    if not isinstance(envelope, MarketResultEnvelope):
        raise ReleaseIdentityVerificationError("result envelope is invalid")
    if envelope.operation_status is not OperationStatus.SUCCESS:
        raise ReleaseIdentityVerificationError("result envelope is not successful")
    ReleaseIdentityVerifier().verify_provenance(
        profile=profile,
        provenance=envelope.provenance,
        context=context,
        verified_identity=verified_identity,
        expected_profile_ref=expected_profile_ref,
    )
    return envelope
