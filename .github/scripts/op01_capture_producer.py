#!/usr/bin/env python3
"""Fail-closed local-only OP01 capture and mechanical verifier.

RD1-V1 intentionally keeps authorization ownership separate from release evidence.
This producer therefore uses only deterministic Git/source identities, exact artifact
bytes, SHA-256 digests, a canonical manifest, and an explicit capture transaction.
It does not implement PKI, certificates, Sigstore, or a signing authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


AUTHORITY_ID = "RD1-V1-OP01A-MARKET-PRODUCT-READ-CAPTURE-V1"
REPOSITORY = "tonychang925-dev/ai_theme_app"
PRODUCER_BRANCH = "rd1-v1/op01/capture-producer"
SOURCE_BRANCH = "rd1-v1/g2c-market-product-read-p0"
PRODUCER_SCRIPT_PATH = Path(".github/scripts/op01_capture_producer.py")
EXPECTED_F = "a05661db2f111052cc4d9c55e8eb60ed5b1f4e80"
EXPECTED_M = "58bc839d6d90ce7847920dfdcf398fcdaf957855"
EXPECTED_M_PARENTS = (
    "b79a1692ba84cc093bf8ba4e721b2b8acff45f0e",
    "08f34f0c3148c17ada669e488e62a5ec678b6556",
)
RELEASE_TAG = "rd1-v1/op01/market-product-read/v1"
CANONICAL_REMOTES = {
    "https://github.com/tonychang925-dev/ai_theme_app.git",
    "ssh://git@github.com/tonychang925-dev/ai_theme_app.git",
    "git@github.com:tonychang925-dev/ai_theme_app.git",
}
CLOUD_EXECUTION_VARIABLES = (
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_EVENT_NAME",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_SHA",
    "GITHUB_WORKFLOW",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_WORKSPACE",
    "ImageOS",
    "RUNNER_ID",
    "RUNNER_NAME",
)
ASSET_NAMES = (
    "manifest.json",
    "artifact.bin",
    "capture-transaction.json",
)


class ProducerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GitIdentity:
    commit: str
    tree: str
    parents: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ProducerContext:
    repository: str
    producer_branch: str
    producer_commit: str
    source_branch: str
    source_commit: str
    source_tree: str
    merge_commit: str
    merge_tree: str


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def sha256_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _git(root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise ProducerError(
            f"git {' '.join(arguments)} failed: {result.stderr.strip()}"
        )
    return result.stdout


def _git_succeeds(root: Path, *arguments: str) -> bool:
    return (
        subprocess.run(
            ("git", "-C", str(root), *arguments),
            capture_output=True,
            text=True,
            check=False,
        ).returncode
        == 0
    )


def _require_full_sha(value: str, label: str) -> str:
    normalized = value.lower()
    if len(normalized) != 40 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ProducerError(f"{label} is not a full SHA-1 commit identity")
    return normalized


def _require_local_execution(environment: dict[str, str]) -> None:
    detected = [name for name in CLOUD_EXECUTION_VARIABLES if environment.get(name)]
    if detected:
        raise ProducerError(
            "cloud execution environment detected; local-only execution is required: "
            + ", ".join(detected)
        )


def _git_identity(root: Path, commit: str) -> GitIdentity:
    output = _git(root, "show", "-s", "--format=%H %T %P", commit)
    parts = output.strip().split()
    if len(parts) < 2:
        raise ProducerError(f"Git identity for {commit} is malformed")
    return GitIdentity(
        commit=_require_full_sha(parts[0], "commit SHA"),
        tree=_require_full_sha(parts[1], "tree SHA"),
        parents=tuple(_require_full_sha(value, "parent SHA") for value in parts[2:]),
    )


def _validate_clean(root: Path, label: str) -> None:
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if status:
        raise ProducerError(f"{label} checkout is dirty")
    modes = _git(root, "ls-tree", "-r", "HEAD")
    if any(line.startswith("160000 ") for line in modes.splitlines()):
        raise ProducerError(f"{label} checkout contains a submodule gitlink")
    tracked = _git(root, "ls-files", "-z")
    attributes = subprocess.run(
        ("git", "-C", str(root), "check-attr", "--stdin", "-z", "filter"),
        input=tracked.encode("utf-8"),
        capture_output=True,
        text=False,
        check=False,
    )
    if attributes.returncode != 0:
        raise ProducerError(f"{label} LFS attribute audit failed")
    if b"filter\x1flfs\x1f" in attributes.stdout.replace(b"\x00", b"\x1f"):
        raise ProducerError(f"{label} checkout contains LFS-smudged content")


def _require_remote(root: Path, label: str) -> None:
    remote = _git(root, "remote", "get-url", "origin").strip()
    if remote not in CANONICAL_REMOTES:
        raise ProducerError(f"{label} repository remote is not the frozen authority")


def _require_branch(root: Path, expected: str, label: str) -> None:
    branch = _git(root, "branch", "--show-current").strip()
    if branch != expected:
        raise ProducerError(f"{label} branch is not the exact frozen branch")


def _require_script_authority(producer_root: Path) -> None:
    if Path(__file__).resolve() != (producer_root / PRODUCER_SCRIPT_PATH).resolve():
        raise ProducerError("producer script is not loaded from the producer checkout")


def validate_git_contract(
    source_root: Path, producer_root: Path, producer_commit: str
) -> ProducerContext:
    _require_script_authority(producer_root)
    _validate_clean(source_root, "source")
    _validate_clean(producer_root, "producer")
    _require_remote(source_root, "source")
    _require_remote(producer_root, "producer")
    _require_branch(source_root, SOURCE_BRANCH, "source")
    _require_branch(producer_root, PRODUCER_BRANCH, "producer")

    expected_producer_commit = _require_full_sha(producer_commit, "producer commit SHA")
    actual_producer_commit = _require_full_sha(
        _git(producer_root, "rev-parse", "HEAD").strip(), "producer HEAD SHA"
    )
    if actual_producer_commit != expected_producer_commit:
        raise ProducerError("producer checkout is not at the exact producer SHA")

    source_head = _require_full_sha(
        _git(source_root, "rev-parse", "HEAD").strip(), "source HEAD SHA"
    )
    if source_head != EXPECTED_F:
        raise ProducerError("source checkout is not at exact F")

    source = _git_identity(source_root, EXPECTED_F)
    merge = _git_identity(source_root, EXPECTED_M)
    if merge.parents != EXPECTED_M_PARENTS:
        raise ProducerError("M parent order does not match the frozen contract")
    if not _git_succeeds(
        source_root, "merge-base", "--is-ancestor", EXPECTED_M, EXPECTED_F
    ):
        raise ProducerError("merge-base ancestry check failed")

    return ProducerContext(
        repository=REPOSITORY,
        producer_branch=PRODUCER_BRANCH,
        producer_commit=actual_producer_commit,
        source_branch=SOURCE_BRANCH,
        source_commit=source.commit,
        source_tree=source.tree,
        merge_commit=merge.commit,
        merge_tree=merge.tree,
    )


def _producer_context_with_git(
    environment: dict[str, str],
    source_root: Path,
    producer_root: Path,
    producer_commit: str,
) -> ProducerContext:
    _require_local_execution(environment)
    return validate_git_contract(source_root, producer_root, producer_commit)


def build_identities(
    context: ProducerContext, artifact_bytes: bytes
) -> tuple[str, str, str, str]:
    artifact_hex = hashlib.sha256(artifact_bytes).hexdigest()
    source_identity = (
        f"git-source:commit={context.source_commit}:tree={context.source_tree}"
    )
    build_identity = (
        f"local-executor:repository={context.repository}:"
        f"branch={context.producer_branch}:commit={context.producer_commit}"
    )
    artifact_identity = f"market-product-read:artifact:v1:sha256={artifact_hex}"
    artifact_digest = "sha256:" + artifact_hex
    return source_identity, build_identity, artifact_identity, artifact_digest


def build_manifest(
    source_identity: str,
    build_identity: str,
    artifact_identity: str,
    artifact_digest: str,
) -> bytes:
    projection = {
        "artifact_digest": artifact_digest,
        "artifact_identity": artifact_identity,
        "artifact_locator": "canonical:artifact.bin",
        "build_identity": build_identity,
        "profile_id": "market-product-judgment-v1",
        "source_identity": source_identity,
    }
    manifest_ref = (
        "market-product-read:manifest:v1:sha256:"
        + hashlib.sha256(canonical_json(projection)).hexdigest()
    )
    return canonical_json({**projection, "manifest_ref": manifest_ref})


def generate_uuidv7() -> str:
    milliseconds = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = int.from_bytes(secrets.token_bytes(2), "big") & 0x0FFF
    random_b = int.from_bytes(secrets.token_bytes(8), "big") & ((1 << 62) - 1)
    value = (
        (milliseconds << 80) | (0x7 << 76) | (random_a << 64) | (0x2 << 62) | random_b
    )
    return str(uuid.UUID(int=value))


def generate_runtime_identity(generator: Callable[[], str]) -> str:
    return f"market-product-read:runtime:v1:uuid={generator()}"


def build_capture_bundle(
    context: ProducerContext, artifact_bytes: bytes, runtime_identity: str
) -> tuple[bytes, bytes, bytes]:
    source_identity, build_identity, artifact_identity, artifact_digest = (
        build_identities(context, artifact_bytes)
    )
    manifest_bytes = build_manifest(
        source_identity, build_identity, artifact_identity, artifact_digest
    )
    manifest_digest = sha256_digest(manifest_bytes)
    artifact_digest_bytes = sha256_digest(artifact_bytes)
    subject_by_purpose = {
        "MANIFEST": manifest_digest,
        "ARTIFACT_IDENTITY": sha256_digest(artifact_identity.encode("utf-8")),
        "ARTIFACT_DIGEST": artifact_digest_bytes,
        "SOURCE_BUILD_LINEAGE": sha256_digest(
            f"{source_identity}\0{build_identity}".encode("utf-8")
        ),
    }
    verifier_preimage = canonical_json(
        {
            "artifact_digest": artifact_digest_bytes,
            "artifact_identity": artifact_identity,
            "authority_id": AUTHORITY_ID,
            "build_identity": build_identity,
            "manifest_digest": manifest_digest,
            "runtime_instance_identity": runtime_identity,
            "source_identity": source_identity,
            "subject_digest_by_purpose": subject_by_purpose,
        }
    )
    verifier_output_id = "op01b:sha256:" + hashlib.sha256(verifier_preimage).hexdigest()
    basis_by_purpose = {
        "MANIFEST": "EXPLICIT_CAPTURED_ARTIFACT",
        "ARTIFACT_IDENTITY": "EXPLICIT_CAPTURED_ARTIFACT",
        "ARTIFACT_DIGEST": "EXPLICIT_CAPTURED_ARTIFACT",
        "SOURCE_BUILD_LINEAGE": "CLEAN_REPOSITORY_SNAPSHOT",
    }
    evidence = [
        {
            "basis": basis_by_purpose[purpose],
            "purpose": purpose,
            "subject_digest": subject_by_purpose[purpose],
            "verifier_output_id": verifier_output_id,
        }
        for purpose in sorted(subject_by_purpose)
    ]
    transaction = {
        "ancestry": {
            "integration_commit": context.source_commit,
            "integration_tree": context.source_tree,
            "merge_commit": context.merge_commit,
            "merge_tree": context.merge_tree,
            "parents_in_order": list(EXPECTED_M_PARENTS),
        },
        "artifact": {
            "byte_length": len(artifact_bytes),
            "digest": artifact_digest_bytes,
            "locator": "artifact.bin",
        },
        "asset_names": list(ASSET_NAMES),
        "authority_id": AUTHORITY_ID,
        "build_identity": build_identity,
        "evidence": evidence,
        "manifest": {
            "byte_length": len(manifest_bytes),
            "digest": manifest_digest,
            "reference": json.loads(manifest_bytes)["manifest_ref"],
        },
        "market_release_identity": {
            "artifact_digest": artifact_digest_bytes,
            "artifact_identity": artifact_identity,
            "build_identity": build_identity,
            "release_manifest_ref": json.loads(manifest_bytes)["manifest_ref"],
            "source_identity": source_identity,
        },
        "producer": {
            "execution_boundary": "LOCAL_ONLY",
            "producer_branch": context.producer_branch,
            "producer_commit": context.producer_commit,
            "repository": context.repository,
            "source_branch": context.source_branch,
            "source_commit": context.source_commit,
        },
        "release": {"tag": RELEASE_TAG, "target_commit": context.source_commit},
        "runtime_instance_identity": runtime_identity,
        "source_identity": source_identity,
        "spec_version": "1.0",
        "status": "CAPTURED_UNVERIFIED",
        "verifier_output_id": verifier_output_id,
    }
    return manifest_bytes, canonical_json(transaction), artifact_bytes


def _validate_asset_layout(root: Path) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ProducerError("output root is not a regular directory")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != set(ASSET_NAMES):
        raise ProducerError("output asset layout is not exact")
    for entry in entries:
        if entry.is_symlink() or not entry.is_file():
            raise ProducerError(f"output asset is not a regular file: {entry.name}")
        if entry.stat().st_mode & 0o777 != 0o644:
            raise ProducerError(f"output asset mode is not 0644: {entry.name}")


def _write_asset(root: Path, name: str, content: bytes) -> None:
    path = root / name
    path.write_bytes(content)
    path.chmod(0o644)


def _generate_archive(source_root: Path, output_root: Path) -> bytes:
    output_root.mkdir(parents=True, exist_ok=False)
    artifact_path = (output_root / "artifact.bin").resolve()
    result = subprocess.run(
        (
            "git",
            "-C",
            str(source_root),
            "archive",
            "--format=tar",
            "--output",
            str(artifact_path),
            EXPECTED_F,
        ),
        check=False,
    )
    if result.returncode != 0:
        raise ProducerError("exact git archive generation failed")
    return artifact_path.read_bytes()


def _exact_archive_bytes(source_root: Path) -> bytes:
    result = subprocess.run(
        ("git", "-C", str(source_root), "archive", "--format=tar", EXPECTED_F),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ProducerError("exact git archive verification failed")
    return result.stdout


def _verify_capture_bundle(
    context: ProducerContext, source_root: Path, output_root: Path
) -> None:
    _validate_asset_layout(output_root)
    artifact_bytes = (output_root / "artifact.bin").read_bytes()
    if artifact_bytes != _exact_archive_bytes(source_root):
        raise ProducerError("artifact.bin is not the exact git archive of F")

    manifest_bytes = (output_root / "manifest.json").read_bytes()
    transaction_bytes = (output_root / "capture-transaction.json").read_bytes()
    try:
        transaction = json.loads(transaction_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProducerError("capture transaction is not valid JSON") from error

    runtime_identity = transaction.get("runtime_instance_identity")
    if not isinstance(runtime_identity, str) or not runtime_identity:
        raise ProducerError("capture transaction runtime identity is invalid")

    expected_manifest, expected_transaction, _ = build_capture_bundle(
        context, artifact_bytes, runtime_identity
    )
    if manifest_bytes != expected_manifest:
        raise ProducerError("manifest bytes do not match the canonical projection")
    if transaction_bytes != expected_transaction:
        raise ProducerError("capture transaction bytes do not match the capture contract")


def _add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--producer-root", type=Path, required=True)
    parser.add_argument("--producer-sha", required=True)
    parser.add_argument("--output-root", type=Path, required=True)


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    _add_common_arguments(subparsers.add_parser("capture"))
    _add_common_arguments(subparsers.add_parser("verify"))
    return parser.parse_args(argv)


def _context_from_arguments(arguments: argparse.Namespace) -> ProducerContext:
    return _producer_context_with_git(
        dict(os.environ),
        arguments.source_root,
        arguments.producer_root,
        arguments.producer_sha,
    )


def _capture(arguments: argparse.Namespace) -> None:
    context = _context_from_arguments(arguments)
    artifact_bytes = _generate_archive(arguments.source_root, arguments.output_root)
    manifest_bytes, transaction_bytes, _ = build_capture_bundle(
        context, artifact_bytes, generate_runtime_identity(generate_uuidv7)
    )
    _write_asset(arguments.output_root, "manifest.json", manifest_bytes)
    _write_asset(arguments.output_root, "capture-transaction.json", transaction_bytes)
    _validate_asset_layout(arguments.output_root)


def _verify(arguments: argparse.Namespace) -> None:
    context = _context_from_arguments(arguments)
    _verify_capture_bundle(context, arguments.source_root, arguments.output_root)


def run(argv: list[str] | None = None) -> None:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.command == "capture":
        _capture(arguments)
    else:
        _verify(arguments)


if __name__ == "__main__":
    try:
        run()
    except ProducerError as error:
        print(f"producer failed closed: {error}", file=sys.stderr)
        raise SystemExit(1)
