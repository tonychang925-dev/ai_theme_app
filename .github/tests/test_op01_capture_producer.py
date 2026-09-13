from __future__ import annotations

import hashlib
import importlib.util
import json
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
        actor=producer.EXPECTED_ACTOR,
        triggering_actor=producer.EXPECTED_ACTOR,
        event_name="workflow_dispatch",
        runner_image_os="ubuntu24",
        workflow_path=producer.WORKFLOW_PATH,
        workflow_sha="a" * 40,
        workflow_ref=producer.EXPECTED_WORKFLOW_REF,
        run_id="1234567890",
        run_attempt="1",
        source_commit=producer.EXPECTED_F,
        source_tree="b" * 40,
        merge_commit=producer.EXPECTED_M,
        merge_tree="c" * 40,
    )


def _environment() -> dict[str, str]:
    return {
        "GITHUB_REPOSITORY": producer.REPOSITORY,
        "GITHUB_ACTOR": producer.EXPECTED_ACTOR,
        "GITHUB_TRIGGERING_ACTOR": producer.EXPECTED_ACTOR,
        "GITHUB_EVENT_NAME": "workflow_dispatch",
        "ImageOS": "ubuntu24",
        "GITHUB_WORKFLOW_REF": producer.EXPECTED_WORKFLOW_REF,
        "GITHUB_WORKFLOW_SHA": "a" * 40,
        "GITHUB_RUN_ID": "1",
        "GITHUB_RUN_ATTEMPT": "1",
        "GITHUB_SHA": "a" * 40,
        "GITHUB_WORKSPACE": "/tmp/workspace",
    }


def _checkout_commits(repository: Path, destination: Path, *commits: str) -> None:
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
    subprocess.run(
        ("git", "-C", str(destination), "checkout", "--detach", commits[-1]),
        check=True,
        capture_output=True,
        text=True,
    )


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


def test_transaction_binds_four_purposes_and_manifest_projection() -> None:
    context = _context()
    artifact = b"exact-artifact"
    runtime = "market-product-read:runtime:v1:uuid=018f0000-0000-7000-8000-000000000001"
    manifest, transaction_bytes, returned_artifact = producer.build_capture_bundle(
        context, artifact, runtime
    )
    transaction = json.loads(transaction_bytes)
    purposes = [record["purpose"] for record in transaction["evidence"]]
    bases = {record["purpose"]: record["basis"] for record in transaction["evidence"]}
    subjects = {
        record["purpose"]: record["subject_digest"]
        for record in transaction["evidence"]
    }
    assert returned_artifact == artifact
    assert purposes == [
        "ARTIFACT_DIGEST",
        "ARTIFACT_IDENTITY",
        "MANIFEST",
        "SOURCE_BUILD_LINEAGE",
    ]
    assert bases == {
        "ARTIFACT_DIGEST": "EXPLICIT_CAPTURED_ARTIFACT",
        "ARTIFACT_IDENTITY": "EXPLICIT_CAPTURED_ARTIFACT",
        "MANIFEST": "EXPLICIT_CAPTURED_ARTIFACT",
        "SOURCE_BUILD_LINEAGE": "CLEAN_REPOSITORY_SNAPSHOT",
    }
    assert subjects["MANIFEST"] == producer.sha256_digest(manifest)
    assert transaction["manifest"]["reference"] == json.loads(manifest)["manifest_ref"]
    assert transaction["producer"]["runner"] == "ubuntu-24.04"
    assert transaction["status"] == "CAPTURED_UNVERIFIED"
    assert transaction_bytes == producer.canonical_json(transaction)


def test_environment_authority_fails_closed() -> None:
    environment = _environment()
    environment["GITHUB_REPOSITORY"] = "example/untrusted"
    try:
        producer._require_environment(environment)
    except producer.ProducerError as error:
        assert "repository" in str(error)
    else:
        raise AssertionError("untrusted repository was accepted")


def test_validate_clean_accepts_non_lfs_repository(tmp_path: Path) -> None:
    root = tmp_path / "repository"
    root.mkdir()
    commands = (
        ("init",),
        ("config", "user.name", "Test User"),
        ("config", "user.email", "test@example.invalid"),
    )
    for command in commands:
        subprocess.run(
            ("git", "-C", str(root), *command),
            check=True,
            capture_output=True,
            text=True,
        )
    (root / "tracked.txt").write_text("clean\n", encoding="utf-8")
    subprocess.run(
        ("git", "-C", str(root), "add", "tracked.txt"),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ("git", "-C", str(root), "commit", "-m", "initial"),
        check=True,
        capture_output=True,
        text=True,
    )

    producer._validate_clean(root, "source")


