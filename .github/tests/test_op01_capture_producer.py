from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "op01_capture_producer.py"
SPEC = importlib.util.spec_from_file_location("op01_capture_producer", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
producer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = producer
SPEC.loader.exec_module(producer)


def _context() -> producer.ProducerContext:
    return producer.ProducerContext(
        repository=producer.REPOSITORY,
        producer_branch=producer.PRODUCER_BRANCH,
        producer_commit="a" * 40,
        source_branch=producer.SOURCE_BRANCH,
        source_commit=producer.EXPECTED_F,
        source_tree="b" * 40,
        merge_commit=producer.EXPECTED_M,
        merge_tree="c" * 40,
    )


def _clone_commit(
    repository: Path, destination: Path, branch: str, commit: str
) -> None:
    subprocess.run(
        (
            "git",
            "clone",
            "--shared",
            "--no-checkout",
            str(repository),
            str(destination),
        ),
        check=True,
        capture_output=True,
        text=True,
    )
    commands = (
        (
            "remote",
            "set-url",
            "origin",
            "https://github.com/tonychang925-dev/ai_theme_app.git",
        ),
        ("checkout", "--detach", commit),
        ("branch", "-f", branch, commit),
        ("checkout", branch),
    )
    for command in commands:
        subprocess.run(
            ("git", "-C", str(destination), *command),
            check=True,
            capture_output=True,
            text=True,
        )


def _producer_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for name in list(environment):
        if name in producer.CLOUD_EXECUTION_VARIABLES or name.startswith("GITHUB_"):
            environment.pop(name)
    return environment


def _run_producer(
    producer_root: Path,
    *arguments: str,
    cwd: Path | None = None,
    environment_updates: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    environment = _producer_environment()
    if environment_updates:
        environment.update(environment_updates)
    return subprocess.run(
        (
            sys.executable,
            str(producer_root / producer.PRODUCER_SCRIPT_PATH),
            *arguments,
        ),
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def _write_bundle(path: Path, transaction_bytes: bytes) -> None:
    payload = producer.canonical_json(
        {
            "_type": "https://in-toto.io/Statement/v1",
            "subject": [
                {
                    "name": "capture-transaction.json",
                    "digest": {"sha256": hashlib.sha256(transaction_bytes).hexdigest()},
                }
            ],
        }
    )
    bundle = producer.canonical_json(
        {
            "dsseEnvelope": {
                "payload": base64.b64encode(payload).decode("ascii"),
                "payloadType": producer.IN_TOTO_PAYLOAD_TYPE,
                "signatures": [
                    {"sig": base64.b64encode(b"local-check-binding").decode("ascii")}
                ],
            },
            "mediaType": producer.SIGSTORE_BUNDLE_MEDIA_TYPE,
            "verificationMaterial": {"localTestEnvelope": True},
        }
    )
    path.write_bytes(bundle)


def _complete_capture(
    source_root: Path,
    producer_root: Path,
    producer_sha: str,
    output_root: Path,
    *,
    relative: bool,
) -> None:
    output_root.parent.mkdir(parents=True, exist_ok=True)
    cwd = output_root.parent
    if relative:
        source = Path(os.path.relpath(source_root, cwd))
        producer_location = Path(os.path.relpath(producer_root, cwd))
        output = Path(os.path.relpath(output_root, cwd))
        bundle_path = cwd / "transaction.bundle.json"
    else:
        source = source_root
        producer_location = producer_root
        output = output_root
        bundle_path = output_root.parent / "transaction.bundle.json"

    capture = _run_producer(
        producer_root,
        "capture",
        "--source-root",
        str(source),
        "--producer-root",
        str(producer_location),
        "--producer-sha",
        producer_sha,
        "--output-root",
        str(output),
        cwd=cwd,
    )
    assert capture.returncode == 0, capture.stderr
    _write_bundle(bundle_path, (output_root / "capture-transaction.json").read_bytes())
    finalize = _run_producer(
        producer_root,
        "finalize",
        "--source-root",
        str(source),
        "--producer-root",
        str(producer_location),
        "--producer-sha",
        producer_sha,
        "--output-root",
        str(output),
        "--sigstore-bundle",
        str(bundle_path),
        cwd=cwd,
    )
    assert finalize.returncode == 0, finalize.stderr


def test_manifest_ref_uses_canonical_projection_excluding_manifest_ref() -> None:
    context = _context()
    source, build, artifact_identity, artifact_digest = producer.build_identities(
        context, b"exact-artifact"
    )
    raw = producer.build_manifest(source, build, artifact_identity, artifact_digest)
    document = json.loads(raw)
    projection = dict(document)
    projection.pop("manifest_ref")
    expected_ref = (
        "market-product-read:manifest:v1:sha256:"
        + hashlib.sha256(producer.canonical_json(projection)).hexdigest()
    )
    assert document == {
        "artifact_digest": artifact_digest,
        "artifact_identity": artifact_identity,
        "artifact_locator": "canonical:artifact.bin",
        "build_identity": build,
        "manifest_ref": expected_ref,
        "profile_id": "market-product-judgment-v1",
        "source_identity": source,
    }
    assert raw == producer.canonical_json(document)
    assert not raw.endswith(b"\n")


def test_transaction_binds_local_authority_and_four_assets() -> None:
    context = _context()
    artifact = b"exact-artifact"
    runtime = "market-product-read:runtime:v1:uuid=018f0000-0000-7000-8000-000000000001"
    manifest, transaction_bytes, returned_artifact = producer.build_capture_bundle(
        context, artifact, runtime
    )
    transaction = json.loads(transaction_bytes)
    assert returned_artifact == artifact
    assert transaction["asset_names"] == list(producer.ASSET_NAMES)
    assert transaction["producer"] == {
        "execution_boundary": "LOCAL_ONLY",
        "producer_branch": producer.PRODUCER_BRANCH,
        "producer_commit": "a" * 40,
        "repository": producer.REPOSITORY,
        "source_branch": producer.SOURCE_BRANCH,
        "source_commit": producer.EXPECTED_F,
    }
    assert transaction["manifest"]["reference"] == json.loads(manifest)["manifest_ref"]
    assert transaction["status"] == "CAPTURED_UNVERIFIED"
    assert transaction_bytes == producer.canonical_json(transaction)


def test_cloud_execution_environment_is_rejected() -> None:
    try:
        producer._require_local_execution({"GITHUB_ACTIONS": "true"})
    except producer.ProducerError as error:
        assert "local-only execution is required" in str(error)
    else:
        raise AssertionError("cloud execution environment was accepted")


def test_workflow_dispatch_path_is_retired() -> None:
    workflow = (
        SCRIPT_PATH.parents[1] / "workflows" / "rd1-v1-op01-market-release-capture.yml"
    )
    assert not workflow.exists()


def test_local_real_git_capture_paths_and_fail_closed_cases(
    tmp_path: Path,
) -> None:
    repository = SCRIPT_PATH.parents[2]
    producer_sha = subprocess.check_output(
        ("git", "-C", str(repository), "rev-parse", "HEAD"), text=True
    ).strip()
    source_root = tmp_path / "source"
    producer_root = tmp_path / "producer"
    _clone_commit(repository, source_root, producer.SOURCE_BRANCH, producer.EXPECTED_F)
    _clone_commit(repository, producer_root, producer.PRODUCER_BRANCH, producer_sha)

    for relative in (True, False):
        output_root = tmp_path / "runs" / str(relative) / "capture-output"
        _complete_capture(
            source_root,
            producer_root,
            producer_sha,
            output_root,
            relative=relative,
        )
        expected_archive = subprocess.check_output(
            (
                "git",
                "-C",
                str(source_root),
                "archive",
                "--format=tar",
                producer.EXPECTED_F,
            )
        )
        assert {entry.name for entry in output_root.iterdir()} == set(
            producer.ASSET_NAMES
        )
        assert (output_root / "artifact.bin").read_bytes() == expected_archive
        for entry in output_root.iterdir():
            assert entry.stat().st_mode & 0o777 == 0o644

    wrong_sha_root = tmp_path / "wrong-sha-output"
    wrong_sha = _run_producer(
        producer_root,
        "capture",
        "--source-root",
        str(source_root),
        "--producer-root",
        str(producer_root),
        "--producer-sha",
        "b" * 40,
        "--output-root",
        str(wrong_sha_root),
    )
    assert wrong_sha.returncode != 0
    assert "exact producer SHA" in wrong_sha.stderr
    assert not wrong_sha_root.exists()

    cloud_root = tmp_path / "cloud-output"
    cloud = _run_producer(
        producer_root,
        "capture",
        "--source-root",
        str(source_root),
        "--producer-root",
        str(producer_root),
        "--producer-sha",
        producer_sha,
        "--output-root",
        str(cloud_root),
        environment_updates={"GITHUB_ACTIONS": "true"},
    )
    assert cloud.returncode != 0
    assert "local-only execution is required" in cloud.stderr
    assert not cloud_root.exists()

    dirty_root = tmp_path / "dirty-output"
    (source_root / "uncommitted.txt").write_text("dirty\n", encoding="utf-8")
    dirty = _run_producer(
        producer_root,
        "capture",
        "--source-root",
        str(source_root),
        "--producer-root",
        str(producer_root),
        "--producer-sha",
        producer_sha,
        "--output-root",
        str(dirty_root),
    )
    assert dirty.returncode != 0
    assert "source checkout is dirty" in dirty.stderr
    assert not dirty_root.exists()


def test_output_mode_validation_fails_closed(tmp_path: Path) -> None:
    for name in producer.CAPTURE_ASSET_NAMES:
        path = tmp_path / name
        path.write_bytes(name.encode("utf-8"))
        path.chmod(0o600)
    try:
        producer._validate_asset_layout(tmp_path, producer.CAPTURE_ASSET_NAMES)
    except producer.ProducerError as error:
        assert "mode is not 0644" in str(error)
    else:
        raise AssertionError("invalid output mode was accepted")
