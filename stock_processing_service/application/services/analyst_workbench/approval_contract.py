"""Approval identity, persisted review state, and runtime integrity contracts."""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import json
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


class ApprovalAuthorizationError(PermissionError):
    """Raised when an approval principal is unauthenticated or unauthorized."""


class ReviewStateError(ValueError):
    """Raised when persisted analyst review state is missing or invalid."""


class RuntimeIntegrityError(ValueError):
    """Raised when the Approved Snapshot runtime dependency closure drifts."""


@dataclass(frozen=True, slots=True)
class ApprovalPrincipal:
    user_id: str
    email: str
    role: str

    @property
    def identity(self) -> str:
        return f"user:{self.user_id}:{self.email}"


def require_approval_principal(authorization: str | None) -> ApprovalPrincipal:
    if not authorization or not authorization.startswith("Bearer "):
        raise ApprovalAuthorizationError("authenticated analyst session required")
    token = authorization[len("Bearer ") :].strip()
    if not token:
        raise ApprovalAuthorizationError("authenticated analyst session required")

    from web_app_service.auth import verify_token

    payload = verify_token(token)
    if not isinstance(payload, dict):
        raise ApprovalAuthorizationError("invalid or expired analyst session")
    user_id = str(payload.get("sub", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    role = str(payload.get("role", "")).strip().lower()
    if not user_id or not email:
        raise ApprovalAuthorizationError(
            "authenticated principal identity is incomplete"
        )
    if role not in {"analyst", "admin"}:
        raise ApprovalAuthorizationError(
            "principal is not authorized to approve snapshots"
        )
    return ApprovalPrincipal(user_id=user_id, email=email, role=role)


class ReviewStateStore:
    """Persist the exact analyst workspace that participates in approval."""

    STATE_FIELDS = ("themes", "watch_groups", "overrides")

    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)

    def _state_path(self, trade_date: date) -> Path:
        return self.base_dir / trade_date.isoformat() / "review_state.json"

    @classmethod
    def workspace_hash(cls, workspace: dict[str, Any]) -> str:
        material = {field: workspace.get(field) for field in cls.STATE_FIELDS}
        raw = json.dumps(
            material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def save(
        self,
        *,
        trade_date: date,
        workspace: dict[str, Any],
        principal: ApprovalPrincipal,
    ) -> dict[str, Any]:
        if not isinstance(workspace, dict):
            raise ReviewStateError("workspace review state must be an object")
        state = {
            "schema_version": 1,
            "trade_date": trade_date.isoformat(),
            **{field: workspace.get(field) for field in self.STATE_FIELDS},
            "state_hash": self.workspace_hash(workspace),
            "reviewed_by": principal.identity,
            "reviewed_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self._state_path(trade_date)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)
        return state

    def load(self, trade_date: date) -> dict[str, Any] | None:
        path = self._state_path(trade_date)
        if not path.exists():
            return None
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReviewStateError(
                "persisted analyst review state is unreadable"
            ) from exc
        if not isinstance(state, dict):
            raise ReviewStateError("persisted analyst review state is invalid")
        if state.get("schema_version") != 1:
            raise ReviewStateError("unsupported analyst review state schema")
        if state.get("trade_date") != trade_date.isoformat():
            raise ReviewStateError("analyst review state trade date mismatch")
        workspace = {field: state.get(field) for field in self.STATE_FIELDS}
        if state.get("state_hash") != self.workspace_hash(workspace):
            raise ReviewStateError("analyst review state hash mismatch")
        if not state.get("reviewed_by"):
            raise ReviewStateError("analyst review state has no authenticated reviewer")
        return state


class RuntimeIntegrityVerifier:
    """Verify the source and dependency manifest for Approved Snapshot execution."""

    MANIFEST_RELPATH = Path(
        "stock_processing_service/application/services/analyst_workbench/"
        "approved_snapshot_runtime_manifest.json"
    )

    @classmethod
    def manifest_hash(cls, manifest: dict[str, Any]) -> str:
        raw = json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def verify(
        cls, repo_root: str | Path, manifest_path: str | Path | None = None
    ) -> str:
        root = Path(repo_root).resolve()
        path = Path(manifest_path) if manifest_path else root / cls.MANIFEST_RELPATH
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeIntegrityError(
                "Approved Snapshot runtime manifest is unreadable"
            ) from exc
        if manifest.get("schema_version") != 1:
            raise RuntimeIntegrityError(
                "unsupported Approved Snapshot runtime manifest"
            )
        files = manifest.get("files")
        if not isinstance(files, list):
            raise RuntimeIntegrityError(
                "Approved Snapshot runtime manifest has no file closure"
            )
        for entry in files:
            relpath = entry.get("path") if isinstance(entry, dict) else None
            if (
                not isinstance(relpath, str)
                or not relpath
                or Path(relpath).is_absolute()
            ):
                raise RuntimeIntegrityError(
                    "Approved Snapshot manifest path is invalid"
                )
            candidate = (root / relpath).resolve()
            if root not in candidate.parents:
                raise RuntimeIntegrityError(
                    "Approved Snapshot manifest escapes repository"
                )
            if not candidate.is_file():
                raise RuntimeIntegrityError(
                    f"Approved Snapshot runtime file missing: {relpath}"
                )
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
            if digest != entry.get("sha256"):
                raise RuntimeIntegrityError(
                    f"Approved Snapshot runtime file changed: {relpath}"
                )
        packages = manifest.get("packages", [])
        if not isinstance(packages, list):
            raise RuntimeIntegrityError("Approved Snapshot package manifest is invalid")
        for entry in packages:
            package = entry.get("package") if isinstance(entry, dict) else None
            expected = entry.get("version") if isinstance(entry, dict) else None
            if not package or not expected:
                raise RuntimeIntegrityError(
                    "Approved Snapshot package entry is invalid"
                )
            try:
                actual = importlib.metadata.version(package)
            except importlib.metadata.PackageNotFoundError as exc:
                raise RuntimeIntegrityError(
                    f"Approved Snapshot package missing: {package}"
                ) from exc
            if actual != expected:
                raise RuntimeIntegrityError(
                    f"Approved Snapshot package changed: {package} {actual} != {expected}"
                )
        return cls.manifest_hash(manifest)


def project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _module_path(root: Path, module: str) -> Path | None:
    candidate = root.joinpath(*module.split("."))
    path = candidate.with_suffix(".py")
    if path.is_file():
        return path
    package = candidate / "__init__.py"
    return package if package.is_file() else None


def build_runtime_manifest(repo_root: str | Path) -> dict[str, Any]:
    """Build the declared Approved Snapshot material-runtime closure."""
    root = Path(repo_root).resolve()
    entrypoint = "stock_processing_service/api_app.py"
    recursive_roots = [
        "stock_processing_service.application.services.analyst_workbench.approval_contract",
        "stock_processing_service.application.services.analyst_workbench.approval_gate",
        "stock_processing_service.application.services.analyst_workbench.draft",
        "stock_processing_service.application.services.analyst_workbench.report_composer",
        "stock_processing_service.application.services.analyst_workbench.review_merger",
        "stock_processing_service.application.services.analyst_workbench.session",
        "stock_processing_service.application.services.analyst_workbench.snapshot",
        "stock_processing_service.application.services.analyst_workbench.snapshot_validator",
        "stock_processing_service.application.services.post_market_engine_report_composer",
    ]
    project_prefixes = ("stock_processing_service", "web_app_service")
    files: set[str] = {entrypoint}
    packages: set[str] = set()
    pending = list(recursive_roots)
    visited: set[str] = set()

    while pending:
        module = pending.pop(0)
        if module in visited:
            continue
        visited.add(module)
        path = _module_path(root, module)
        if path is None:
            raise RuntimeIntegrityError(
                f"Approved Snapshot runtime module missing: {module}"
            )
        files.add(path.relative_to(root).as_posix())
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError) as exc:
            raise RuntimeIntegrityError(
                f"cannot inspect Approved Snapshot module: {module}"
            ) from exc
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module] if node.module else []
                if node.level:
                    parent_parts = module.split(".")
                    for _ in range(node.level):
                        parent_parts.pop()
                    base = ".".join(parent_parts)
                    names = [f"{base}.{node.module}" if node.module else base]
            else:
                continue
            for name in names:
                if not name:
                    continue
                top = name.split(".")[0]
                if any(
                    name == prefix or name.startswith(prefix + ".")
                    for prefix in project_prefixes
                ):
                    pending.append(name)
                elif top not in sys.stdlib_module_names and top != "__future__":
                    packages.add({"jwt": "PyJWT"}.get(top, top))

    file_entries = [
        {
            "path": relpath,
            "sha256": hashlib.sha256((root / relpath).read_bytes()).hexdigest(),
        }
        for relpath in sorted(files)
    ]
    package_entries = [
        {"package": package, "version": importlib.metadata.version(package)}
        for package in sorted(packages)
    ]
    return {
        "schema_version": 1,
        "scope": "approved_snapshot_public_projection",
        "entrypoint": entrypoint,
        "recursive_roots": recursive_roots,
        "files": file_entries,
        "packages": package_entries,
    }


__all__ = [
    "ApprovalAuthorizationError",
    "ApprovalPrincipal",
    "ReviewStateError",
    "ReviewStateStore",
    "RuntimeIntegrityError",
    "RuntimeIntegrityVerifier",
    "build_runtime_manifest",
    "project_root",
    "require_approval_principal",
]
