"""Readers that select only explicit canonical release inputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from stock_processing_service.application.identity.models import ArtifactDigest
from stock_processing_service.application.identity.release_identity_verifier import (
    CanonicalArtifact,
    CanonicalReleaseManifest,
)


@dataclass(frozen=True, slots=True)
class ManifestLocator:
    root: Path
    relative_path: str


@dataclass(frozen=True, slots=True)
class ArtifactLocator:
    root: Path
    relative_path: str


def _resolve(locator: ManifestLocator | ArtifactLocator, label: str) -> Path:
    root = locator.root.resolve()
    candidate = (root / locator.relative_path).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError(f"{label} locator escapes canonical root")
    if not candidate.is_file():
        raise ValueError(f"{label} does not select a canonical file")
    return candidate


def _digest(value: bytes) -> ArtifactDigest:
    return ArtifactDigest("sha256:" + hashlib.sha256(value).hexdigest())


def read_canonical_manifest(locator: ManifestLocator) -> CanonicalReleaseManifest:
    path = _resolve(locator, "manifest locator")
    raw = path.read_bytes()
    document = json.loads(raw.decode("utf-8"))
    required = {
        "manifest_ref",
        "profile_id",
        "source_identity",
        "build_identity",
        "artifact_identity",
        "artifact_digest",
        "artifact_locator",
    }
    if not isinstance(document, dict) or not required.issubset(document):
        raise ValueError("canonical manifest fields are missing")
    if any(
        not isinstance(document[field], str) or not document[field].strip()
        for field in required
    ):
        raise ValueError("canonical manifest fields must be non-empty strings")
    if not document["artifact_locator"].startswith("canonical:"):
        raise ValueError("artifact locator is not canonical")
    return CanonicalReleaseManifest(
        manifest_ref=document["manifest_ref"],
        profile_id=document["profile_id"],
        source_identity=document["source_identity"],
        build_identity=document["build_identity"],
        artifact_identity=document["artifact_identity"],
        artifact_digest=ArtifactDigest(document["artifact_digest"]),
        artifact_locator=document["artifact_locator"].removeprefix("canonical:"),
        manifest_digest=_digest(raw),
    )


def read_canonical_artifact(
    locator: ArtifactLocator, expected_artifact_identity: str
) -> CanonicalArtifact:
    path = _resolve(locator, "artifact locator")
    return CanonicalArtifact(
        artifact_identity=expected_artifact_identity,
        artifact_locator=locator.relative_path,
        bytes_=path.read_bytes(),
    )


def calculate_artifact_digest(artifact: CanonicalArtifact) -> ArtifactDigest:
    if not isinstance(artifact, CanonicalArtifact):
        raise ValueError("digest input must be a canonical artifact")
    return _digest(artifact.bytes_)