def test_run_creates_intended_relative_output_root_for_exact_archive(
    tmp_path: Path, monkeypatch
) -> None:
    repository = SCRIPT_PATH.parents[2]
    workflow_sha = subprocess.check_output(
        ("git", "-C", str(repository), "rev-parse", "HEAD"), text=True
    ).strip()
    source_root = tmp_path / "source"
    workflow_root = tmp_path / "workflow"
    run_root = tmp_path / "run"
    output_root = run_root / "capture-output"
    _checkout_commits(repository, source_root, producer.EXPECTED_M, producer.EXPECTED_F)
    _checkout_commits(repository, workflow_root, workflow_sha)
    run_root.mkdir()
    monkeypatch.chdir(run_root)
    environment = _environment()
    environment["GITHUB_WORKFLOW_SHA"] = workflow_sha
    environment["GITHUB_SHA"] = workflow_sha
    for name, value in environment.items():
        monkeypatch.setenv(name, value)

    producer.run(
        (
            "--integration-commit",
            producer.EXPECTED_F,
            "--source-root",
            str(source_root),
            "--workflow-root",
            str(workflow_root),
            "--output-root",
            str(output_root.relative_to(tmp_path / "run")),
        )
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
    assert output_root.is_dir()
    assert (output_root / "artifact.bin").read_bytes() == expected_archive


def test_environment_accepts_real_canonical_workflow_authority() -> None:
    context = producer._require_environment(_environment())

    assert context.workflow_ref == producer.EXPECTED_WORKFLOW_REF
    assert context.workflow_sha == "a" * 40


def test_environment_rejects_noncanonical_workflow_ref() -> None:
    environment = _environment()
    environment["GITHUB_WORKFLOW_REF"] = (
        "refs/heads/rd1-v1/op01/capture-producer@" + "a" * 40
    )

    try:
        producer._require_environment(environment)
    except producer.ProducerError as error:
        assert "frozen producer branch" in str(error)
    else:
        raise AssertionError("synthetic workflow ref was accepted")


def test_environment_rejects_workflow_sha_mismatch() -> None:
    environment = _environment()
    environment["GITHUB_WORKFLOW_SHA"] = "b" * 40

    try:
        producer._require_environment(environment)
    except producer.ProducerError as error:
        assert "workflow SHA" in str(error)
    else:
        raise AssertionError("workflow SHA mismatch was accepted")


def test_environment_requires_workflow_sha() -> None:
    environment = _environment()
    del environment["GITHUB_WORKFLOW_SHA"]

    try:
        producer._require_environment(environment)
    except producer.ProducerError as error:
        assert "required GitHub Actions identity is missing" in str(error)
    else:
        raise AssertionError("missing workflow SHA was accepted")


def test_workflow_uses_real_authority_without_synthetic_override() -> None:
    workflow = (
        SCRIPT_PATH.parents[1]
        / "workflows"
        / ("rd1-v1-op01-market-release-capture.yml")
    )
    text = workflow.read_text(encoding="utf-8")
    assert f"      EXPECTED_WORKFLOW_REF: {producer.EXPECTED_WORKFLOW_REF}\n" in text
    assert (
        '          test "${GITHUB_WORKFLOW_REF}" = "${EXPECTED_WORKFLOW_REF}"\n' in text
    )
    assert '          test "${GITHUB_WORKFLOW_SHA}" = "${GITHUB_SHA}"\n' in text
    assert "GITHUB_WORKFLOW_REF#refs/heads/" not in text
    build_step = text[text.index("      - name: Build canonical capture inputs\n") :]
    assert "GITHUB_WORKFLOW_REF:" not in build_step


def test_workflow_permission_contract_is_exact() -> None:
    workflow = (
        SCRIPT_PATH.parents[1]
        / "workflows"
        / ("rd1-v1-op01-market-release-capture.yml")
    )
    text = workflow.read_text(encoding="utf-8")
    permissions = text.split("permissions:\n", 1)[1].split("\n\njobs:", 1)[0]
    assert permissions == (
        "  attestations: write\n" "  id-token: write\n" "  contents: write"
    )
