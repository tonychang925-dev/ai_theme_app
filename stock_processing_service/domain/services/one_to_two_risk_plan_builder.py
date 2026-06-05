from __future__ import annotations

from stock_processing_service.contracts.dto.one_to_two_dto import OneToTwoFeatures, RuleResult, ScoreResult


class OneToTwoRiskPlanBuilder:
    """构建 1进2 的触发/失效/退出计划。"""

    def build(self, f: OneToTwoFeatures, rule: RuleResult, score: ScoreResult) -> dict:
        return {
            "trigger_plan": {
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
            },
            "invalidation_plan": [
                "板块无助攻",
                "同题材被其他股票卡位",
                "高开超过7%后快速回落",
                "首次封板后反复炸板",
                "10:30前不能有效封板",
            ],
            "exit_plan": [
                "二板当天炸板且午后不能回封，减仓或清仓",
                "二板后次日低开，等待冲高失败后离场",
                "二板后次日高开7%-8%后回落，及时兑现",
                "三板炸板或明显走弱，第一时间兑现",
            ],
        }
