from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_contracts import (
    UNIVERSE_REQUIRED_CYCLE_FIELDS,
    UNIVERSE_REQUIRED_IDENTITY_FIELDS,
)

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
    transition_type: str = ""
    transition_confidence: Decimal = Decimal("0")
    trigger_flags: list[str] | None = None
    fade_watch: bool = False
    fade_confirmed: bool = False


@dataclass(frozen=True)
class UniverseBuildResult:
    formal_rows: list[SubjectStockPoolDTO]
    observe_rows: list[SubjectStockPoolDTO]
    blocked_rows: list[SubjectStockPoolDTO]
    diagnostics: dict[str, dict[str, Any]]
    formal_count: int = 0
    observe_count: int = 0
    blocked_count: int = 0


class StrongWatchUniverseBuilder:
    """
    Layer C-1 Universe gate.

    - formal: identity confirmed + main theme + mainline alive
    - observe: independent leader gene only
    - blocked: missing subject key or missing identity/cycle context

    Old-chain compatibility:
    ordinary non-formal subject rows are diagnostics only. They must not enter
    the production strong-watch pool as observe rows, because old-chain D1 only
    consumes an already-converged strong_stock_watch_pool/history source.
    """

    def __init__(
        self,
        *,
        allow_observe_when_not_formal: bool = False,
    ) -> None:
        self._allow_observe_when_not_formal = allow_observe_when_not_formal

    @staticmethod
    def _normalize_identity(raw: SubjectIdentity | dict[str, Any] | None, subject_key: str) -> SubjectIdentity | None:
        if raw is None:
            return None
        if isinstance(raw, SubjectIdentity):
            return raw
        if isinstance(raw, dict):
            if any(k not in raw for k in UNIVERSE_REQUIRED_IDENTITY_FIELDS):
                return None
            return SubjectIdentity(
                subject_key=subject_key,
                identity_status=str(raw.get("identity_status") or "").lower(),
                is_main_theme=bool(raw.get("is_main_theme") or False),
                rule_version=str(raw.get("rule_version") or ""),
            )
        if hasattr(raw, "identity_status"):
            return SubjectIdentity(
                subject_key=subject_key,
                identity_status=str(getattr(raw, "identity_status", "") or "").lower(),
                is_main_theme=bool(getattr(raw, "is_main_theme", False)),
                rule_version=str(getattr(raw, "rule_version", "") or ""),
            )
        return None

    @staticmethod
    def _normalize_cycle(raw: CycleStatus | dict[str, Any] | None, subject_key: str) -> CycleStatus | None:
        if raw is None:
            return None
        if isinstance(raw, CycleStatus):
            return raw
        if isinstance(raw, dict):
            if any(k not in raw for k in UNIVERSE_REQUIRED_CYCLE_FIELDS):
                return None
            return CycleStatus(
                subject_key=subject_key,
                final_cycle_state=str(raw.get("final_cycle_state") or ""),
                final_mainline_alive=bool(raw.get("final_mainline_alive") or False),
                transition_type=str(raw.get("transition_type") or ""),
                transition_confidence=Decimal(str(raw.get("transition_confidence") or raw.get("confidence") or "0")),
                trigger_flags=list(raw.get("trigger_flags") or []),
                fade_watch=bool(raw.get("fade_watch") or False),
                fade_confirmed=bool(raw.get("fade_confirmed") or False),
            )
        if hasattr(raw, "final_cycle_state") or hasattr(raw, "final_mainline_alive"):
            return CycleStatus(
                subject_key=subject_key,
                final_cycle_state=str(getattr(raw, "final_cycle_state", "") or ""),
                final_mainline_alive=bool(getattr(raw, "final_mainline_alive", False)),
                transition_type=str(getattr(raw, "transition_type", "") or ""),
                transition_confidence=Decimal(str(getattr(raw, "transition_confidence", getattr(raw, "confidence", "0")) or "0")),
                trigger_flags=list(getattr(raw, "trigger_flags", []) or []),
                fade_watch=bool(getattr(raw, "fade_watch", False)),
                fade_confirmed=bool(getattr(raw, "fade_confirmed", False)),
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

            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            prior7_limitup_days = int(metadata.get("prior7_limitup_days") or 0)
            recent_limit_up_count = int(metadata.get("recent_limit_up_count") or 0)
            max_consecutive_limit_up_days = int(metadata.get("max_consecutive_limit_up_days") or 0)
            two_board_entry = bool(metadata.get("two_board_entry") or False) or (
                max_consecutive_limit_up_days >= 2
                or recent_limit_up_count >= 2
                or prior7_limitup_days >= 2
            )
            strong_gene_seed = bool(metadata.get("strong_gene_seed") or False) or two_board_entry
            independent_gene_diag = {
                "two_board_entry": two_board_entry,
                "strong_gene_seed": strong_gene_seed,
                "strong_gene_seed_reason": str(metadata.get("strong_gene_seed_reason") or ""),
                "prior7_limitup_days": prior7_limitup_days,
                "recent_limit_up_count": recent_limit_up_count,
                "max_consecutive_limit_up_days": max_consecutive_limit_up_days,
                "identity_scope": str(metadata.get("identity_scope") or ""),
            }

            identity = self._normalize_identity(identities_by_subject.get(subject_key), subject_key)
            cycle = self._normalize_cycle(cycles_by_subject.get(subject_key), subject_key)
            cycle_source = "db"

            # ── 覆盖策略: 区分 "B层覆盖缺口" vs "真正非主线" ──
            # 原则:
            #   1. 独立强势基因只授予个股观察资格，不确认 Layer A/B。
            #   2. 非独立强势基因对象仍按 identity/cycle 缺失严格 blocked。
            #   3. identity+cycle 的主线 formal 路径保持 confirmed+alive。
            if identity is None and cycle is None:
                if strong_gene_seed:
                    observe_rows.append(row)
                    diagnostics[stock_id] = {
                        "universe_status": "observe",
                        "universe_reason": "independent_leader_without_layer_ab",
                        "entry_path": "independent_leader",
                        "identity_present": False,
                        "cycle_present": False,
                        **independent_gene_diag,
                    }
                    continue
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "missing_identity_and_cycle",
                }
                continue

            if identity is None:
                if strong_gene_seed:
                    observe_rows.append(row)
                    diagnostics[stock_id] = {
                        "universe_status": "observe",
                        "universe_reason": "independent_leader_without_identity",
                        "entry_path": "independent_leader",
                        "identity_present": False,
                        "cycle_present": True,
                        "final_cycle_state": cycle.final_cycle_state if cycle else "n/a",
                        "final_mainline_alive": cycle.final_mainline_alive if cycle else False,
                        **independent_gene_diag,
                    }
                    continue
                # cycle 存在但 identity 缺失 (罕见: 可能是旧数据残留)
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "contract_missing_identity_fields",
                    "cycle_present": True,
                    "final_cycle_state": cycle.final_cycle_state if cycle else "n/a",
                }
                continue

            # identity 存在, 处理 cycle 缺失的情况
            # Inferred cycle removed — strict document path: no cycle → blocked.
            if cycle is None:
                identity_confirmed_prelim = (
                    identity.identity_status == "confirmed" and identity.is_main_theme
                )
                if strong_gene_seed:
                    observe_rows.append(row)
                    diagnostics[stock_id] = {
                        "universe_status": "observe",
                        "universe_reason": "independent_leader_without_cycle",
                        "entry_path": "independent_leader",
                        "identity_present": True,
                        "cycle_present": False,
                        "identity_status": identity.identity_status,
                        "is_main_theme": identity.is_main_theme,
                        "identity_confirmed_pass": identity_confirmed_prelim,
                        **independent_gene_diag,
                    }
                    continue
                if identity_confirmed_prelim:
                    blocked_rows.append(row)
                    diagnostics[stock_id] = {
                        "universe_status": "blocked",
                        "universe_reason": "identity_confirmed_but_cycle_missing",
                        "identity_present": True,
                        "cycle_present": False,
                        "identity_status": identity.identity_status,
                        "is_main_theme": identity.is_main_theme,
                    }
                    continue
                else:
                    blocked_rows.append(row)
                    diagnostics[stock_id] = {
                        "universe_status": "blocked",
                        "universe_reason": "identity_not_mainline_and_cycle_missing",
                        "identity_present": True,
                        "cycle_present": False,
                        "identity_status": identity.identity_status,
                        "is_main_theme": identity.is_main_theme,
                    }
                    continue

            # ── 正常主线判定 (与原有逻辑一致) ──
            identity_confirmed = identity.identity_status == "confirmed" and identity.is_main_theme
            cycle_alive = cycle.final_mainline_alive

            diag = {
                "identity_status": identity.identity_status,
                "is_main_theme": identity.is_main_theme,
                "identity_confirmed_pass": identity_confirmed,
                "final_cycle_state": cycle.final_cycle_state,
                "final_mainline_alive": cycle.final_mainline_alive,
                "transition_type": cycle.transition_type,
                "transition_confidence": str(cycle.transition_confidence),
                "trigger_flags": list(cycle.trigger_flags or []),
                "cycle_alive_pass": cycle_alive,
                "cycle_source": cycle_source,
                **independent_gene_diag,
            }

            if identity_confirmed and cycle_alive:
                formal_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "formal",
                    "universe_reason": "identity_confirmed_and_cycle_alive",
                    "entry_path": "mainline_strong",
                    **diag,
                }
                continue

            if strong_gene_seed:
                observe_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "observe",
                    "universe_reason": "independent_leader_entry",
                    "entry_path": "independent_leader",
                    **diag,
                }
                continue

            if self._allow_observe_when_not_formal:
                observe_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "observe",
                    "universe_reason": "identity_or_cycle_not_formal",
                    "entry_path": "mainline_observe",
                    **diag,
                }
            else:
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "diagnostic_only",
                    "universe_reason": "identity_or_cycle_not_formal_not_watch_pool_eligible",
                    "entry_path": "observe_diagnostic",
                    **diag,
                }

        return UniverseBuildResult(
            formal_rows=formal_rows,
            observe_rows=observe_rows,
            blocked_rows=blocked_rows,
            diagnostics=diagnostics,
            formal_count=len(formal_rows),
            observe_count=len(observe_rows),
            blocked_count=len(blocked_rows),
        )
