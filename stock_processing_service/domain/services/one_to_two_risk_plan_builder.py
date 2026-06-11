from __future__ import annotations

from decimal import Decimal

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult, ScoreResult


from stock_processing_service.domain.services.one_to_two_technical_summary_formatter import (
    OneToTwoTechnicalSummaryFormatter,
)


class OneToTwoRiskPlanBuilder:
    """构建 1进2 的观察解释、触发计划、放弃条件。

    Phase 3: 不改变 decision / score / rank，只补解释字段。
    """

    def __init__(self) -> None:
        self._tech_formatter = OneToTwoTechnicalSummaryFormatter()

    # ── public entry ──

    def build(self, f: OneToTwoFeatures, rule: RuleResult, score: ScoreResult) -> dict:
        decision = rule.decision

        plan = {
            "trigger_plan": self._trigger_plan(f, decision),
            "invalidation_plan": self._invalidation_plan(decision),
            "exit_plan": self._exit_plan(decision),
            # Phase 3 explanation fields
            "observation_reason": self._build_observation_reason(f, rule, score),
            "subject_logic": self._build_subject_logic(f),
            "technical_summary": self._build_technical_summary(f, rule, score),
            "event_logic": self._build_event_logic(f),
            "key_parameters": self._build_key_parameters(f, rule, score),
            "tomorrow_plan": self._build_tomorrow_plan(f, decision),
            "give_up_conditions": self._build_give_up_conditions(f, decision),
        }
        return plan

    # ── P3-A: observation_reason ──

    def _build_observation_reason(self, f: OneToTwoFeatures, rule: RuleResult, score: ScoreResult) -> list[str]:
        reasons: list[str] = []

        # 1. First-board fact
        fb_type = str(getattr(f, "first_board_type", "") or "")
        if fb_type == "chain_first_board":
            reasons.append("T日为真实首板，且前一交易日未涨停，符合 chain_first_board")
        else:
            reasons.append(f"T日首板事实入池，首板类型: {fb_type}")

        # 2. Mainline / hotspot context
        if f.is_confirmed_mainline:
            reasons.append("所属题材属于 confirmed mainline")
        elif f.is_strong_hotspot:
            reasons.append("所属题材属于 strong hotspot 观察范围")

        # 3. Turnover
        tr = f.turnover_rate
        if tr is not None and tr >= Decimal("0.08"):
            reasons.append(f"换手率 {float(tr)*100:.1f}%，达到观察要求")
        elif tr is not None:
            reasons.append(f"换手率 {float(tr)*100:.1f}%，偏低（列为风险因素）")

        # 4. Market environment
        mode = str(f.market_trade_mode or "")
        if mode in ("mainline_core_only", "mainline_tradable"):
            reasons.append("市场环境允许观察主线核心首板")
        elif mode == "no_trade":
            reasons.append("市场环境 no_trade，仅保留观察不 focus")

        # 5. Decision explanation
        if rule.decision == "focus":
            reasons.append("综合评分和技术形态达到 focus 标准")
        elif rule.decision == "observe_only":
            rf = rule.risk_flags or []
            if any("技术" in str(r) for r in rf):
                reasons.append("技术形态未完全确认，因此降为谨慎观察")
            elif any("换手" in str(r) for r in rf):
                reasons.append("换手率偏低，降为谨慎观察")
            elif any("板块" in str(r) for r in rf):
                reasons.append("板块合力偏弱，降为谨慎观察")
            else:
                reasons.append(f"暂不符合 focus 条件: {'; '.join(rf[:2]) if rf else '综合评分不足'}")

        # 6. Veto-free note
        if not rule.veto_reasons:
            reasons.append("无硬否决项")

        return reasons

    # ── P3-C: subject_logic ──

    @staticmethod
    def _build_subject_logic(f: OneToTwoFeatures) -> dict:
        auth = dict(f.subject_authenticity or {})
        return {
            "subject_key": f.subject_key,
            "subject_name": f.subject_name,
            "lifecycle_state": f.lifecycle_state,
            "same_subject_limit_count": f.same_subject_limit_count,
            "same_subject_strong_count": f.same_subject_strong_count,
            "stock_subject_authenticity": {
                "level": auth.get("level", "unknown"),
                "score": float(Decimal(str(auth.get("score", 0))) or 0),
            },
            "selection_reason": str(auth.get("authenticity_scope") or "subject_fallback"),
        }

    # ── P3-E: event_logic — event-driven evidence read-only, no DB query ──

    @staticmethod
    def _build_event_logic(f: OneToTwoFeatures) -> dict:
        """Build event_logic from pre-computed subject_authenticity data.
        Does NOT query event_theme_map or news_event — frontend must never do so either.
        """
        auth = dict(f.subject_authenticity or {})
        source_trace = dict(f.source_trace or {})
        subject_selection = dict(source_trace.get("subject_selection") or {})

        level = str(auth.get("level") or "unknown")
        score_val = auth.get("score")

        # Check for actual event data
        evidence_events = auth.get("evidence_events") or []
        has_events = bool(evidence_events)

        # Determine evidence level
        if level in ("core", "direct") and score_val is not None and float(score_val) >= 70:
            evidence_level = "strong"
            summary = "个股与题材存在明确的产业链/主营/公告证据，题材正宗度较高。"
        elif level in ("core", "direct", "related"):
            # Events exist — the subject has related event drivers
            evidence_level = "medium"
            summary = f"题材存在 {len(evidence_events)} 条近期驱动事件，个股与题材存在一定关联。"
        elif has_events:
            evidence_level = "weak"
            summary = f"题材存在 {len(evidence_events)} 条近期驱动事件，但个股与题材的产业链/公告关联度不足，需人工复核。"
        else:
            evidence_level = "weak"
            summary = "暂无直接事件证据，题材正宗度偏弱，需人工复核。"

        # Collect evidence fragments from source_trace
        evidence: list[dict] = []
        sel_auth = subject_selection.get("subject_authenticity", {})
        if isinstance(sel_auth, dict):
            if sel_auth.get("purity_score") is not None:
                evidence.append({
                    "source": "stock_subject_authenticity",
                    "type": "purity",
                    "score": sel_auth.get("purity_score"),
                    "scope": str(sel_auth.get("authenticity_scope") or ""),
                })
            if sel_auth.get("theme_tier"):
                evidence.append({
                    "source": "stock_subject_authenticity",
                    "type": "theme_tier",
                    "value": sel_auth.get("theme_tier"),
                })

        first_board_trace = dict(source_trace.get("first_board_trace") or {})
        if first_board_trace.get("chain_violation_reason"):
            evidence.append({
                "source": "first_board_classifier",
                "type": "chain_violation",
                "reason": first_board_trace.get("chain_violation_reason"),
            })

        return {
            "summary": summary,
            "evidence_level": evidence_level,
            "subject_authenticity_level": level,
            "subject_authenticity_score": (
                float(score_val) if score_val is not None else None
            ),
            "evidence": evidence,
        }

    # ── P3-B: technical summary via OneToTwoTechnicalSummaryFormatter ──

    def _build_technical_summary(self, f: OneToTwoFeatures, rule: RuleResult, score: ScoreResult) -> dict:
        tech_score_str = score.score_detail.get("technical_structure", "0")
        try:
            tech_score = float(Decimal(str(tech_score_str)))
        except Exception:
            tech_score = None

        return self._tech_formatter.format(
            f.kline_pattern_quality,
            technical_structure_score=tech_score,
            risk_flags=list(rule.risk_flags),
            veto_reasons=list(rule.veto_reasons),
        )

    # ── P3-A: key_parameters ──

    @staticmethod
    def _build_key_parameters(f: OneToTwoFeatures, rule: RuleResult, score: ScoreResult) -> dict:
        return {
            "first_board_type": getattr(f, "first_board_type", ""),
            "limit_streak_count": f.limit_streak_count,
            "previous_trade_date_limit_up": f.previous_trade_date_limit_up,
            "turnover_rate": float(f.turnover_rate) if f.turnover_rate is not None else None,
            "is_one_word_board": f.is_one_word_board,
            "is_late_seal": f.is_late_seal,
            "first_limit_time": f.first_limit_time,
            "same_subject_limit_count": f.same_subject_limit_count,
            "same_subject_strong_count": f.same_subject_strong_count,
            "lifecycle_state": f.lifecycle_state,
            "market_trade_mode": f.market_trade_mode,
            "allow_trade": f.allow_trade,
            "final_score": float(score.final_score) if score.final_score is not None else None,
            "technical_structure_score": (
                float(Decimal(str(score.score_detail.get("technical_structure", "0"))))
                if score.score_detail.get("technical_structure") else None
            ),
            "theme_authenticity_score": (
                float(Decimal(str(score.score_detail.get("theme_authenticity", "0"))))
                if score.score_detail.get("theme_authenticity") else None
            ),
            "board_breadth_score": (
                float(Decimal(str(score.score_detail.get("board_breadth", "0"))))
                if score.score_detail.get("board_breadth") else None
            ),
            "risk_flags": list(rule.risk_flags),
            "veto_reasons": list(rule.veto_reasons),
        }

    # ── P3-D: tomorrow_plan (decision-aware, no buy semantics) ──

    def _build_tomorrow_plan(self, f: OneToTwoFeatures, decision: str) -> dict:
        mode = str(f.market_trade_mode or "")

        if decision == "focus":
            return {
                "expected_behavior": "明日重点观察二板确认，关注竞价强度、开盘主动性和回封质量。",
                "auction_watch": [
                    "理想竞价为温和高开 2%-5% 并伴随量能放大",
                    "题材核心股同步走强更优",
                ],
                "confirmation_triggers": [
                    "开盘后主动上攻并接近涨停",
                    "首次开板后快速回封",
                    "封单持续增强且同题材联动",
                ],
            }

        if decision == "observe_only":
            if mode == "no_trade":
                return {
                    "expected_behavior": "市场环境 no_trade，仅观察不主动关注。",
                    "auction_watch": ["仅保留数据跟踪，不做主动观察。"],
                    "confirmation_triggers": [],
                }
            return {
                "expected_behavior": "先观察承接和主动性，只有走势超预期才升级观察。",
                "auction_watch": [
                    "观察竞价是否有量能支撑",
                    "低开需看到明确弱转强信号才考虑升级",
                ],
                "confirmation_triggers": [
                    "回踩不破关键位后放量上攻",
                    "分时承接强于同题材平均水平",
                ],
            }

        if decision == "pending_review_only":
            return {
                "expected_behavior": "需人工确认题材、技术或数据缺口，未确认前不作为交易对象。",
                "auction_watch": ["人工确认后方可进入观察。"],
                "confirmation_triggers": [],
            }

        # reject — no plan
        return {"expected_behavior": "", "auction_watch": [], "confirmation_triggers": []}

    # ── P3-D: give_up_conditions ──

    def _build_give_up_conditions(self, f: OneToTwoFeatures, decision: str) -> list[str]:
        conditions: list[str] = []

        if decision == "focus":
            conditions = [
                "低开低走且无承接",
                "高开后快速回落跌破分时均线",
                "题材核心股明显走弱",
                "冲板失败后连续炸板",
                "市场环境转为 no_trade",
            ]
        elif decision == "observe_only":
            conditions = [
                "高开无承接",
                "冲板失败后持续回落",
                "跌破关键支撑",
                "竞价量能严重不足",
            ]
        elif decision == "pending_review_only":
            conditions = [
                "人工复核周期内数据未补全",
                "人工判断题材或技术不支持",
            ]

        return conditions

    # ── legacy plan helpers (preserved from v1, cleaned of buy semantics) ──

    @staticmethod
    def _trigger_plan(f: OneToTwoFeatures, decision: str) -> dict:
        if decision == "reject":
            return {"auction": [], "intraday": []}
        return {
            "auction": [
                "9:24后重点观察集合竞价",
                "高开3%-5%为佳",
                "竞价量能活跃，不能明显缩量",
                "低开且无弱转强则放弃",
            ],
            "intraday": [
                "开盘后快速拉升",
                "同题材内率先冲击涨停或明显强于竞争对手",
                "二板封板速度快，封单稳定",
                "炸板后能够快速回封",
            ],
        }

    @staticmethod
    def _invalidation_plan(decision: str) -> list[str]:
        if decision == "reject":
            return []
        return [
            "板块无助攻",
            "同题材被其他股票卡位",
            "高开超过7%后快速回落",
            "首次封板后反复炸板",
            "10:30前不能有效封板",
        ]

    @staticmethod
    def _exit_plan(decision: str) -> list[str]:
        if decision == "reject":
            return []
        return [
            "二板当天炸板且午后不能回封，减仓或清仓",
            "二板后次日低开，等待冲高失败后离场",
            "二板后次日高开7%-8%后回落，及时兑现",
            "三板炸板或明显走弱，第一时间兑现",
        ]
