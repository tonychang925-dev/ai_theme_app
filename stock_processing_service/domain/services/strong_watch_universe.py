from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import SubjectStockPoolDTO
from stock_processing_service.domain.services.strong_watch_contracts import (
    UNIVERSE_REQUIRED_CYCLE_FIELDS,
    UNIVERSE_REQUIRED_IDENTITY_FIELDS,
)

# —— 覆盖策略常量 ——

# 当 identity 已确认为主线但 cycle 数据缺失时，使用的推断 cycle 状态
# 保守策略: final_mainline_alive=False, 归入 observe (不自动升级为 formal)
# 当 Layer B 覆盖提升后，真实 cycle 数据将自然替代推断值
_INFERRED_CYCLE_STATE = "unknown"
_INFERRED_MAINLINE_ALIVE = False


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

    # ── 覆盖策略: cycle 推断 (Phase 0) ──

    @staticmethod
    def _infer_cycle_for_confirmed_identity(subject_key: str) -> CycleStatus:
        """
        当 identity 已确认为主线但 cycle 数据缺失时，使用保守推断值。
        推断的 cycle 保证 subject 不会被 blocked，但也不会自动升级为 formal
        (final_mainline_alive=False)，确保只有真实 B 层数据才能触发 formal 主线路径。
        当 Layer B 覆盖提升后，真实 cycle 数据会自然替代推断值。
        """
        return CycleStatus(
            subject_key=subject_key,
            final_cycle_state=_INFERRED_CYCLE_STATE,
            final_mainline_alive=_INFERRED_MAINLINE_ALIVE,
            transition_type="",
            transition_confidence=Decimal("0"),
            trigger_flags=[],
            fade_watch=False,
            fade_confirmed=False,
        )

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
            cycle_source = "db"

            # ── 覆盖策略: 区分 "B层覆盖缺口" vs "真正非主线" ──
            # 原则:
            #   1. identity + cycle 都缺失 → blocked (确认非主线)
            #   2. identity 缺失(但 cycle 存在) → blocked (罕见边界, 保守处理)
            #   3. identity 存在 + cycle 缺失 + identity 已确认主线 → observe (B层覆盖缺口, 保守降级)
            #   4. identity 存在 + cycle 缺失 + identity 非主线 → blocked (正确排除)
            if identity is None and cycle is None:
                blocked_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "blocked",
                    "universe_reason": "missing_identity_and_cycle",
                }
                continue

            if identity is None:
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
            if cycle is None:
                identity_confirmed_prelim = (
                    identity.identity_status == "confirmed" and identity.is_main_theme
                )
                if identity_confirmed_prelim and os.environ.get("LAYER_C_ALLOW_INFERRED_CYCLE", "0") == "1":
                    # B层覆盖缺口: identity 已确认为主线, 但 cycle 数据尚未生成
                    # 使用保守推断 cycle (alive=False), 归入 observe
                    # Gate: LAYER_C_ALLOW_INFERRED_CYCLE (Phase 1: default 0, strict document path)
                    cycle = self._infer_cycle_for_confirmed_identity(subject_key)
                    cycle_source = "inferred"
                elif identity_confirmed_prelim:
                    # Gate closed: missing cycle → blocked (strict document path)
                    blocked_rows.append(row)
                    diagnostics[stock_id] = {
                        "universe_status": "blocked",
                        "universe_reason": "identity_confirmed_but_cycle_missing_inferred_disabled",
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
            metadata = row.metadata if isinstance(row.metadata, dict) else {}
            prior7_limitup_days = int(metadata.get("prior7_limitup_days") or 0)
            recent_limit_up_count = int(metadata.get("recent_limit_up_count") or 0)
            max_consecutive_limit_up_days = int(metadata.get("max_consecutive_limit_up_days") or 0)
            # 旧链旁路：两连板（或近7日强势连板信号）允许入围，避免漏掉非主线但强势龙头。
            two_board_entry = (
                max_consecutive_limit_up_days >= 2
                or recent_limit_up_count >= 2
                or prior7_limitup_days >= 2
            )

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
                "two_board_entry": two_board_entry,
                "prior7_limitup_days": prior7_limitup_days,
                "recent_limit_up_count": recent_limit_up_count,
                "max_consecutive_limit_up_days": max_consecutive_limit_up_days,
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

            # Gate: LAYER_C_ALLOW_TWO_BOARD_BYPASS (Phase 1: default 1, Phase 2: default 0)
            if two_board_entry and os.environ.get("LAYER_C_ALLOW_TWO_BOARD_BYPASS", "1") == "1":
                formal_rows.append(row)
                diagnostics[stock_id] = {
                    "universe_status": "formal",
                    "universe_reason": "two_board_entry",
                    "entry_path": "two_board",
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
            formal_count=len(formal_rows),
            observe_count=len(observe_rows),
            blocked_count=len(blocked_rows),
        )
