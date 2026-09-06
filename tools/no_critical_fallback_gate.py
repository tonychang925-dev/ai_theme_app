#!/usr/bin/env python3
"""NCF-1 static gate: reject new critical fallback behavior."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import tokenize
import warnings
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


RULES = {
    "NCF-01": ("production import test/mock/fake/stub", "P1"),
    "NCF-02": ("ImportError creates local fake/stub", "P1"),
    "NCF-03": ("critical config defaults to memory/mock/test", "P1"),
    "NCF-04": ("exception handler returns success-like default", "P2"),
    "NCF-05": ("synthetic identity/persona/system prompt", "P1"),
    "NCF-06": ("fallback or alternate provider autobind", "P1"),
    "NCF-07": ("getter auto-constructs authority", "P1"),
    "NCF-08": ("legacy storage/history fallback", "P1"),
    "NCF-09": ("typed result converted to legacy carrier", "P2"),
    "NCF-10": ("missing canonical asset becomes normal no-op", "P1"),
    "NCF-11": ("missing provenance is guessed", "P1"),
    "NCF-12": ("outer SUCCESS with inner unavailable/error", "P1"),
    "NCF-13": ("production test-mode reachability", "P1"),
    "NCF-14": ("provider failure becomes assistant text", "P1"),
    "NCF-15": ("ambient critical import resolution", "P1"),
    "NCF-16": ("canonical conversation missing uses legacy history", "P1"),
}

CRITICAL_TERMS = re.compile(
    r"identity|persona|conversation|memory|context|market|database|provider|"
    r"d1|websearch|webfetch|c1|c2|evidence|strategy|runtime|composition|"
    r"launcher|auth|provenance",
    re.I,
)
SOURCE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx", ".sh"}
EXCLUDED_PARTS = {
    ".git", "node_modules", "dist", "build", "__pycache__", ".venv", "venv",
    "docs", ".github", ".codex", "hooks",
}
AI_THEME_PRODUCTION_ROOTS = {
    "database_service", "stock_processing_service", "theme_service",
    "web_app_service", "executables", "deploy",
}


@dataclass(frozen=True)
class Violation:
    rule: str
    repo: str
    file: str
    line: int
    symbol: str
    severity: str
    reason: str
    fingerprint: str


def is_test_path(path: str) -> bool:
    lowered = path.lower().replace("\\", "/")
    return (
        "/tests/" in f"/{lowered}"
        or "/test/" in f"/{lowered}"
        or "/fixtures/" in lowered
        or "/__tests__/" in lowered
        or ".test." in lowered
        or ".spec." in lowered
        or "/test_" in f"/{lowered}"
        or lowered.endswith("_test.py")
    )


def is_critical_path(path: str) -> bool:
    return bool(CRITICAL_TERMS.search(path))


def make_fingerprint(rule: str, file: str, reason: str) -> str:
    normalized = " ".join(reason.split()).casefold()
    return hashlib.sha256(f"{rule}|{file}|{normalized}".encode()).hexdigest()


def add(violations: list[Violation], rule: str, repo: str, path: str,
        line: int, symbol: str, reason: str, force_severity: str | None = None) -> None:
    severity = force_severity or RULES[rule][1]
    if rule == "NCF-04" and ("True" in reason or "true" in reason or "success" in reason.lower()):
        severity = "P1"
    violations.append(Violation(
        rule=rule,
        repo=repo,
        file=path,
        line=line,
        symbol=symbol,
        severity=severity,
        reason=reason,
        fingerprint=make_fingerprint(rule, path, reason),
    ))


def _source_line(lines: list[str], index: int) -> str:
    return lines[index].strip() if 0 <= index < len(lines) else ""


def _docstring_ranges(tree: ast.AST) -> set[int]:
    ranges: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        body = node.body
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            ranges.update(range(value.lineno, value.end_lineno + 1))
    return ranges


def _code_lines(text: str, tree: ast.AST) -> list[str]:
    lines = text.splitlines()
    ignored = _docstring_ranges(tree)
    try:
        tokens = list(tokenize.generate_tokens(iter(text.splitlines()).__next__))
        for token in tokens:
            if token.type == tokenize.COMMENT:
                ignored.update(range(token.start[0], token.end[0] + 1))
    except (tokenize.TokenError, IndentationError):
        pass
    return ["" if index in ignored else line for index, line in enumerate(lines, start=1)]


def scan_python(text: str, repo: str, path: str) -> list[Violation]:
    violations: list[Violation] = []
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(text)
    except SyntaxError:
        return violations
    lines = _code_lines(text, tree)

    for child in ast.walk(tree):
        if isinstance(child, ast.ImportFrom):
            module = child.module or ""
            if re.search(r"(^|[.])(tests?|mocks?|fakes?|stubs?|fixtures?)($|[.])", module, re.I):
                add(violations, "NCF-01", repo, path, child.lineno, "<module>",
                    f"production source imports test implementation {module}")
        if isinstance(child, ast.ExceptHandler) and child.body:
            exception_name = (
                child.type.id if isinstance(child.type, ast.Name) else ast.unparse(child.type)
            ) if child.type is not None else "Exception"
            for statement in ast.walk(child):
                if isinstance(statement, ast.Call) and isinstance(statement.func, ast.Name):
                    if re.search(r"mock|fake|stub|fixture", statement.func.id, re.I):
                        add(violations, "NCF-02", repo, path, statement.lineno, exception_name,
                            f"exception handler constructs {statement.func.id}")

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not re.match(r"get_", node.name, re.I):
            continue
        if not re.search(r"authority|provider|identity", node.name, re.I):
            continue
        constructors = [
            child for child in ast.walk(node)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name | ast.Attribute)
            and re.search(r"provider|authority|identity", ast.unparse(child.func), re.I)
        ]
        has_cache_miss = any(
            isinstance(child, ast.Compare)
            and any(isinstance(operator, ast.Is) for operator in child.ops)
            and "None" in [ast.unparse(comparator) for comparator in child.comparators]
            for child in ast.walk(node)
        )
        has_typed_rejection = any(isinstance(child, ast.Raise) for child in ast.walk(node))
        if constructors and (has_cache_miss or len(constructors) > 1) and not has_typed_rejection:
            add(violations, "NCF-07", repo, path, node.lineno, node.name,
                "authority getter auto-constructs or dynamically substitutes an implementation")

    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.ExceptHandler) or not child.body:
                continue
            exception_name = (
                child.type.id if isinstance(child.type, ast.Name) else ast.unparse(child.type)
            ) if child.type is not None else "Exception"
            for returned in ast.walk(child):
                if not isinstance(returned, ast.Return):
                    continue
                value = returned.value
                literal = (
                    isinstance(value, ast.Constant)
                    or isinstance(value, ast.List | ast.Dict | ast.Tuple)
                    and not getattr(value, "elts", None)
                    and not getattr(value, "values", None)
                )
                if literal and is_critical_path(path):
                    rendered = ast.unparse(value) if value is not None else "None"
                    add(violations, "NCF-04", repo, path, returned.lineno, node.name,
                        f"{exception_name} handler returns default {rendered}",
                        force_severity=(
                            "P1"
                            if exception_name in {"Exception", "BaseException"}
                            and (rendered == "True" or "success" in rendered.lower())
                            else None
                        ),
                )

    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if line.startswith("#") or line.startswith('"') or line.startswith("'"):
            continue
        if re.search(
            r"(getenv|environ\.get)\([^\n]*(memory|mock|fake|fixture|(?<![a-z])test(?![a-z]))",
            line,
            re.I,
        ):
            add(violations, "NCF-03", repo, path, index, "config-default", line)
        if re.search(r"(identity|persona|system_prompt).*(mock|fake|synthetic|fallback)", line, re.I):
            add(violations, "NCF-05", repo, path, index, "synthetic-identity", line)
        if re.search(r"(fallback_provider|alternate_provider|provider.*fallback|fallback.*provider)", line, re.I):
            add(violations, "NCF-06", repo, path, index, "provider-binding", line)
        if re.search(r"(legacy.*(history|storage)|fallback.*(history|storage))", line, re.I):
            add(violations, "NCF-08", repo, path, index, "legacy-storage", line)
        if re.search(r"legacy_from_execution|to_legacy_carrier", line, re.I):
            add(violations, "NCF-09", repo, path, index, "legacy-carrier", line)
        if re.search(r"(asset|persona|identity).*(missing|unavailable).*(return\s+(none|{})|pass)", line, re.I):
            add(violations, "NCF-10", repo, path, index, "asset-noop", line)
        if re.search(r"provenance.*(=\s*\{\}|get\([^\n]*,\s*['\"](?:unknown|guessed|synthetic)['\"]|=\s*['\"](?:unknown|guessed|synthetic)['\"])", line, re.I):
            add(violations, "NCF-11", repo, path, index, "provenance", line)
        if re.search(r"(outer.*success.*inner.*(error|unavailable)|inner.*(error|unavailable).*outer.*success)", line, re.I):
            add(violations, "NCF-12", repo, path, index, "outer-success", line)
        if re.search(
            r"(TEST_MODE\s*=\s*(?:1|true|['\"](?:1|true|test)['\"])|"
            r"test_mode\s*=\s*(?:True|1)|ENV[A-Z_]*(?:==|equals).*(?:test|fixture))",
            line,
            re.I,
        ):
            add(violations, "NCF-13", repo, path, index, "test-mode", line)
        if re.search(r"(provider.*(fail|error|exception).*(assistant|stream)|except.*provider.*stream_async)", line, re.I):
            add(violations, "NCF-14", repo, path, index, "provider-failure", line)
        if re.search(r"sys\.path\.insert.*(?:test|fixture|tmp|private)", line, re.I):
            add(violations, "NCF-15", repo, path, index, "ambient-import", line)
        if re.search(r"(conversation.*(missing|unavailable).*legacy|canonical.*missing.*history)", line, re.I):
            add(violations, "NCF-16", repo, path, index, "legacy-history", line)
    return violations


def scan_js(text: str, repo: str, path: str) -> list[Violation]:
    violations: list[Violation] = []
    for index, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("//") or line.startswith("*"):
            continue
        if re.search(r"(?:from|import)\s+['\"].*(?:test|mock|fake|stub|fixture)", line, re.I):
            add(violations, "NCF-01", repo, path, index, "import", line)
        if re.search(r"(DB_TYPE|databaseType).*(memory|mock|test|fixture)", line, re.I):
            add(violations, "NCF-03", repo, path, index, "config-default", line)
        if re.search(r"catch\s*(?:\([^)]*\))?\s*\{\s*return\s*(?:\[\]|\{\}|null|false|true|['\"])", line, re.I):
            add(violations, "NCF-04", repo, path, index, "catch-default", line)
        if re.search(r"(fallbackProvider|alternateProvider|provider.*fallback)", line, re.I):
            add(violations, "NCF-06", repo, path, index, "provider-binding", line)
        if re.search(r"(legacyHistory|legacyStorage)", line, re.I):
            add(violations, "NCF-08", repo, path, index, "legacy-storage", line)
        if re.search(r"TEST_MODE\s*===?\s*['\"](?:1|true|test)", line, re.I):
            add(violations, "NCF-13", repo, path, index, "test-mode", line)
        if re.search(r"providerError.*(?:assistantText|stream)", line, re.I):
            add(violations, "NCF-14", repo, path, index, "provider-failure", line)
    return violations


def scan_text(text: str, repo: str, path: str) -> list[Violation]:
    if path.endswith(".py"):
        return scan_python(text, repo, path)
    return scan_js(text, repo, path)


def candidate_files(root: Path, repo: str, files: Iterable[str] | None = None) -> list[Path]:
    if files is not None:
        candidates = [
            Path(item).resolve() for item in files
            if Path(item).exists() and Path(item).suffix in SOURCE_SUFFIXES
        ]
        return candidates
    return sorted(
        path for path in root.rglob("*")
        if path.is_file()
        and path.suffix in SOURCE_SUFFIXES
        and not any(part in EXCLUDED_PARTS for part in path.parts)
        and not any("test_harness" in part.lower() or "probe" in part.lower() for part in path.parts)
        and not is_test_path(path.as_posix())
    )


def scan(root: Path, repo: str, files: Iterable[str] | None = None) -> list[Violation]:
    violations: list[Violation] = []
    for path in candidate_files(root, repo, files):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            rel = path.name
        if is_test_path(rel) or path.name == Path(__file__).name:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        violations.extend(scan_text(text, repo, rel))
    return violations


def evaluate(violations: list[Violation], baseline: dict) -> dict:
    allowed: dict[tuple[str, str], list[dict]] = {}
    for item in baseline.get("entries", []):
        allowed.setdefault((item["rule"], item["file"]), []).append(item)
    existing: list[Violation] = []
    new: list[Violation] = []
    unresolved = {key: list(items) for key, items in allowed.items()}
    for item in violations:
        key = (item.rule, item.file)
        matches = [entry for entry in unresolved.get(key, []) if entry["fingerprint"] == item.fingerprint]
        if matches:
            unresolved[key].remove(matches[0])
            existing.append(item)
            if not unresolved[key]:
                del unresolved[key]
            continue
        if key in allowed:
            new.append(item)
        else:
            new.append(item)
    resolved = [item for key in sorted(unresolved) for item in unresolved[key]]
    return {
        "existing_debt": [asdict(item) for item in existing],
        "new_violations": [asdict(item) for item in new],
        "resolved_debt": resolved,
    }


def report(result: dict) -> tuple[dict, int]:
    new = result["new_violations"]
    p0 = [item for item in new if item["severity"] == "P0"]
    p1 = [item for item in new if item["severity"] == "P1"]
    p2 = [item for item in new if item["severity"] == "P2"]
    fail = bool(p0 or p1 or result.get("baseline_expanded")) or (
        result.get("fail_p2", False) and bool(p2)
    )
    summary = {
        "NCF_GATE": "FAIL" if fail else "PASS",
        "P0_NEW": len(p0),
        "P1_NEW": len(p1),
        "P2_NEW": len(p2),
        "BASELINE_EXPANDED": "YES" if result.get("baseline_expanded") else "NO",
        "EXISTING_DEBT": len(result["existing_debt"]),
        "RESOLVED_DEBT": len(result["resolved_debt"]),
        "PRODUCTION_MOCK_REACHABLE": "YES" if has_rules(new, {"NCF-01", "NCF-02", "NCF-13"}) else "NO",
        "PRODUCTION_FIXTURE_REACHABLE": "YES" if has_rules(new, {"NCF-01", "NCF-13"}) else "NO",
        "SYNTHETIC_SUCCESS_REACHABLE": "YES" if has_rules(new, {"NCF-05", "NCF-12", "NCF-14"}) else "NO",
        "FAIL_OPEN_AUTHORITY": "YES" if has_rules(new, {"NCF-03", "NCF-06", "NCF-07", "NCF-11", "NCF-15"}) else "NO",
        "FAIL_OPEN_VERIFICATION": "YES" if has_rules(new, {"NCF-12", "NCF-14"}) else "NO",
        "SABOTAGE_TESTS": "FAIL" if fail else "PASS",
    }
    return summary, 1 if fail else 0


def has_rules(findings: list[dict], rules: set[str]) -> bool:
    return any(item["rule"] in rules for item in findings)


def validate_baseline(baseline: dict) -> str | None:
    entries = baseline.get("entries")
    if baseline.get("schema_version") != 1 or not isinstance(entries, list):
        return "schema must be version 1 with an entries array"
    if entries and baseline.get("authorization") != "EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT":
        return "baseline entries require EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT"
    required = {"rule", "file", "line", "symbol", "severity", "reason", "fingerprint"}
    for index, item in enumerate(entries):
        if not isinstance(item, dict) or not required.issubset(item):
            return f"baseline entry {index} is incomplete"
        if item["rule"] not in RULES or item["severity"] not in {"P0", "P1", "P2", "P3"}:
            return f"baseline entry {index} has invalid rule or severity"
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="unknown")
    parser.add_argument("--baseline", type=Path, default=Path("ncf-baseline.json"))
    parser.add_argument("--files", nargs="*", default=None)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--fail-p2", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--authorization")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    violations = scan(root, args.repo, args.files)
    baseline = {"schema_version": 1, "authorization": "", "entries": []}
    if args.baseline.is_file():
        try:
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"NCF baseline invalid: {exc}", file=sys.stderr)
            return 2
    baseline_error = validate_baseline(baseline)
    if baseline_error:
        print(f"NCF baseline invalid: {baseline_error}", file=sys.stderr)
        return 2

    baseline_already_existed = bool(baseline.get("entries"))
    prior_result = evaluate(violations, baseline)
    expansion = baseline_already_existed and bool(prior_result["new_violations"])

    if args.update_baseline:
        required_authorization = "EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT"
        if args.authorization != required_authorization:
            print(
                "NCF baseline update refused: provide --authorization EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT",
                file=sys.stderr,
            )
            return 2

    if args.update_baseline:
        baseline = {
            "schema_version": 1,
            "authorization": "EXPLICIT_TONY_GO_NCF_A5_LOCAL_CODEX_CI_GITHUB_ENFORCEMENT",
            "entries": sorted(
                [asdict(item) for item in violations],
                key=lambda item: (item["file"], item["rule"], item["line"]),
            ),
        }
        args.baseline.write_text(json.dumps(baseline, indent=2) + "\n", encoding="utf-8")

    result = evaluate(violations, baseline)
    result["baseline_expanded"] = args.update_baseline and expansion
    result["fail_p2"] = args.fail_p2
    summary, status = report(result)
    payload = {"summary": summary, "findings": result}
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print("NO_CRITICAL_FALLBACK_GATE")
        for key, value in summary.items():
            print(f"{key}: {value}")
        for item in result["new_violations"]:
            print(f"{item['severity']} {item['rule']} {item['file']}:{item['line']} {item['symbol']} — {item['reason']}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
