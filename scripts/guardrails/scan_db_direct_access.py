#!/usr/bin/env python3
import json
import re
from pathlib import Path

ROOTS = ["frontend", "frontend_bff", "web_app_service"]
EXCLUDE_SUFFIX = (".png", ".jpg", ".jpeg", ".gif", ".svg", ".map", ".lock")
EXCLUDE_DIR_NAMES = {"node_modules", "dist", ".git", "__pycache__", ".venv", "venv", "logs", "reports"}
EXCLUDE_FILE_PATTERNS = ("*.log", "*.min.js")
SCAN_CODE_SUFFIX = {".py", ".ts", ".tsx", ".js", ".jsx", ".sql"}
EXCLUDE_PATH_CONTAINS = ("/tests/", "/test/")
PATTERNS = {
    "db_client": re.compile(r"\b(asyncpg|psycopg|sqlalchemy|create_engine|aiomysql|pymysql|redis\.Redis|redis\.from_url)\b"),
    "raw_sql": re.compile(
        r"(?i)\bselect\b.+\bfrom\b|\binsert\s+into\b|\bupdate\s+\w+\s+set\b|\bdelete\s+from\b"
    ),
}
RAW_SQL_FILE_SUFFIX = {".py", ".sql", ".sql.j2"}


def scan_file(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return []
    findings = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for rule, pattern in PATTERNS.items():
            if rule == "raw_sql" and path.suffix.lower() not in RAW_SQL_FILE_SUFFIX:
                continue
            if pattern.search(line):
                # Security regex signatures are not DB access.
                if "security_middleware.py" in str(path) and "select\\s+\\*\\s+from" in line:
                    continue
                findings.append({"file": str(path), "line": line_no, "rule": rule, "snippet": line.strip()[:200]})
    return findings


def main() -> int:
    findings = []
    for root in ROOTS:
        p = Path(root)
        if not p.exists():
            continue
        for file in p.rglob("*"):
            if file.is_dir():
                continue
            if any(part in EXCLUDE_DIR_NAMES for part in file.parts):
                continue
            file_str = str(file).replace("\\", "/")
            if any(token in file_str for token in EXCLUDE_PATH_CONTAINS):
                continue
            if file.suffix.lower() in EXCLUDE_SUFFIX:
                continue
            if file.suffix.lower() not in SCAN_CODE_SUFFIX:
                continue
            if any(file.match(pattern) for pattern in EXCLUDE_FILE_PATTERNS):
                continue
            findings.extend(scan_file(file))

    findings.sort(key=lambda x: (x["file"], x["line"], x["rule"]))
    print(json.dumps(findings, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
