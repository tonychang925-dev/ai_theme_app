#!/usr/bin/env python3
"""Fail-closed local-only producer for the frozen OP01-A capture contract."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, padding, rsa
from cryptography.x509 import (
    BasicConstraints,
    ExtendedKeyUsage,
    Extension,
    ExtensionNotFound,
    KeyUsage,
    load_der_x509_certificate,
    load_pem_x509_certificate,
)
from cryptography.x509.oid import ExtendedKeyUsageOID


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
CAPTURE_ASSET_NAMES = (
    "manifest.json",
    "artifact.bin",
    "capture-transaction.json",
)
ASSET_NAMES = (*CAPTURE_ASSET_NAMES, "capture-transaction.sigstore.json")
SIGSTORE_BUNDLE_MEDIA_TYPE = "application/vnd.dev.sigstore.bundle+json"
IN_TOTO_PAYLOAD_TYPE = "application/vnd.in-toto+json"


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


def _require_local_execution(environment: dict[str, str]) -> None:
    detected = [name for name in CLOUD_EXECUTION_VARIABLES if environment.get(name)]
    if detected:
        raise ProducerError(
            "cloud execution environment detected; local-only execution is required: "
            + ", ".join(detected)
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
    script_path = Path(__file__).resolve()
    expected_path = (producer_root / PRODUCER_SCRIPT_PATH).resolve()
    if script_path != expected_path:
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
        _git(producer_root, "rev-parse", "HEAD").strip(),
        "producer HEAD SHA",
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
            "release_manifest_ref": json.loads(manifest_bytes)["manifest_ref"],
            "build_identity": build_identity,
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


def _validate_asset_layout(root: Path, expected_names: tuple[str, ...]) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ProducerError("output root is not a regular directory")
    entries = list(root.iterdir())
    if {entry.name for entry in entries} != set(expected_names):
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
    archive = subprocess.run(
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
    if archive.returncode != 0:
        raise ProducerError("exact git archive generation failed")
    return artifact_path.read_bytes()


def _exact_archive_bytes(source_root: Path) -> bytes:
    result = subprocess.run(
        (
            "git",
            "-C",
            str(source_root),
            "archive",
            "--format=tar",
            EXPECTED_F,
        ),
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        raise ProducerError("exact git archive verification failed")
    return result.stdout


def _decode_base64(value: Any, label: str) -> bytes:
    if not isinstance(value, str):
        raise ProducerError(f"Sigstore bundle {label} is not textual")
    try:
        return base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as error:
        raise ProducerError(f"Sigstore bundle {label} is not valid base64") from error


def _load_certificate(path: Path):
    if path.is_symlink() or not path.is_file():
        raise ProducerError("local trust root path is invalid")
    encoded = path.read_bytes()
    try:
        return load_pem_x509_certificate(encoded)
    except ValueError:
        try:
            return load_der_x509_certificate(encoded)
        except ValueError as error:
            raise ProducerError(
                "local trust root is not a valid X.509 certificate"
            ) from error


def _verify_certificate_signature(child, issuer) -> None:
    if child.issuer != issuer.subject:
        raise ProducerError("Sigstore certificate issuer identity does not match")
    public_key = issuer.public_key()
    try:
        if isinstance(public_key, ed25519.Ed25519PublicKey):
            public_key.verify(child.signature, child.tbs_certificate_bytes)
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(
                child.signature,
                child.tbs_certificate_bytes,
                ec.ECDSA(child.signature_hash_algorithm),
            )
        elif isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(
                child.signature,
                child.tbs_certificate_bytes,
                padding.PKCS1v15(),
                child.signature_hash_algorithm,
            )
        else:
            raise ProducerError(
                "Sigstore certificate public-key algorithm is unsupported"
            )
    except InvalidSignature as error:
        raise ProducerError(
            "Sigstore certificate chain signature is invalid"
        ) from error


def _require_certificate_time(certificate) -> None:
    now = datetime.now(timezone.utc)
    if certificate.not_valid_before_utc > now:
        raise ProducerError("Sigstore certificate is not yet valid")
    if certificate.not_valid_after_utc <= now:
        raise ProducerError("Sigstore certificate is expired")


def _require_extension(certificate, extension_class) -> Extension:
    try:
        return certificate.extensions.get_extension_for_class(extension_class)
    except ExtensionNotFound as error:
        raise ProducerError("Sigstore certificate extension is missing") from error


def _verify_certificate_chain(material: dict[str, Any], trust_root):
    if set(material) != {"x509CertificateChain"}:
        raise ProducerError("Sigstore verification material shape is unsupported")
    chain_container = material["x509CertificateChain"]
    if not isinstance(chain_container, dict) or set(chain_container) != {
        "certificates"
    }:
        raise ProducerError("Sigstore certificate chain shape is invalid")
    encoded_certificates = chain_container["certificates"]
    if not isinstance(encoded_certificates, list) or len(encoded_certificates) < 2:
        raise ProducerError("Sigstore certificate chain is incomplete")
    certificates = []
    for encoded in encoded_certificates:
        raw = _decode_base64(
            encoded.get("rawBytes") if isinstance(encoded, dict) else None,
            "certificate",
        )
        try:
            certificate = load_der_x509_certificate(raw)
        except ValueError as error:
            raise ProducerError("Sigstore certificate is invalid DER") from error
        if set(encoded) != {"rawBytes"}:
            raise ProducerError("Sigstore certificate entry has unsupported fields")
        certificates.append(certificate)
    if certificates[-1].public_bytes(
        serialization.Encoding.DER
    ) != trust_root.public_bytes(serialization.Encoding.DER):
        raise ProducerError("Sigstore chain does not terminate at the local trust root")
    _verify_certificate_signature(certificates[-1], certificates[-1])
    for child, issuer in zip(certificates[:-1], certificates[1:]):
        constraints = _require_extension(issuer, BasicConstraints).value
        if not constraints.ca:
            raise ProducerError("Sigstore certificate issuer is not a CA")
        _verify_certificate_signature(child, issuer)
    for certificate in certificates:
        _require_certificate_time(certificate)
    leaf = certificates[0]
    leaf_constraints = _require_extension(leaf, BasicConstraints).value
    if leaf_constraints.ca:
        raise ProducerError("Sigstore leaf certificate is a CA certificate")
    if not _require_extension(leaf, KeyUsage).value.digital_signature:
        raise ProducerError("Sigstore leaf cannot verify digital signatures")
    key_purposes = _require_extension(leaf, ExtendedKeyUsage).value
    if ExtendedKeyUsageOID.CODE_SIGNING not in key_purposes:
        raise ProducerError("Sigstore leaf is not authorized for code signing")
    return leaf


def _dsse_preauthentic_encoding(payload_type: str, payload: bytes) -> bytes:
    return (
        b"DSSEv1 "
        + str(len(payload_type)).encode("ascii")
        + b" "
        + payload_type.encode("ascii")
        + b" "
        + str(len(payload)).encode("ascii")
        + b" "
        + payload
    )


def _verify_leaf_signature(public_key, message: bytes, signature: bytes) -> None:
    try:
        if isinstance(public_key, ed25519.Ed25519PublicKey):
            public_key.verify(signature, message)
        elif isinstance(public_key, ec.EllipticCurvePublicKey):
            public_key.verify(signature, message, ec.ECDSA(hashes.SHA256()))
        elif isinstance(public_key, rsa.RSAPublicKey):
            public_key.verify(
                signature,
                message,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        else:
            raise ProducerError("Sigstore signature algorithm is unsupported")
    except InvalidSignature as error:
        raise ProducerError("Sigstore DSSE signature verification failed") from error


def _validate_sigstore_bundle(
    bundle_bytes: bytes, transaction_bytes: bytes, trust_root
) -> None:
    try:
        bundle = json.loads(bundle_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProducerError("Sigstore bundle is not valid JSON") from error
    if not isinstance(bundle, dict):
        raise ProducerError("Sigstore bundle is not an object")
    if bundle.get("mediaType") != SIGSTORE_BUNDLE_MEDIA_TYPE:
        raise ProducerError("Sigstore bundle media type is not canonical")
    material = bundle.get("verificationMaterial")
    if not isinstance(material, dict):
        raise ProducerError("Sigstore bundle verification material is missing")
    envelope = bundle.get("dsseEnvelope")
    if not isinstance(envelope, dict):
        raise ProducerError("Sigstore bundle DSSE envelope is missing")
    if envelope.get("payloadType") != IN_TOTO_PAYLOAD_TYPE:
        raise ProducerError("Sigstore bundle payload type is not in-toto")
    payload_bytes = _decode_base64(envelope.get("payload"), "payload")
    try:
        payload = json.loads(payload_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ProducerError("Sigstore bundle payload is not valid JSON") from error
    if not isinstance(payload, dict) or payload.get("_type") != (
        "https://in-toto.io/Statement/v1"
    ):
        raise ProducerError("Sigstore bundle statement type is invalid")
    expected_subjects = [
        {
            "name": "capture-transaction.json",
            "digest": {"sha256": hashlib.sha256(transaction_bytes).hexdigest()},
        }
    ]
    if payload.get("subject") != expected_subjects:
        raise ProducerError("Sigstore bundle does not bind the transaction bytes")
    signatures = envelope.get("signatures")
    if not isinstance(signatures, list) or len(signatures) != 1:
        raise ProducerError("Sigstore bundle must contain exactly one signature")
    signature = signatures[0]
    if not isinstance(signature, dict) or set(signature) not in (
        {"sig"},
        {"keyid", "sig"},
    ):
        raise ProducerError("Sigstore bundle signature entry is invalid")
    if signature.get("keyid", "") != "":
        raise ProducerError("Sigstore bundle key identity is not canonical")
    signature_bytes = _decode_base64(signature.get("sig"), "signature")
    leaf = _verify_certificate_chain(material, trust_root)
    _verify_leaf_signature(
        leaf.public_key(),
        _dsse_preauthentic_encoding(IN_TOTO_PAYLOAD_TYPE, payload_bytes),
        signature_bytes,
    )


def _verify_capture_bundle(
    context: ProducerContext, source_root: Path, output_root: Path, trust_root
) -> None:
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
    if not isinstance(runtime_identity, str):
        raise ProducerError("capture transaction runtime identity is invalid")
    expected_manifest, expected_transaction, _ = build_capture_bundle(
        context, artifact_bytes, runtime_identity
    )
    if manifest_bytes != expected_manifest:
        raise ProducerError("manifest bytes do not match the canonical projection")
    if transaction_bytes != expected_transaction:
        raise ProducerError(
            "capture transaction bytes do not match the capture contract"
        )
    _validate_sigstore_bundle(
        (output_root / "capture-transaction.sigstore.json").read_bytes(),
        transaction_bytes,
        trust_root,
    )


def _parse_arguments(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--source-root", type=Path, required=True)
    capture.add_argument("--producer-root", type=Path, required=True)
    capture.add_argument("--producer-sha", required=True)
    capture.add_argument("--output-root", type=Path, required=True)
    finalize = subparsers.add_parser("finalize")
    finalize.add_argument("--source-root", type=Path, required=True)
    finalize.add_argument("--producer-root", type=Path, required=True)
    finalize.add_argument("--producer-sha", required=True)
    finalize.add_argument("--output-root", type=Path, required=True)
    finalize.add_argument("--sigstore-bundle", type=Path, required=True)
    finalize.add_argument("--trust-root", type=Path, required=True)
    return parser.parse_args(argv)


def _capture(arguments: argparse.Namespace) -> None:
    context = _producer_context_with_git(
        dict(os.environ),
        arguments.source_root,
        arguments.producer_root,
        arguments.producer_sha,
    )
    artifact_bytes = _generate_archive(arguments.source_root, arguments.output_root)
    runtime_identity = generate_runtime_identity(generate_uuidv7)
    manifest_bytes, transaction_bytes, _ = build_capture_bundle(
        context, artifact_bytes, runtime_identity
    )
    _write_asset(arguments.output_root, "manifest.json", manifest_bytes)
    _write_asset(arguments.output_root, "capture-transaction.json", transaction_bytes)
    _validate_asset_layout(arguments.output_root, CAPTURE_ASSET_NAMES)


def _finalize(arguments: argparse.Namespace) -> None:
    context = _producer_context_with_git(
        dict(os.environ),
        arguments.source_root,
        arguments.producer_root,
        arguments.producer_sha,
    )
    _validate_asset_layout(arguments.output_root, CAPTURE_ASSET_NAMES)
    bundle_path = arguments.sigstore_bundle
    if bundle_path.is_symlink() or not bundle_path.is_file():
        raise ProducerError("local Sigstore bundle path is invalid")
    bundle_bytes = bundle_path.read_bytes()
    transaction_bytes = (
        arguments.output_root / "capture-transaction.json"
    ).read_bytes()
    trust_root = _load_certificate(arguments.trust_root)
    _validate_sigstore_bundle(bundle_bytes, transaction_bytes, trust_root)
    _write_asset(
        arguments.output_root, "capture-transaction.sigstore.json", bundle_bytes
    )
    _verify_capture_bundle(
        context, arguments.source_root, arguments.output_root, trust_root
    )
    _validate_asset_layout(arguments.output_root, ASSET_NAMES)


def run(argv: list[str] | None = None) -> None:
    arguments = _parse_arguments(sys.argv[1:] if argv is None else argv)
    if arguments.command == "capture":
        _capture(arguments)
    else:
        _finalize(arguments)


if __name__ == "__main__":
    try:
        run()
    except ProducerError as error:
        print(f"producer failed closed: {error}", file=sys.stderr)
        raise SystemExit(1)
