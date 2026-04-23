from __future__ import annotations

from dataclasses import dataclass


ELIGIBLE_CYCLE_STAGES = {"start", "fermentation", "divergence", "rebound"}
TRADE_FOCUS_ACTIONS = {"主做", "关注弱转强", "可主做", "可做弱转强"}
UNCONFIRMED_LEADER_STATUSES = {"", "当日领涨候选", "待确认龙头"}


@dataclass(frozen=True)
class ThemeLeaderLlmQueueInput:
    trade_date: str
    subject_key: str
    theme_name: str
    mainline_bucket: str
    primary_cycle_stage: str
    leader_status: str
    action_bias: str
    candidate_count: int
    limit_up_count: int
    top_candidate_score: float
    second_candidate_score: float
    top_is_limit_up: bool
    second_is_limit_up: bool
    top_role_label: str = ""
    second_role_label: str = ""
    mainline_alive: bool = False
    mainline_strength_score: float = 0.0
    fade_watch: bool = False
    fade_confirmed: bool = False


@dataclass(frozen=True)
class ThemeLeaderLlmQueueDecision:
    trade_date: str
    subject_key: str
    theme_name: str
    mainline_bucket: str
    primary_cycle_stage: str
    need_llm_judgement: bool
    is_trade_focus: bool
    queue_priority: int
    queue_reason: str
    source_type: str = "p3.phase2.leader_llm_queue"
    source_version: str = "theme_leader_llm_queue.v1"
    rule_version: str = "theme_leader_llm_queue.v1"


class ThemeLeaderLlmQueueService:
    def evaluate(self, item: ThemeLeaderLlmQueueInput) -> ThemeLeaderLlmQueueDecision:
        mainline_bucket = (
            "main"
            if bool(item.mainline_alive) and float(item.mainline_strength_score or 0.0) >= 75.0
            else "strong_branch"
            if bool(item.mainline_alive)
            else "inactive"
        )
        cycle_stage = str(item.primary_cycle_stage or "").strip()
        leader_status = str(item.leader_status or "").strip()
        action_bias = str(item.action_bias or "").strip()
        top_role_label = str(item.top_role_label or "").strip()
        mainline_strength = float(item.mainline_strength_score or 0.0)

        is_trade_focus = action_bias in TRADE_FOCUS_ACTIONS or cycle_stage in {"divergence", "rebound"}

        reasons: list[str] = []
        priority = 0
        has_decision_conflict = False

        if not bool(item.mainline_alive):
            reasons.append("主线未存活，不进入龙头 LLM 裁决")
        elif bool(item.fade_confirmed):
            reasons.append("主线退潮已确认，不进入龙头 LLM 裁决")
        elif cycle_stage not in ELIGIBLE_CYCLE_STAGES:
            reasons.append("非启动/发酵/分歧/弱转强阶段，不进入龙头 LLM 裁决")
        elif item.candidate_count <= 0:
            reasons.append("缺少候选股，不进入龙头 LLM 裁决")
        else:
            if mainline_strength >= 80:
                priority += 200
                reasons.append("主线强度高，优先级提升")
            elif mainline_strength >= 65:
                priority += 150
                reasons.append("主线强度中高，纳入优先队列")
            else:
                priority += 110
            if is_trade_focus:
                priority += 20
            if bool(item.fade_watch):
                priority -= 20
                reasons.append("处于退潮观察，优先级下调")

            if cycle_stage == "divergence":
                priority += 70
                reasons.append("分歧阶段，需确认龙头是否继续成立")
                has_decision_conflict = True
            elif cycle_stage == "rebound":
                priority += 75
                reasons.append("弱转强阶段，需确认龙头是否反包强化")
                has_decision_conflict = True
            elif cycle_stage == "fermentation":
                priority += 35
                reasons.append("发酵阶段，需跟踪龙头/龙二/卡位演化")
            elif cycle_stage == "start":
                priority += 20
                reasons.append("启动阶段，需确认首轮领涨候选")

            if leader_status in UNCONFIRMED_LEADER_STATUSES:
                priority += 55
                reasons.append("龙头状态未确认")
                has_decision_conflict = True

            if item.candidate_count >= 2 and item.second_candidate_score > 0:
                score_gap = float(item.top_candidate_score or 0) - float(item.second_candidate_score or 0)
                if score_gap <= 8:
                    priority += 35
                    reasons.append("前两名候选分差接近")
                    has_decision_conflict = True

            if item.limit_up_count >= 2:
                priority += 20
                reasons.append("存在多只涨停前排，需区分龙头/卡位/补涨")
                has_decision_conflict = True

            if item.top_is_limit_up and item.second_is_limit_up:
                priority += 10

            if top_role_label and top_role_label != "龙头":
                priority += 10
                reasons.append("规则首位候选未直接落在龙头角色")
                has_decision_conflict = True

        need_llm_judgement = (
            bool(item.mainline_alive)
            and not bool(item.fade_confirmed)
            and cycle_stage in ELIGIBLE_CYCLE_STAGES
            and item.candidate_count > 0
            and has_decision_conflict
        )

        queue_reason = "；".join(reasons) if reasons else "规则判断已足够明确"
        return ThemeLeaderLlmQueueDecision(
            trade_date=item.trade_date,
            subject_key=item.subject_key,
            theme_name=item.theme_name,
            mainline_bucket=mainline_bucket,
            primary_cycle_stage=cycle_stage,
            need_llm_judgement=need_llm_judgement,
            is_trade_focus=is_trade_focus,
            queue_priority=priority if need_llm_judgement else 0,
            queue_reason=queue_reason,
        )
