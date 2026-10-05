#!/usr/bin/env python3
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

ROOT = "stock_processing_service"
FORBIDDEN = re.compile(r"\._client\b|\._db\b|\bexecute_query\b|\basyncpg\b")
SQL = re.compile(r"\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b")


def _tracked_files(base: Path, prefix: str):
    # Guard only repository truth; local caches/untracked artifacts are not candidate source.
    proc = subprocess.run(
        ["git", "-C", str(base), "ls-files", "--", prefix],
        capture_output=True, text=True,
    )
    if proc.returncode == 0:
        return [base / line.strip() for line in proc.stdout.splitlines() if line.strip()]
    root = base / prefix
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def _read_lines(path: Path):
    try:
        return path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []


def scan(base_dir: Path | str = Path(".")):
    base = Path(base_dir).resolve()
    root = base / ROOT
    findings = []

    for layer in ("application", "domain"):
        p = root / layer
        if not p.exists():
            continue
        for file in _tracked_files(base, f"{ROOT}/{layer}"):
            if not file.is_file():
                continue
            rel = file.relative_to(base).as_posix()
            if file.suffix == ".md" or "/tests/" in ("/" + rel):
                continue
            for line_no, line in enumerate(_read_lines(file), 1):
                if FORBIDDEN.search(line):
                    findings.append({
                        "label": f"{layer} layer contains forbidden gateway/sql symbols",
                        "file": rel,
                        "line": line_no,
                        "snippet": line.strip(),
                    })

    if root.exists():
        for file in _tracked_files(base, ROOT):
            if not file.is_file():
                continue
            rel = file.relative_to(base).as_posix()
            path_key = "/" + rel
            if file.suffix == ".md" or "/tests/" in path_key or "/scripts/" in path_key:
                continue
            if file.name.startswith("db_") and file.name.endswith("_gateway.py"):
                continue
            for line_no, line in enumerate(_read_lines(file), 1):
                if SQL.search(line):
                    findings.append({
                        "label": "stock_processing_service contains SQL literals",
                        "file": rel,
                        "line": line_no,
                        "snippet": line.strip(),
                    })

    findings.sort(key=lambda x: (x["label"], x["file"], x["line"], x["snippet"]))
    return findings


def normalize(items):
    return {(x["label"], x["file"], x["snippet"]) for x in items}


def materialize_base(base_sha: str, destination: Path) -> None:
    archive = destination / "base.tar"
    proc = subprocess.run(
        ["git", "archive", "--format=tar", "-o", str(archive), base_sha, ROOT],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git archive failed")
    with tarfile.open(archive, "r") as tf:
        tf.extractall(destination / "tree", filter="data")


def main() -> int:
    base_sha = os.getenv("STOCK_GUARDRAIL_BASE_SHA", "").strip()
    if not base_sha:
        print("missing STOCK_GUARDRAIL_BASE_SHA; refusing non-incremental guardrail evaluation")
        return 2
    try:
        subprocess.run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print(f"base commit is unavailable: {base_sha}")
        return 2

    current = scan(Path("."))
    with tempfile.TemporaryDirectory(prefix="stock-guardrail-base-") as tmp:
        root = Path(tmp)
        try:
            materialize_base(base_sha, root)
        except Exception as exc:
            print(f"failed to materialize base {base_sha}: {exc}")
            return 2
        baseline = scan(root / "tree")

    current_set = normalize(current)
    base_set = normalize(baseline)
    new_items = sorted(current_set - base_set)
    print(f"stock-processing historical debt: base={len(base_set)} candidate={len(current_set)} new={len(new_items)}")
    if not new_items:
        print("[PASS] stock_processing_service guardrails: no new violations versus exact base")
        return 0

    print("[FAIL] stock_processing_service newly introduced guardrail violations")
    for label, file, snippet in new_items:
        print(f"- {file} [{label}] {snippet}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
