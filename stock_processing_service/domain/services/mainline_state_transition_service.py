"""MainlineStateTransitionService — Layer B 主线状态迁移（主题级）。

等价旧链 stock_service/services/mainline_state_transition_service.py (540行)。
负责：
1. 读取当日 cycle_judgement + identity 确认状态
2. 读取前一日 mainline_state_daily
3. 计算 from_state → to_state → transition_type
4. 生成 trigger_flags + confidence
5. 写入 mainline_state_daily + mainline_state_transition
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from stock_processing_service.contracts.dto import (
    MainlineCycleDTO,
    MainlineIdentityDTO,
)


@dataclass(frozen=True)
class MainlineStateDailyDTO:
    trade_date: date
    subject_key: str
    theme_name: str
    state: str              # final_cycle_state
    state_score: Decimal
    is_mainline: bool       # identity_confirmed AND final_mainline_alive
    mainline_strength_score: Decimal
    fade_watch_score: Decimal
    fade_confirmed_score: Decimal
    divergence_score: Decimal
    repair_score: Decimal
    evidence_json: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MainlineStateTransitionDTO:
    trade_date: date
    subject_key: str
    theme_name: str
    from_state: str | None
    to_state: str
    transition_type: str   # upgrade / downgrade / fade / flat
    from_score: Decimal
    to_score: Decimal
    confidence: Decimal
    trigger_flags: list[str] = field(default_factory=list)
    evidence_json: dict[str, Any] = field(default_factory=dict)


class MainlineStateTransitionService:
    """主线状态迁移服务（主题级）。

    设计文档 §13.3.2：迁移服务只负责 from_state → to_state → transition_type，
    不得反向定义主状态。

    final_mainline_alive = NOT fade_confirmed（§25.3）。
    """

    _STATE_RANK = {
        "fade_confirmed": 0,
        "fade_watch": 1,
        "start": 2,
        "fermentation": 3,
        "divergence": 4,
        "repair": 5,
        "acceleration": 6,
    }

    def build_daily_snapshots(
        self,
        trade_date: date,
        cycles: list[MainlineCycleDTO],
        identities: dict[str, MainlineIdentityDTO],
        prior_snapshots: dict[str, MainlineStateDailyDTO] | None = None,
    ) -> list[MainlineStateDailyDTO]:
        """构建当日 MainlineStateDaily 快照。

        is_mainline = identity_confirmed AND final_mainline_alive
        """
        snapshots: list[MainlineStateDailyDTO] = []
        for cyc in cycles:
            identity = identities.get(cyc.subject_key)
            identity_confirmed = (
                identity is not None
                and identity.is_main_theme
                and identity.identity_status == "confirmed"
            )
            final_mainline_alive = cyc.final_mainline_alive
            is_mainline = identity_confirmed and final_mainline_alive

            state = cyc.final_cycle_state
            if state == "acceleration":
                state_score = cyc.mainline_strength_score
            elif state == "repair":
                state_score = cyc.repair_score
            elif state == "divergence":
                state_score = cyc.divergence_score
            elif state == "fade_watch":
                state_score = cyc.fade_watch_score
            elif state == "fade_confirmed":
                state_score = cyc.fade_confirmed_score
            else:
                state_score = cyc.mainline_strength_score

            evidence: dict[str, Any] = {
                "identity_confirmed": identity_confirmed,
                "final_mainline_alive": final_mainline_alive,
                "is_mainline": is_mainline,
            }
            if identity:
                evidence["identity_composite_score"] = float(identity.composite_score)

            snapshots.append(
                MainlineStateDailyDTO(
                    trade_date=trade_date,
                    subject_key=cyc.subject_key,
                    theme_name=cyc.theme_name,
                    state=state,
                    state_score=state_score,
                    is_mainline=is_mainline,
                    mainline_strength_score=cyc.mainline_strength_score,
                    fade_watch_score=cyc.fade_watch_score,
                    fade_confirmed_score=cyc.fade_confirmed_score,
                    divergence_score=cyc.divergence_score,
                    repair_score=cyc.repair_score,
                    evidence_json=evidence,
                )
            )

        return snapshots

    def build_transitions(
        self,
        trade_date: date,
        daily_snapshots: list[MainlineStateDailyDTO],
        prior_snapshots: dict[str, MainlineStateDailyDTO] | None = None,
    ) -> list[MainlineStateTransitionDTO]:
        """构建 from_state → to_state 迁移记录（仅主线存活 subjects）。"""
        prior = prior_snapshots or {}
        transitions: list[MainlineStateTransitionDTO] = []

        for snap in daily_snapshots:
            if not snap.is_mainline:
                continue

            prev = prior.get(snap.subject_key)
            from_state = prev.state if prev else None
            to_state = snap.state
            transition_type = self._transition_type(from_state, to_state)
            confidence = self._calc_confidence(snap, prev, transition_type)
            trigger_flags = self._calc_trigger_flags(snap, prev, transition_type)

            evidence: dict[str, Any] = {"transition_type": transition_type}
            if prev:
                evidence["from_state"] = prev.state
                evidence["from_score"] = str(prev.state_score)
                evidence["from_is_mainline"] = prev.is_mainline

            transitions.append(
                MainlineStateTransitionDTO(
                    trade_date=trade_date,
                    subject_key=snap.subject_key,
                    theme_name=snap.theme_name,
                    from_state=from_state,
                    to_state=to_state,
                    transition_type=transition_type,
                    from_score=prev.state_score if prev else Decimal("0"),
                    to_score=snap.state_score,
                    confidence=confidence,
                    trigger_flags=trigger_flags,
                    evidence_json=evidence,
                )
            )

        return transitions

    def _state_rank(self, state: str | None) -> int:
        if state is None:
            return -1
        return self._STATE_RANK.get(state, -1)

    def _transition_type(self, from_state: str | None, to_state: str) -> str:
        if to_state == "fade_confirmed":
            return "fade"
        if from_state is None or from_state == to_state:
            return "flat"
        from_rank = self._state_rank(from_state)
        to_rank = self._state_rank(to_state)
        if from_rank == -1 or to_rank == -1:
            return "flat"
        if to_rank > from_rank:
            return "upgrade"
        if to_rank < from_rank:
            return "downgrade"
        return "flat"

    def _calc_confidence(
        self,
        snap: MainlineStateDailyDTO,
        prev: MainlineStateDailyDTO | None,
        transition_type: str,
    ) -> Decimal:
        if prev is None:
            return Decimal("60")
        score_delta = abs(float(snap.state_score) - float(prev.state_score))
        conf = Decimal("60") + Decimal(str(min(score_delta * 0.8, 30.0)))
        if transition_type == "fade":
            conf += Decimal("5")
        return min(conf, Decimal("95"))

    def _calc_trigger_flags(
        self,
        snap: MainlineStateDailyDTO,
        prev: MainlineStateDailyDTO | None,
        transition_type: str,
    ) -> list[str]:
        flags: list[str] = []
        if prev is None:
            flags.append("no_previous_snapshot")
            return flags

        # 主线强度跳跃
        if float(snap.mainline_strength_score) > float(prev.mainline_strength_score) + 8.0:
            flags.append("mainline_strength_jump")

        # 退潮风险跳跃
        if float(snap.fade_confirmed_score) > float(prev.fade_confirmed_score) + 10.0:
            flags.append("fade_risk_jump")

        # 状态变更
        if snap.state != prev.state:
            flags.append("state_changed")

        # 进入退潮
        if transition_type == "fade":
            flags.append("enter_fade_confirmed")

        # 恢复信号
        if prev.state in {"fade_watch", "fade_confirmed"} and snap.state in {"repair", "acceleration"}:
            flags.append("recovery_signal")

        return flags
