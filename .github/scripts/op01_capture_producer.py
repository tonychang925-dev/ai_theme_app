#!/usr/bin/env python3
"""Fail-closed producer for the frozen OP01-A capture contract."""

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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable


AUTHORITY_ID = "RD1-V1-OP01A-MARKET-PRODUCT-READ-CAPTURE-V1"
REPOSITORY = "tonychang925-dev/ai_theme_app"
PRODUCER_BRANCH = "rd1-v1/op01/capture-producer"
WORKFLOW_PATH = ".github/workflows/rd1-v1-op01-market-release-capture.yml"
EXPECTED_WORKFLOW_REF = f"{REPOSITORY}/{WORKFLOW_PATH}@refs/heads/{PRODUCER_BRANCH}"
EXPECTED_F = "a05661db2f111052cc4d9c55e8eb60ed5b1f4e80"
EXPECTED_M = "58bc839d6d90ce7847920dfdcf398fcdaf957855"
EXPECTED_M_PARENTS = (
    "b79a1692ba84cc093bf8ba4e721b2b8acff45f0e",
    "08f34f0c3148c17ada669e488e62a5ec678b6556",
)
EXPECTED_ACTOR = "tonychang925-dev"
RELEASE_TAG = "rd1-v1/op01/market-product-read/v1"
ASSET_NAMES = (
    "manifest.json",
    "artifact.bin",
    "capture-transaction.json",
    "capture-transaction.sigstore.json",
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
    actor: str
    triggering_actor: str
    event_name: str
    runner_image_os: str
    workflow_path: str
    workflow_sha: str
    workflow_ref: str
    run_id: str
    run_attempt: str
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


def _git(source_root: Path, *arguments: str, check: bool = True) -> str:
    result = subprocess.run(
        ("git", "-C", str(source_root), *arguments),
        capture_output=True,
        text=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise ProducerError(
            f"git {' '.join(arguments)} failed: {result.stderr.strip()}"
        )
    return result.stdout


def _git_succeeds(source_root: Path, *arguments: str) -> bool:
    return (
        subprocess.run(
            ("git", "-C", str(source_root), *arguments),
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


def _require_environment(environment: dict[str, str]) -> ProducerContext:
    required = (
        "GITHUB_REPOSITORY",
        "GITHUB_ACTOR",
        "GITHUB_TRIGGERING_ACTOR",
        "GITHUB_EVENT_NAME",
        "ImageOS",
        "GITHUB_WORKFLOW_REF",
        "GITHUB_WORKFLOW_SHA",
        "GITHUB_RUN_ID",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_SHA",
        "GITHUB_WORKSPACE",
    )
    if any(not environment.get(name) for name in required):
        raise ProducerError("a required GitHub Actions identity is missing")
    if environment["GITHUB_REPOSITORY"] != REPOSITORY:
        raise ProducerError("capture repository is not the frozen authority")
    if environment["GITHUB_ACTOR"] != EXPECTED_ACTOR:
        raise ProducerError("workflow actor is not the repository owner")
    if environment["GITHUB_TRIGGERING_ACTOR"] != EXPECTED_ACTOR:
        raise ProducerError("workflow triggering actor is not the repository owner")
    if environment["GITHUB_EVENT_NAME"] != "workflow_dispatch":
        raise ProducerError("workflow event is not workflow_dispatch")
    if environment["ImageOS"] != "ubuntu24":
        raise ProducerError("runner image is not ubuntu-24.04")
    workflow_ref = environment["GITHUB_WORKFLOW_REF"]
    if workflow_ref != EXPECTED_WORKFLOW_REF:
        raise ProducerError("workflow is not running on the frozen producer branch")
    workflow_sha = _require_full_sha(environment["GITHUB_WORKFLOW_SHA"], "workflow SHA")
    workflow_commit_sha = _require_full_sha(
        environment["GITHUB_SHA"], "workflow commit SHA"
    )
    if workflow_sha != workflow_commit_sha:
        raise ProducerError("workflow SHA and workflow commit SHA disagree")
    return ProducerContext(
        repository=environment["GITHUB_REPOSITORY"],
        actor=environment["GITHUB_ACTOR"],
        triggering_actor=environment["GITHUB_TRIGGERING_ACTOR"],
        event_name=environment["GITHUB_EVENT_NAME"],
        runner_image_os=environment["ImageOS"],
        workflow_path=WORKFLOW_PATH,
        workflow_sha=workflow_sha,
        workflow_ref=workflow_ref,
        run_id=environment["GITHUB_RUN_ID"],
        run_attempt=environment["GITHUB_RUN_ATTEMPT"],
        source_commit="",
        source_tree="",
        merge_commit="",
        merge_tree="",
    )


def _git_identity(source_root: Path, commit: str) -> GitIdentity:
    output = _git(source_root, "show", "-s", "--format=%H %T %P", commit)
    parts = output.strip().split()
    if len(parts) < 2:
        raise ProducerError(f"Git identity for {commit} is malformed")
    parents = tuple(_require_full_sha(value, "parent SHA") for value in parts[2:])
    return GitIdentity(
        commit=_require_full_sha(parts[0], "commit SHA"),
        tree=_require_full_sha(parts[1], "tree SHA"),
        parents=parents,
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
        input=tracked,
        capture_output=True,
        text=False,
        check=False,
    )
    if attributes.returncode != 0:
        raise ProducerError(f"{label} LFS attribute audit failed")
    if b"filter\x1flfs\x1f" in attributes.stdout.replace(b"\x00", b"\x1f"):
        raise ProducerError(f"{label} checkout contains LFS-smudged content")


def validate_git_contract(
    source_root: Path,
    workflow_root: Path,
    integration_commit: str,
    context: ProducerContext,
) -> ProducerContext:
    candidate = _require_full_sha(integration_commit, "integration commit")
    if candidate != EXPECTED_F:
        raise ProducerError("integration commit is not the exact frozen candidate F")
    _validate_clean(workflow_root, "workflow")
    _validate_clean(source_root, "source")
    source = _git_identity(source_root, candidate)
    merge = _git_identity(source_root, EXPECTED_M)
    if source.commit != EXPECTED_F:
        raise ProducerError("source commit changed during identity resolution")
    if merge.commit != EXPECTED_M:
        raise ProducerError("merge commit changed during identity resolution")
    if merge.parents != EXPECTED_M_PARENTS:
        raise ProducerError("M parent order does not match the frozen contract")
    if not _git_succeeds(
        source_root, "merge-base", "--is-ancestor", EXPECTED_M, EXPECTED_F
    ):
        raise ProducerError("merge-base ancestry check failed")
    if _git(source_root, "rev-parse", "HEAD") != f"{EXPECTED_F}\n":
        raise ProducerError("source checkout is not at exact F")
    workflow_identity = _git_identity(workflow_root, context.workflow_sha)
    if workflow_identity.commit != context.workflow_sha:
        raise ProducerError("workflow checkout is not at the exact workflow SHA")
    workflow_file = workflow_root / WORKFLOW_PATH
    if not workflow_file.is_file() or workflow_file.is_symlink():
        raise ProducerError("producer workflow path is invalid")
    return replace(
        context,
        source_commit=source.commit,
        source_tree=source.tree,
        merge_commit=merge.commit,
        merge_tree=merge.tree,
    )


def build_identities(
    context: ProducerContext, artifact_bytes: bytes
) -> tuple[str, str, str, str]:
    artifact_hex = hashlib.sha256(artifact_bytes).hexdigest()
    source_identity = (
        f"git-source:commit={context.source_commit}:tree={context.source_tree}"
    )
    build_identity = (
        "github-actions:owner=tonychang925-dev:repo=ai_theme_app:"
        f"workflow=rd1-v1-op01-market-release-capture.yml@{context.workflow_sha}:"
        f"run={context.run_id}:attempt={context.run_attempt}"
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
    manifest = {**projection, "manifest_ref": manifest_ref}
    return canonical_json(manifest)


def generate_runtime_identity(generator: Callable[[], str]) -> str:
    return f"market-product-read:runtime:v1:uuid={generator()}"


def generate_uuidv7() -> str:
    milliseconds = int(time.time() * 1000) & ((1 << 48) - 1)
    random_a = int.from_bytes(secrets.token_bytes(2), "big") & 0x0FFF
    random_b = int.from_bytes(secrets.token_bytes(8), "big") & ((1 << 62) - 1)
    value = (
        (milliseconds << 80) | (0x7 << 76) | (random_a << 64) | (0x2 << 62) | random_b
    )
    return str(uuid.UUID(int=value))


def build_capture_bundle(
    context: ProducerContext,
    artifact_bytes: bytes,
    runtime_identity: str,
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
            "release_manifest_ref": json.loads(manifest_bytes)["manifest_ref"],
            "build_identity": build_identity,
            "source_identity": source_identity,
        },
        "producer": {
            "actor": context.actor,
            "event": context.event_name,
            "repository": context.repository,
            "run_attempt": context.run_attempt,
            "run_id": context.run_id,
            "runner": "ubuntu-24.04",
            "triggering_actor": context.triggering_actor,
            "workflow_path": context.workflow_path,
            "workflow_ref": context.workflow_ref,
            "workflow_sha": context.workflow_sha,
        },
        "release": {"tag": RELEASE_TAG, "target_commit": context.source_commit},
        "runtime_instance_identity": runtime_identity,
        "source_identity": source_identity,
        "spec_version": "1.0",
        "status": "CAPTURED_UNVERIFIED",
        "verifier_output_id": verifier_output_id,
    }
    return manifest_bytes, canonical_json(transaction), artifact_bytes


def _producer_context_with_git(
    environment: dict[str, str],
    source_root: Path,
    workflow_root: Path,
    integration_commit: str,
) -> ProducerContext:
    context = _require_environment(environment)
    return validate_git_contract(
        source_root, workflow_root, integration_commit, context
    )


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--integration-commit", required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--workflow-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> None:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    context = _producer_context_with_git(
        dict(os.environ),
        arguments.source_root,
        arguments.workflow_root,
        arguments.integration_commit,
    )
    output_root = arguments.output_root
    output_root.mkdir(parents=True, exist_ok=False)
    artifact_path = output_root / "artifact.bin"
    archive = subprocess.run(
        (
            "git",
            "-C",
            str(arguments.source_root),
            "archive",
            "--format=tar",
            "--output",
            str(artifact_path),
            EXPECTED_F,
        ),
        check=False,
    )
    if archive.returncode != 0:
        raise ProducerError("exact git archive generation failed")
    artifact_bytes = artifact_path.read_bytes()
    runtime_identity = generate_runtime_identity(generate_uuidv7)
    manifest_bytes, transaction_bytes, _ = build_capture_bundle(
        context, artifact_bytes, runtime_identity
    )
    (output_root / "manifest.json").write_bytes(manifest_bytes)
    (output_root / "capture-transaction.json").write_bytes(transaction_bytes)


if __name__ == "__main__":
    try:
        run()
    except ProducerError as error:
        print(f"producer failed closed: {error}", file=sys.stderr)
        raise SystemExit(1)
