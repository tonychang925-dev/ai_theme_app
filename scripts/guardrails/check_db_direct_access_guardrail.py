#!/usr/bin/env python3
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

from scan_db_direct_access import ROOTS, scan_roots


def normalize(items):
    return {
        (str(i.get("file") or ""), str(i.get("rule") or ""), str(i.get("snippet") or "").strip())
        for i in items
    }


def materialize_base(base_sha: str, destination: Path) -> None:
    archive = destination / "base.tar"
    cmd = ["git", "archive", "--format=tar", "-o", str(archive), base_sha, *ROOTS]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git archive failed")
    with tarfile.open(archive, "r") as tf:
        tf.extractall(destination / "tree", filter="data")


def main() -> int:
    base_sha = os.getenv("DB_GUARDRAIL_BASE_SHA", "").strip()
    if not base_sha:
        print("missing DB_GUARDRAIL_BASE_SHA; refusing non-incremental guardrail evaluation")
        return 2

    try:
        subprocess.run(["git", "cat-file", "-e", f"{base_sha}^{{commit}}"], check=True, capture_output=True)
    except subprocess.CalledProcessError:
        print(f"base commit is unavailable: {base_sha}")
        return 2

    current = scan_roots(Path("."))
    with tempfile.TemporaryDirectory(prefix="db-guardrail-base-") as tmp:
        root = Path(tmp)
        try:
            materialize_base(base_sha, root)
        except Exception as exc:
            print(f"failed to materialize base {base_sha}: {exc}")
            return 2
        baseline = scan_roots(root / "tree")

    curr_set = normalize(current)
    base_set = normalize(baseline)
    new_items = sorted(curr_set - base_set)

    print(f"DB direct-access historical debt: base={len(base_set)} candidate={len(curr_set)} new={len(new_items)}")
    if not new_items:
        print("DB direct-access guardrail passed: no new violations versus exact base.")
        return 0

    print("DB direct-access guardrail failed: found newly introduced violations.")
    for file, rule, snippet in new_items:
        print(f"- {file} [{rule}] {snippet}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
