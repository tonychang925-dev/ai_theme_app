"""PR-14D: EngineReportAdapter — Notion/PreMarket Brief 消费 engine report 的轻量适配层。

不修改 Notion publisher 或 PreMarket Brief builder 内部逻辑，
只提供结构化提取方法，调用方按需使用。
"""

from __future__ import annotations

from typing import Any


class EngineReportAdapter:
    """Extract engine report sections for downstream consumers."""

    def __init__(self, recap_doc: dict[str, Any]) -> None:
        self._recap = recap_doc
        # The composer output may be merged into daily_review_v2 or stored directly
        v2 = recap_doc.get("daily_review_v2", {}) or {}
        self._engine = {
            "engine_summary": recap_doc.get("engine_summary") or v2.get("engine_summary"),
            "market_regime_review": recap_doc.get("market_regime_review"),
            "index_technical_reviews": recap_doc.get("index_technical_reviews") or v2.get("index_technical_reviews", []),
            "mainline_daily_states": recap_doc.get("mainline_daily_states") or v2.get("mainline_daily_states", []),
            "post_market_decision_v2": recap_doc.get("post_market_decision_v2"),
            "evidence_alignment_index": recap_doc.get("evidence_alignment_index") or v2.get("evidence_alignment_index"),
        }

    @property
    def has_engine_data(self) -> bool:
        return bool(self._engine["engine_summary"])

    # ── Notion sections ──

    def notion_trade_conclusion(self) -> dict[str, Any]:
        es = self._engine["engine_summary"] or {}
        return {
            "allow_trade": es.get("allow_trade", False),
            "trade_mode": es.get("trade_mode", "no_trade"),
            "position_limit": es.get("position_limit"),
            "blocking_rule": es.get("no_trade_blocking_rule"),
            "reasons": es.get("no_trade_reasons", []),
            "next_day_strategy": es.get("next_day_strategy", ""),
            "conclusion": es.get("conclusion", ""),
            "risk_notes": es.get("risk_notes", []),
        }

    def notion_market_environment(self) -> dict[str, Any]:
        mr = self._engine["market_regime_review"] or {}
        return {
            "broad_market_regime": mr.get("broad_market_regime", ""),
            "short_term_sentiment": mr.get("short_term_sentiment", ""),
            "mainline_environment": mr.get("mainline_environment", ""),
            "allow_trade": mr.get("allow_trade", False),
            "trade_mode": mr.get("trade_mode", "no_trade"),
            "index_data_ready": mr.get("index_data_ready", False),
            "index_count": len(self._engine["index_technical_reviews"]),
        }

    def notion_mainline_states(self) -> list[dict[str, Any]]:
        return self._engine["mainline_daily_states"] or []

    def notion_d1_watch(self) -> dict[str, Any]:
        pdv = self._engine["post_market_decision_v2"] or {}
        d1s = pdv.get("weak_to_strong_d1_reviews", [])
        focus = pdv.get("next_day_focus_stocks", [])
        return {
            "d1_total": len(d1s),
            "d1_formal": sum(1 for d in d1s if d.get("candidate_level") == "formal"),
            "d1_observe": sum(1 for d in d1s if d.get("candidate_level") != "formal"),
            "focus_count": len(focus),
        }

    # ── PreMarket Brief sections ──

    def premkt_trading_permission(self) -> dict[str, Any]:
        """次日交易权限摘要，供盘前必读使用。"""
        es = self._engine["engine_summary"] or {}
        allow = bool(es.get("allow_trade", False))
        return {
            "allow_trade": allow,
            "trade_mode": es.get("trade_mode", "no_trade"),
            "position_limit": es.get("position_limit", 0),
            "no_trade_blocking_rule": es.get("no_trade_blocking_rule"),
            "next_day_strategy": es.get("next_day_strategy", ""),
            "has_formal_buy_plan": allow and (self.notion_d1_watch().get("focus_count", 0) > 0),
        }

    def premkt_observation_list(self) -> list[dict[str, Any]]:
        """次日观察清单（D1 observe_only + focus stocks）。"""
        pdv = self._engine["post_market_decision_v2"] or {}
        d1s = pdv.get("weak_to_strong_d1_reviews", [])
        result = []
        for d in d1s:
            result.append({
                "stock_id": d.get("stock_id", ""),
                "stock_name": d.get("stock_name", ""),
                "theme_name": d.get("theme_name", ""),
                "mainline_id": d.get("mainline_id", ""),
                "candidate_level": d.get("candidate_level", "observe_only"),
                "candidate_score": d.get("candidate_score"),
                "buy_condition": d.get("buy_condition", []),
                "invalid_condition": d.get("invalid_condition", []),
                "d2_required": d.get("d2_required", False),
                "d2_status": d.get("d2_status", "pending"),
            })
        return result

    def premkt_d2_pending_list(self) -> list[dict[str, Any]]:
        """D2 pending 竞价检查清单。"""
        focus = (self._engine["post_market_decision_v2"] or {}).get("next_day_focus_stocks", [])
        result = []
        for f in focus:
            result.append({
                "stock_id": f.get("stock_id", ""),
                "stock_name": f.get("stock_name", ""),
                "mainline_name": f.get("theme_name", ""),
                "d1_level": f.get("candidate_level", ""),
                "buy_condition": f.get("buy_condition", []),
                "invalid_condition": f.get("invalid_condition", []),
                "d2_required": f.get("d2_required", True),
                "d2_status": "pending",
                "suggested_position": f.get("suggested_position", 0),
            })
        return result

    def premkt_risk_notes(self) -> list[str]:
        es = self._engine["engine_summary"] or {}
        return es.get("risk_notes", [])

    # ── Diagnostics ──

    def diagnostics(self) -> dict[str, Any]:
        return {
            "has_engine_data": self.has_engine_data,
            "engine_summary_present": bool(self._engine["engine_summary"]),
            "market_regime_present": bool(self._engine["market_regime_review"]),
            "mainline_states_count": len(self._engine["mainline_daily_states"]),
            "index_tech_count": len(self._engine["index_technical_reviews"]),
            "fallback_to_sections": not self.has_engine_data,
        }
