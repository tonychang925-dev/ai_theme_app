from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stock_processing_service.contracts.dto import SubjectStockPoolDTO


@dataclass(frozen=True)
class SubjectIdentity:
    subject_key: str
    identity_status: str
    is_main_theme: bool
    rule_version: str = ""


@dataclass(frozen=True)
class CycleStatus:
    subject_key: str
    final_cycle_state: str
    final_mainline_alive: bool
    fade_watch: bool = False
    fade_confirmed: bool = False


@dataclass(frozen=True)
class UniverseBuildResult:
    formal_rows: list[SubjectStockPoolDTO]
    observe_rows: list[SubjectStockPoolDTO]
    blocked_rows: list[SubjectStockPoolDTO]
    diagnostics: dict[str, dict[str, Any]]


class StrongWatchUniverseBuilder:
    """
    Layer C-1 Universe gate.

    - formal: identity confirmed + main theme + mainline alive
    - observe: identity/cycle known but not formal eligible
    - blocked: missing subject key or missing identity/cycle context
    """

    def __init__(
        self,
        *,
        allow_observe_when_not_formal: bool = True,
    ) -> None:
        self._allow_observe_when_not_formal = allow_observe_when_not_formal

    @staticmethod
    def _normalize_identity(raw: SubjectIdentity | dict[str, Any] | None, subject_key: str) -> SubjectIdentity | None:
        if raw is None:
            return None
        if isinstance(raw, SubjectIdentity):
            return raw
        if isinstance(raw, dict):
            return SubjectIdentity(
                subject_key=subject_key,
                identity_status=str(raw.get("identity_status") or "").lower(),
                is_main_theme=bool(raw.get("is_main_theme") or False),
                rule_version=str(raw.get("rule_version") or ""),
            )
        return None

    @staticmethod
    def _normalize_cycle(raw: CycleStatus | dict[str, Any] | None, subject_key: str) -> CycleStatus | None:
        if raw is None:
            return None
        if isinstance(raw, CycleStatus):
            return raw
        if isinstance(raw, dict):
            return CycleStatus(
                subject_key=subject_key,
                final_cycle_state=str(raw.get("final_cycle_state") or ""),
                final_mainline_alive=bool(raw.get("final_mainline_alive") or False),
                fade_watch=bool(raw.get("fade_watch") or False),
                fade_confirmed=bool(raw.get("fade_confirmed") or False),
            )
        return None

    def build_universe(
        self,
        *,
        pool_rows: list[SubjectStockPoolDTO],
        identities_by_subject: dict[str, SubjectIdentity | dict[str, Any]],
        cycles_by_subject: dict[str, CycleStatus | dict[str, Any]],
    ) -> UniverseBuildResult:
        formal_rows: list[SubjectStockPoolDTO] = []
        observe_rows: list[SubjectStockPoolDTO] = []
        blocked_rows: list[SubjectStockPoolDTO] = []
        diagnostics: dict[str, dict[str, Any]] = {}

        for row in pool_rows:
            subject_key = str(row.subject_key or "")
            stock_id = str(row.stock_id or "")
            if not subject_key:
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "missing_subject_key",
                }
                continue

            identity = self._normalize_identity(identities_by_subject.get(subject_key), subject_key)
            cycle = self._normalize_cycle(cycles_by_subject.get(subject_key), subject_key)

            if identity is None or cycle is None:
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "missing_identity_or_cycle",
                    "identity_present": identity is not None,
                    "cycle_present": cycle is not None,
                }
                continue

            identity_confirmed = identity.identity_status == "confirmed" and identity.is_main_theme
            cycle_alive = cycle.final_mainline_alive

            diag = {
                "identity_status": identity.identity_status,
                "is_main_theme": identity.is_main_theme,
                "identity_confirmed_pass": identity_confirmed,
                "final_cycle_state": cycle.final_cycle_state,
                "final_mainline_alive": cycle.final_mainline_alive,
                "cycle_alive_pass": cycle_alive,
            }

            if identity_confirmed and cycle_alive:
                formal_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "formal",
                    "universe_reason": "identity_confirmed_and_cycle_alive",
                    **diag,
                }
                continue

            if self._allow_observe_when_not_formal:
                observe_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "observe",
                    "universe_reason": "identity_or_cycle_not_formal",
                    **diag,
                }
            else:
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "identity_or_cycle_not_formal",
                    **diag,
                }

        return UniverseBuildResult(
            formal_rows=formal_rows,
            observe_rows=observe_rows,
            blocked_rows=blocked_rows,
            diagnostics=diagnostics,
        )

