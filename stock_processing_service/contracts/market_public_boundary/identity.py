from __future__ import annotations

from dataclasses import dataclass


def _require_non_empty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class MarketReleaseIdentity:
    source_identity: str
    build_identity: str
    artifact_identity: str
    artifact_digest: str
    release_manifest_ref: str

    def __post_init__(self) -> None:
        for field_name, value in (
            ("source_identity", self.source_identity),
            ("build_identity", self.build_identity),
            ("artifact_identity", self.artifact_identity),
            ("artifact_digest", self.artifact_digest),
            ("release_manifest_ref", self.release_manifest_ref),
        ):
            _require_non_empty(value, field_name)

        pairs = (
            ("source_identity", "build_identity"),
            ("build_identity", "artifact_identity"),
            ("artifact_identity", "artifact_digest"),
        )
        for left_name, right_name in pairs:
            left = getattr(self, left_name)
            right = getattr(self, right_name)
            if left == right:
                raise ValueError(f"{left_name} must differ from {right_name}")


@dataclass(frozen=True, slots=True)
class MarketObjectRef:
    object_type: str
    object_id: str | int
    revision_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.object_type, "object_type")
        if not isinstance(self.object_id, (str, int)) or isinstance(self.object_id, bool):
            raise ValueError("object_id must be a public string or integer identifier")
        if isinstance(self.object_id, str) and not self.object_id.strip():
            raise ValueError("object_id must be non-empty")
        if self.revision_id is not None:
            _require_non_empty(self.revision_id, "revision_id")


@dataclass(frozen=True, slots=True)
class MarketBoundaryIdentity:
    provider_id: str
    public_contract_name: str
    public_contract_version: str
    release_identity: MarketReleaseIdentity
    supported_capabilities: tuple[str, ...]
    supported_object_types: tuple[str, ...]

    def __post_init__(self) -> None:
        for field_name, value in (
            ("provider_id", self.provider_id),
            ("public_contract_name", self.public_contract_name),
            ("public_contract_version", self.public_contract_version),
        ):
            _require_non_empty(value, field_name)
        if not isinstance(self.release_identity, MarketReleaseIdentity):
            raise ValueError("release_identity must be a MarketReleaseIdentity")
        for field_name, values in (
            ("supported_capabilities", self.supported_capabilities),
            ("supported_object_types", self.supported_object_types),
        ):
            if not isinstance(values, tuple) or not values:
                raise ValueError(f"{field_name} must be a non-empty tuple")
            if any(not isinstance(value, str) or not value.strip() for value in values):
                raise ValueError(f"{field_name} entries must be non-empty strings")
            if len(set(values)) != len(values):
                raise ValueError(f"{field_name} entries must be unique")
