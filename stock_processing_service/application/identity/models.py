"""Mechanically separated identity and noncanonical evidence records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


def _require_identifier(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


@dataclass(frozen=True, slots=True)
class SourceIdentity:
    value: str

    def __post_init__(self) -> None:
        _require_identifier(self.value, "source_identity")


@dataclass(frozen=True, slots=True)
class BuildIdentity:
    value: str

    def __post_init__(self) -> None:
        _require_identifier(self.value, "build_identity")


@dataclass(frozen=True, slots=True)
class ArtifactIdentity:
    value: str

    def __post_init__(self) -> None:
        _require_identifier(self.value, "artifact_identity")


@dataclass(frozen=True, slots=True)
class ArtifactDigest:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not self.value.startswith("sha256:"):
            raise ValueError("artifact_digest must use the explicit sha256 algorithm")
        digest = self.value.removeprefix("sha256:")
        if len(digest) != 64 or any(
            character not in "0123456789abcdef" for character in digest
        ):
            raise ValueError(
                "artifact_digest must contain 64 lowercase hexadecimal digits"
            )


@dataclass(frozen=True, slots=True)
class RuntimeInstanceIdentity:
    value: str

    def __post_init__(self) -> None:
        _require_identifier(self.value, "runtime_instance_identity")


@dataclass(frozen=True, slots=True)
class IdentityBundle:
    source_identity: SourceIdentity
    build_identity: BuildIdentity
    artifact_identity: ArtifactIdentity
    artifact_digest: ArtifactDigest
    runtime_instance_identity: RuntimeInstanceIdentity

    def __post_init__(self) -> None:
        fields = (
            ("source_identity", self.source_identity, SourceIdentity),
            ("build_identity", self.build_identity, BuildIdentity),
            ("artifact_identity", self.artifact_identity, ArtifactIdentity),
            ("artifact_digest", self.artifact_digest, ArtifactDigest),
            (
                "runtime_instance_identity",
                self.runtime_instance_identity,
                RuntimeInstanceIdentity,
            ),
        )
        values: list[str] = []
        for field_name, value, expected_type in fields:
            if not isinstance(value, expected_type):
                raise ValueError(f"{field_name} has the wrong identity type")
            values.append(value.value)
        if len(set(values)) != len(values):
            raise ValueError(
                "source, build, artifact, digest, and runtime identities must all differ"
            )


class ReleaseEvidenceBasis(str, Enum):
    PROVIDER_ATTESTED = "PROVIDER_ATTESTED"
    CLEAN_REPOSITORY_SNAPSHOT = "CLEAN_REPOSITORY_SNAPSHOT"
    EXPLICIT_CAPTURED_ARTIFACT = "EXPLICIT_CAPTURED_ARTIFACT"
    DIRTY_TRACKED_CONTENT = "DIRTY_TRACKED_CONTENT"
    UNTRACKED_CONTENT = "UNTRACKED_CONTENT"
    RUNTIME_CAPTURE = "RUNTIME_CAPTURE"


class EvidencePurpose(str, Enum):
    MANIFEST = "MANIFEST"
    ARTIFACT_IDENTITY = "ARTIFACT_IDENTITY"
    ARTIFACT_DIGEST = "ARTIFACT_DIGEST"
    SOURCE_BUILD_LINEAGE = "SOURCE_BUILD_LINEAGE"


@dataclass(frozen=True, slots=True)
class MechanicalEvidence:
    purpose: EvidencePurpose
    basis: ReleaseEvidenceBasis
    subject_digest: ArtifactDigest
    verifier_output_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.purpose, EvidencePurpose):
            raise ValueError("evidence purpose has the wrong type")
        if not isinstance(self.basis, ReleaseEvidenceBasis):
            raise ValueError("release evidence basis has the wrong type")
        if not isinstance(self.subject_digest, ArtifactDigest):
            raise ValueError("evidence subject digest has the wrong type")
        _require_identifier(self.verifier_output_id, "verifier_output_id")
        if self.basis is ReleaseEvidenceBasis.PROVIDER_ATTESTED:
            raise ValueError("provider attestation is not mechanical verifier evidence")


@dataclass(frozen=True, slots=True)
class CapturedSourceEvidence:
    capture_id: str
    basis: ReleaseEvidenceBasis
    content_digest: ArtifactDigest

    def __post_init__(self) -> None:
        _require_identifier(self.capture_id, "capture_id")
        if not isinstance(self.basis, ReleaseEvidenceBasis):
            raise ValueError("captured source evidence basis has the wrong type")
        if not isinstance(self.content_digest, ArtifactDigest):
            raise ValueError("captured source digest has the wrong type")

    @property
    def canonical_source(self) -> bool:
        return self.basis in (
            ReleaseEvidenceBasis.CLEAN_REPOSITORY_SNAPSHOT,
            ReleaseEvidenceBasis.EXPLICIT_CAPTURED_ARTIFACT,
        )


@dataclass(frozen=True, slots=True)
class SemanticReconstruction:
    reconstruction_id: str
    evidence: tuple[CapturedSourceEvidence, ...]

    def __post_init__(self) -> None:
        _require_identifier(self.reconstruction_id, "reconstruction_id")
        if not isinstance(self.evidence, tuple) or not self.evidence:
            raise ValueError(
                "semantic reconstruction requires explicit captured evidence"
            )
        if any(not isinstance(item, CapturedSourceEvidence) for item in self.evidence):
            raise ValueError("semantic reconstruction contains invalid evidence")

    @property
    def evidence_bases(self) -> tuple[ReleaseEvidenceBasis, ...]:
        return tuple(item.basis for item in self.evidence)

    @property
    def canonical_source(self) -> bool:
        return bool(self.evidence) and all(
            item.canonical_source for item in self.evidence
        )


@dataclass(frozen=True, slots=True)
class CompatibilityLineage:
    source_trace_id: str

    def __post_init__(self) -> None:
        _require_identifier(self.source_trace_id, "source_trace_id")


def validate_compatibility_lineage(
    lineage: CompatibilityLineage, identities: IdentityBundle
) -> CompatibilityLineage:
    if not isinstance(lineage, CompatibilityLineage):
        raise ValueError("lineage must be CompatibilityLineage")
    if not isinstance(identities, IdentityBundle):
        raise ValueError("identities must be IdentityBundle")
    values = (
        identities.source_identity.value,
        identities.build_identity.value,
        identities.artifact_identity.value,
        identities.artifact_digest.value,
        identities.runtime_instance_identity.value,
    )
    if lineage.source_trace_id in values:
        raise ValueError(
            "source_trace_id is compatibility lineage, not release identity"
        )
    return lineage


def validate_semantic_reconstruction(
    reconstruction: SemanticReconstruction, *, require_canonical_source: bool
) -> SemanticReconstruction:
    if not isinstance(reconstruction, SemanticReconstruction):
        raise ValueError("reconstruction must be SemanticReconstruction")
    if not reconstruction.evidence:
        raise ValueError("semantic reconstruction has no captured evidence")
    if require_canonical_source and not reconstruction.canonical_source:
        bases = ",".join(basis.value for basis in reconstruction.evidence_bases)
        raise ValueError(f"semantic reconstruction source is noncanonical: {bases}")
    return reconstruction
