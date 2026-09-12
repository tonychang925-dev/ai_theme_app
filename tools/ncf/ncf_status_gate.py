#!/usr/bin/env python3
"""Deterministic, exact-SHA-bound critical-fallback gate for pull requests."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_POLICIES = (
    "NCF-01-critical-fallback",
    "NCF-02-test-double-production-reachability",
    "NCF-03-legacy-authority-fallback",
    "NCF-04-alternate-provider-masking",
    "NCF-05-synthetic-success",
    "NCF-06-exception-success",
    "NCF-07-ambient-authority-selection",
    "NCF-08-production-test-mode",
    "NCF-09-fail-closed",
)
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".sh"}
NCF_OWNED_PREFIXES = (
    "tools/ncf/",
    "tests/governance/",
)
CRITICAL_PATH = re.compile(
    r"identity|persona|conversation|memory|context|market|database|provider|"
    r"runtime|composition|launcher|auth|provenance|fallback",
    re.I,
)
TEST_DOUBLE = re.compile(r"\b(mock|fake|stub|fixture)s?\b", re.I)
FALLBACK = re.compile(r"\b(fallback|legacy|alternate|synthetic|placeholder)\b", re.I)
SUCCESS_VALUE = re.compile(
    r"\b(return|exit)\s+(0|true|success|ok|none|null)\b|"
    r"\breturn\s+(\{\}|\[\]|\"\"|'')\s*$",
    re.I,
)
PRODUCTION_TEST_MODE = re.compile(
    r"\b(test[_-]?mode|debug[_-]?mode|allow[_-]?mocks?)\b.*=\s*(true|1|yes)",
    re.I,
)
AMBIENT_SELECTION = re.compile(
    r"(getenv|environ|walk|glob|resolve).*(legacy|private|fallback).*(path|dir|home)",
    re.I,
)
PINNED_ACTION = re.compile(r"uses:\s*[^\s@]+@([0-9a-f]{40})(\s|$)")


@dataclass(frozen=True)
class Finding:
    policy: str
    file: str
    line: int
    reason: str


class GateError(RuntimeError):
    pass


def run_git(root: Path, args: Iterable[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def require_git(root: Path, args: Iterable[str], purpose: str) -> str:
    result = run_git(root, args)
    if result.returncode != 0:
        raise GateError(f"git failed while {purpose}: {result.stderr.strip()}")
    return result.stdout.strip()


def is_production_source(path: str) -> bool:
    return Path(path).suffix.lower() in SOURCE_SUFFIXES and not any(
        path.startswith(prefix) for prefix in NCF_OWNED_PREFIXES
    )


def exception_success(text: str) -> bool:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not re.match(r"\s*except\b", line):
            continue
        indent = len(line) - len(line.lstrip())
        for candidate in lines[index + 1:]:
            candidate_indent = len(candidate) - len(candidate.lstrip())
            if candidate.strip() and candidate_indent <= indent:
                break
            if SUCCESS_VALUE.search(candidate):
                return True
    return False


def scan_source(path: str, text: str) -> list[Finding]:
    findings: list[Finding] = []
    critical = CRITICAL_PATH.search(path)
    for number, line in enumerate(text.splitlines(), 1):
        if critical and FALLBACK.search(line):
            findings.append(Finding("NCF-01-critical-fallback", path, number, line.strip()))
        if TEST_DOUBLE.search(line):
            findings.append(
                Finding("NCF-02-test-double-production-reachability", path, number, line.strip())
            )
        if critical and re.search(r"legacy.*(authority|provider)|fallback.*(authority|provider)", line, re.I):
            findings.append(Finding("NCF-03-legacy-authority-fallback", path, number, line.strip()))
        if critical and re.search(r"alternate.*(provider|source).*except|except.*alternate.*(provider|source)", line, re.I):
            findings.append(Finding("NCF-04-alternate-provider-masking", path, number, line.strip()))
        if re.search(r"(synthetic|placeholder).*success|success.*(synthetic|placeholder)", line, re.I):
            findings.append(Finding("NCF-05-synthetic-success", path, number, line.strip()))
        if AMBIENT_SELECTION.search(line):
            findings.append(Finding("NCF-07-ambient-authority-selection", path, number, line.strip()))
        if PRODUCTION_TEST_MODE.search(line):
            findings.append(Finding("NCF-08-production-test-mode", path, number, line.strip()))
    if critical and exception_success(text):
        findings.append(Finding("NCF-06-exception-success", path, 1, "exception handler returns success-like value"))
    return findings


def validate_workflow(root: Path) -> list[Finding]:
    path = ".github/workflows/no-critical-fallback-gate.yml"
    workflow_path = root / path
    if not workflow_path.is_file():
        raise GateError(f"missing required gate workflow: {path}")
    text = workflow_path.read_text(encoding="utf-8")
    findings: list[Finding] = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.search(r"\buses:\s*(\S+)", line)
        if match and not re.fullmatch(r"[^@]+@[0-9a-f]{40}", match.group(1)):
            findings.append(Finding("NCF-09-fail-closed", path, number, "workflow action is not exact-SHA pinned"))
        if re.search(r"\b(statuses|checks|attestations|id-token|deployments|packages):\s*write", line, re.I):
            findings.append(Finding("NCF-09-fail-closed", path, number, "workflow requests status-manufacturing write permission"))
    if "ref: ${{ github.event.pull_request.head.sha }}" not in text:
        findings.append(Finding("NCF-09-fail-closed", path, 1, "workflow does not check out exact PR head SHA"))
    return findings


def load_baseline(path: Path, repository: str, required_context: str) -> dict[str, object]:
    if not path.is_file():
        raise GateError(f"missing baseline: {path}")
    try:
        baseline = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise GateError(f"invalid baseline: {error}") from error
    expected_keys = {"schema_version", "repository", "required_context", "policies"}
    if set(baseline) != expected_keys:
        raise GateError("baseline shape is unsupported")
    if baseline["schema_version"] != 2:
        raise GateError("unsupported baseline schema version")
    if baseline["repository"] != repository:
        raise GateError("baseline repository mismatch")
    if baseline["required_context"] != required_context:
        raise GateError("baseline required context mismatch")
    if tuple(baseline["policies"]) != REQUIRED_POLICIES:
        raise GateError("baseline policy set mismatch")
    return baseline


def evaluate(args: argparse.Namespace) -> tuple[bool, dict[str, object]]:
    root = args.root.resolve()
    if args.event_name != "pull_request":
        raise GateError("unsupported GitHub event; exact pull_request evaluation required")
    if args.repository != "tonychang925-dev/ai_theme_app":
        raise GateError("repository mismatch")
    if not re.fullmatch(r"[0-9a-f]{40}", args.head_sha):
        raise GateError("candidate SHA is not a valid exact SHA")
    if not re.fullmatch(r"[0-9a-f]{40}", args.github_sha):
        raise GateError("workflow run SHA is not a valid exact SHA")

    baseline_path = args.baseline if args.baseline.is_absolute() else root / args.baseline
    baseline = load_baseline(baseline_path, args.repository, args.required_context)
    require_git(root, ["rev-parse", "--verify", f"{args.head_sha}^{{commit}}"], "validating candidate SHA")
    require_git(root, ["merge-base", "--is-ancestor", args.base_sha, args.head_sha], "validating base ancestry")
    checked_out_sha = require_git(root, ["rev-parse", "HEAD"], "reading checked-out SHA")
    if checked_out_sha != args.head_sha:
        raise GateError("working tree HEAD differs from exact candidate SHA")

    changed_output = require_git(
        root,
        ["diff", "--name-only", "--diff-filter=ACMRT", args.base_sha, args.head_sha],
        "enumerating exact candidate changes",
    )
    changed_files = tuple(line for line in changed_output.splitlines() if line)
    findings: list[Finding] = []
    for relative_path in changed_files:
        if not is_production_source(relative_path):
            continue
        candidate_path = root / relative_path
        if not candidate_path.is_file():
            raise GateError(f"changed production source is missing at candidate SHA: {relative_path}")
        try:
            text = candidate_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise GateError(f"cannot read changed source {relative_path}: {error}") from error
        findings.extend(scan_source(relative_path, text))
    findings.extend(validate_workflow(root))

    result = {
        "context": baseline["required_context"],
        "repository": args.repository,
        "event": args.event_name,
        "base_sha": args.base_sha,
        "candidate_sha": args.head_sha,
        "github_sha": args.github_sha,
        "changed_files": changed_files,
        "policy_count": len(REQUIRED_POLICIES),
        "finding_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }
    return not findings, result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--baseline", type=Path, default=Path("tools/ncf/ncf-baseline.json"))
    parser.add_argument("--repository", required=True)
    parser.add_argument("--required-context", default="NO_CRITICAL_FALLBACK_GATE")
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--github-sha", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        passed, result = evaluate(args)
    except (GateError, OSError, subprocess.SubprocessError) as error:
        passed = False
        result = {
            "context": args.required_context,
            "repository": args.repository,
            "candidate_sha": args.head_sha,
            "finding_count": 1,
            "findings": [{"policy": "NCF-09-fail-closed", "file": "", "line": 0, "reason": str(error)}],
        }
    print(json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
