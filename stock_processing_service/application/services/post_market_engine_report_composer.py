"""PR-14A: PostMarketEngineReportComposer.

Composes engine outputs into DailyReviewV2 report structure.
Does NOT re-evaluate — only reads existing engine results.
"""

from __future__ import annotations

import logging
from typing import Any

from stock_processing_service.application.services.post_market_narrative_composer import (
    PostMarketNarrativeComposer,
)
from stock_processing_service.application.services.post_market_hotspot_overview_composer import (
    PostMarketHotspotOverviewComposer,
)

logger = logging.getLogger(__name__)


class PostMarketEngineReportComposer:
    """Compose engine outputs into a structured report view model.

    Input: recap_doc (already populated with engine outputs)
    Output: dict with engine_summary, market_regime_review,
            index_technical_reviews, mainline_daily_states,
            post_market_decision_v2, market_overview_review,
            market_overview_narrative, market_hotspot_overview
    """

    def compose(self, recap_doc: dict[str, Any]) -> dict[str, Any]:
        """Build engine report structure from existing recap_doc fields."""

        regime = recap_doc.get("market_regime_review", {})
        pdv2 = recap_doc.get("post_market_decision_v2", {})
        lifecycle = recap_doc.get("mainline_lifecycle_reviews", [])
        amu = recap_doc.get("active_mainline_universe", {})
        regime_diag = recap_doc.get("market_regime_diagnostics", {})

        # ── 1. engine_summary ──
        engine_summary = self._build_engine_summary(regime, pdv2)

        # ── 2. market_regime_review ──
        market_regime_review = self._build_market_regime_review(
            regime, regime_diag
        )

        # ── 3. index_technical_reviews ──
        index_technical_reviews = self._build_index_technical_reviews(
            regime, regime_diag
        )

        # ── 4. mainline_daily_states ──
        mainline_daily_states = self._build_mainline_daily_states(
            lifecycle, pdv2, amu
        )

        # ── 5. post_market_decision_v2 ──
        post_market_decision_v2 = self._build_pdv2_review(pdv2)

        # ── 6. evidence alignment index ──
        evidence_alignment_index = self._build_evidence_alignment_index(
            mainline_daily_states, pdv2
        )

        # ── 7. market overview ──
        market_summary = self._pass_through(recap_doc, "market_summary")
        market_overview_review = self._pass_through(recap_doc, "market_overview_review")
        narrative_composer = PostMarketNarrativeComposer()
        market_overview_narrative = narrative_composer.compose_market_overview(
            engine_summary=engine_summary,
            market_regime_review=market_regime_review,
            index_technical_reviews=index_technical_reviews,
            mainline_daily_states=mainline_daily_states,
            post_market_decision_v2=post_market_decision_v2,
            market_overview_review=market_overview_review,
            market_summary=market_summary,
        )
        market_hotspot_narrative = narrative_composer.compose_market_hotspot(
            market_overview_review=market_overview_review,
            market_summary=market_summary,
            market_regime_review=market_regime_review,
            mainline_daily_states=mainline_daily_states,
            engine_summary=engine_summary,
            post_market_decision_v2=post_market_decision_v2,
        )
        mainline_narrative = narrative_composer.compose_mainline_narrative(
            mainline_daily_states=mainline_daily_states,
            market_regime_review=market_regime_review,
            engine_summary=engine_summary,
            post_market_decision_v2=post_market_decision_v2,
        )
        d1_narrative = narrative_composer.compose_d1_narrative(
            engine_summary=engine_summary,
            market_regime_review=market_regime_review,
            post_market_decision_v2=post_market_decision_v2,
        )
        hotspot_overview_composer = PostMarketHotspotOverviewComposer()
        market_hotspot_overview = hotspot_overview_composer.compose(recap_doc)

        return {
            "engine_summary": engine_summary,
            "market_regime_review": market_regime_review,
            "index_technical_reviews": index_technical_reviews,
            "mainline_daily_states": mainline_daily_states,
            "post_market_decision_v2": post_market_decision_v2,
            "evidence_alignment_index": evidence_alignment_index,
            "market_overview_narrative": market_overview_narrative,
            "market_hotspot_overview": market_hotspot_overview,
            "market_hotspot_narrative": market_hotspot_narrative,
            "mainline_narrative": mainline_narrative,
            "d1_narrative": d1_narrative,
            "market_overview_review": market_overview_review,
        }

    def _build_engine_summary(
        self, regime: dict, pdv2: dict
    ) -> dict[str, Any]:
        tp = pdv2.get("trading_permission", {})
        ntr = regime.get("no_trade_reasons", [])
        blocking = regime.get("no_trade_blocking_rule", "")

        return {
            "allow_trade": bool(tp.get("allow_trade", False)),
            "trade_mode": str(tp.get("trade_mode", "no_trade")),
            "position_limit": float(tp.get("position_limit", 0)),
            "no_trade_blocking_rule": blocking if not tp.get("allow_trade") else None,
            "no_trade_reasons": list(ntr) if isinstance(ntr, list) else [],
            "action_bias": self._action_bias(regime, pdv2),
            "conclusion": self._conclusion(regime, pdv2),
            "next_day_strategy": self._next_day_strategy(regime),
            "risk_notes": list(regime.get("risk_notes", [])),
        }

    def _build_market_regime_review(
        self, regime: dict, regime_diag: dict
    ) -> dict[str, Any]:
        return {
            "broad_market_regime": str(regime.get("broad_market_regime", "")),
            "short_term_sentiment": str(regime.get("short_term_sentiment", "")),
            "mainline_environment": str(regime.get("mainline_environment", "")),
            "allow_trade": bool(regime.get("allow_trade", False)),
            "trade_mode": str(regime.get("trade_mode", "no_trade")),
            "position_limit": float(regime.get("position_limit", 0)),
            "no_trade_blocking_rule": regime.get("no_trade_blocking_rule", ""),
            "no_trade_reasons": list(regime.get("no_trade_reasons", [])),
            "index_data_ready": bool(regime_diag.get("index_data_ready", False)),
            "index_data_source": str(regime_diag.get("index_data_source", "")),
            "index_technical_reviews": self._build_index_technical_reviews(regime, regime_diag),
            "diagnostics": regime.get("diagnostics", {}),
        }

    def _build_index_technical_reviews(
        self, regime: dict, regime_diag: dict
    ) -> list[dict[str, Any]]:
        reviews = regime.get("index_technical_reviews", [])
        if not reviews:
            reviews = regime_diag.get("index_technical_reviews", [])
        result = []
        for r in reviews:
            flags = r.get("risk_flags") or r.get("risk_flags_json") or []
            if isinstance(flags, str):
                try:
                    import json
                    flags = json.loads(flags)
                except Exception:
                    flags = [flags]
            result.append({
                "index_code": str(r.get("index_code", "")),
                "index_name": str(r.get("index_name", "")),
                "close": self._float_or_none(r.get("close")),
                "pct_chg": self._float_or_none(r.get("pct_chg")),
                "trend_state": str(r.get("trend_state", "")),
                "trend_score": float(r.get("trend_score", 0) or 0),
                "above_ma5": bool(r.get("above_ma5")),
                "above_ma10": bool(r.get("above_ma10")),
                "above_ma20": bool(r.get("above_ma20")),
                "above_ma60": bool(r.get("above_ma60")),
                "ma_structure": str(r.get("ma_structure", "")),
                "macd_state": str(r.get("macd_state", "")),
                "support_level": self._float_or_none(r.get("support_level")),
                "resistance_level": self._float_or_none(r.get("resistance_level")),
                "nearest_support_level": self._float_or_none(r.get("nearest_support_level")),
                "nearest_resistance_level": self._float_or_none(r.get("nearest_resistance_level")),
                "support_distance_pct": self._float_or_none(r.get("support_distance_pct")),
                "resistance_distance_pct": self._float_or_none(r.get("resistance_distance_pct")),
                "support_status": str(r.get("support_status", "")),
                "resistance_status": str(r.get("resistance_status", "")),
                "volume_pattern": str(r.get("volume_pattern", "")),
                "index_trade_hint": str(r.get("index_trade_hint", "")),
                "warning_level": str(r.get("warning_level", "normal")),
                "risk_flags": flags if isinstance(flags, list) else [],
                "conclusion": self._index_conclusion(r),
            })
        return result

    def _build_mainline_daily_states(
        self,
        lifecycle: list[dict],
        pdv2: dict,
        amu: dict,
    ) -> list[dict[str, Any]]:
        lifecycle_by_id = {r.get("mainline_id", ""): r for r in lifecycle}

        strong_pool = pdv2.get("strong_stock_pool_reviews", [])
        d1_list = pdv2.get("weak_to_strong_d1_reviews", [])
        focus_list = pdv2.get("next_day_focus_stocks", [])

        mainlines = amu.get("active_mainlines", [])

        result = []
        for ml in mainlines:
            mid = str(ml.get("mainline_id", ""))
            lr = lifecycle_by_id.get(mid, {})

            strong_count = sum(1 for s in strong_pool if s.get("mainline_id") == mid)
            d1_count = sum(1 for d in d1_list if d.get("mainline_id") == mid)
            focus_count = sum(1 for f in focus_list if f.get("mainline_id") == mid)

            result.append({
                "trade_date": str(amu.get("trade_date", "")),
                "mainline_id": mid,
                "mainline_name": str(ml.get("mainline_name", "")),
                "canonical_subject_key": str(ml.get("canonical_subject_key", "")),
                "active_subject_keys": amu.get("active_subject_keys", []),
                "lifecycle_state": str(lr.get("lifecycle_state", "unknown")),
                "mainline_alive": bool(lr.get("mainline_alive", False)),
                "mainline_trade_alive": bool(lr.get("mainline_trade_alive", False)),
                "risk_state": lr.get("risk_state"),
                "event_count_1d": 0,
                "event_count_3d": 0,
                "event_count_7d": 0,
                "mainline_strength_score": lr.get("mainline_strength_score"),
                "fade_risk_score": lr.get("fade_risk_score"),
                "strong_pool_count": strong_count,
                "d1_count": d1_count,
                "focus_count": focus_count,
                "action_advice": self._mainline_action(lr),
                "conclusion": self._mainline_conclusion(lr),
                "diagnostics": lr.get("diagnostics", {}),
            })
        return result

    def _build_pdv2_review(self, pdv2: dict) -> dict[str, Any]:
        return {
            "trading_permission": pdv2.get("trading_permission", {}),
            "strong_stock_pool_reviews": pdv2.get("strong_stock_pool_reviews", []),
            "weak_to_strong_d1_reviews": pdv2.get("weak_to_strong_d1_reviews", []),
            "next_day_focus_stocks": pdv2.get("next_day_focus_stocks", []),
            "trading_principle_v2": pdv2.get("trading_principle_v2", {}),
            "diagnostics": pdv2.get("diagnostics", {}),
        }

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    @staticmethod
    def _pass_through(recap_doc: dict[str, Any], key: str) -> dict[str, Any]:
        value = recap_doc.get(key)
        return dict(value) if isinstance(value, dict) else {}

    def _action_bias(self, regime: dict, pdv2: dict) -> str:
        tp = pdv2.get("trading_permission", {})
        if not tp.get("allow_trade"):
            return "防守"
        mode = tp.get("trade_mode", "")
        if mode == "ultra_short_only":
            return "超短防守"
        if mode == "mainline_core_only":
            return "主线核心"
        return "正常参与"

    def _conclusion(self, regime: dict, pdv2: dict) -> str:
        tp = pdv2.get("trading_permission", {})
        if not tp.get("allow_trade"):
            reasons = regime.get("no_trade_reasons", [])
            if reasons:
                return f"当前不交易：{reasons[0]}"
            return "当前不交易"
        mode = tp.get("trade_mode", "")
        if mode == "ultra_short_only":
            return "仅允许超短线，需竞价确认"
        if mode == "mainline_core_only":
            return "仅主线核心可参与，仓位控制"
        return "市场环境支持，可按计划参与"

    def _next_day_strategy(self, regime: dict) -> str:
        mode = regime.get("trade_mode", "no_trade")
        if mode == "no_trade":
            return "不做新开仓，只观察主线是否修复"
        if mode == "ultra_short_only":
            return "超短试探，控制仓位 ≤0.2，竞价确认"
        if mode == "mainline_core_only":
            return "聚焦主线核心前排，非核心不参与"
        return "按主线计划执行，注意分歧低吸"

    def _index_conclusion(self, r: dict) -> str:
        trend = str(r.get("trend_state", ""))
        if trend == "bearish_trend":
            return "空头趋势，谨慎"
        if trend == "downtrend_rebound":
            return "弱反抽，不追"
        if trend == "bullish_trend":
            return "多头趋势，支撑有效"
        if trend == "neutral_box":
            return "箱体震荡，观望"
        return "趋势不明"

    def _mainline_action(self, lr: dict) -> str:
        state = str(lr.get("lifecycle_state", ""))
        trade_alive = bool(lr.get("mainline_trade_alive", False))
        if not trade_alive:
            return "回避"
        if state in ("fade_watch",):
            return "仅观察"
        if state in ("divergence", "repair"):
            return "分歧低吸/修复确认"
        if state in ("fermentation", "acceleration"):
            return "按阶段参与"
        if state in ("start", "seed"):
            return "龙头确认"
        return "观察"

    def _build_evidence_alignment_index(
        self,
        mainline_states: list[dict],
        pdv2: dict,
    ) -> dict[str, dict]:
        """PR-14C: Build stock_id/subject_key → engine context index.

        Returns { "by_stock": {...}, "by_subject": {...} }
        Each entry has: active_mainline, mainline_id, mainline_name,
        lifecycle_state, trade_alive, in_layer_c, layer_c_level,
        is_d1_candidate, d1_level, is_focus_stock, trade_action.
        """
        by_stock: dict[str, dict] = {}
        by_subject: dict[str, dict] = {}

        ml_map = {m.get("mainline_id", ""): m for m in mainline_states}

        strong = pdv2.get("strong_stock_pool_reviews", [])
        d1_list = pdv2.get("weak_to_strong_d1_reviews", [])
        focus_list = pdv2.get("next_day_focus_stocks", [])

        d1_by_stock = {str(d.get("stock_id", "")): d for d in d1_list}
        focus_by_stock = {str(f.get("stock_id", "")): f for f in focus_list}
        d1_subjects = {str(d.get("subject_key", "")) for d in d1_list if d.get("subject_key")}

        for s in strong:
            sid = str(s.get("stock_id", ""))
            sk = str(s.get("subject_key", ""))
            mid = str(s.get("mainline_id", ""))
            ml = ml_map.get(mid, {})

            entry = s.get("pool_entry_type", "observe_only")
            is_d1 = sid in d1_by_stock
            is_focus = sid in focus_by_stock
            d1_level = str(d1_by_stock[sid].get("candidate_level", "")) if is_d1 else ""
            trade_alive = bool(ml.get("mainline_trade_alive", False))
            state = str(ml.get("lifecycle_state", "unknown"))
            d1_subject = sk in d1_subjects

            action = "observe_only"
            if is_focus:
                action = "focus"
            elif is_d1 and d1_level == "formal":
                action = "d1_formal"
            elif is_d1:
                action = "d1_observe"
            elif not trade_alive:
                action = "avoid" if state in ("fade_confirmed", "dead") else "observe_only"
            elif state == "fade_watch":
                action = "observe_only"
            elif entry == "reject":
                action = "observe_only"

            alignment = {
                "active_mainline": True,
                "mainline_id": mid,
                "mainline_name": str(ml.get("mainline_name", "")),
                "lifecycle_state": state,
                "mainline_trade_alive": trade_alive,
                "in_layer_c": True,
                "layer_c_level": entry,
                "is_d1_candidate": is_d1,
                "d1_level": d1_level,
                "is_focus_stock": is_focus,
                "trade_action": action,
                "evidence_role": (
                    "focus_stock" if is_focus
                    else "d1_candidate" if is_d1
                    else "layer_c_tracking" if entry != "reject"
                    else "tracking_only"
                ),
            }
            if sid:
                by_stock[sid] = alignment

        if d1_subjects:
            for sk in d1_subjects:
                if sk not in by_subject:
                    ml_match = None
                    for m in mainline_states:
                        aks = m.get("active_subject_keys", [])
                        if sk in aks:
                            ml_match = m
                            break
                    by_subject[sk] = {
                        "active_mainline": bool(ml_match),
                        "mainline_id": str(ml_match.get("mainline_id", "")) if ml_match else "",
                        "mainline_name": str(ml_match.get("mainline_name", "")) if ml_match else "",
                        "lifecycle_state": str(ml_match.get("lifecycle_state", "unknown")) if ml_match else "unknown",
                        "trade_alive": bool(ml_match.get("mainline_trade_alive", False)) if ml_match else False,
                        "has_d1": True,
                        "evidence_role": "d1",
                    }

        return {
            "by_stock": by_stock,
            "by_subject": by_subject,
            "indexed_stocks": len(by_stock),
            "indexed_subjects": len(by_subject),
        }

    def _mainline_conclusion(self, lr: dict) -> str:
        state = str(lr.get("lifecycle_state", ""))
        trade_alive = bool(lr.get("mainline_trade_alive", False))
        if not trade_alive:
            return "不可交易"
        if state == "fade_watch":
            return "退潮观察，等待修复信号"
        if state == "divergence":
            return "分歧阶段，关注龙头和修复"
        if state == "repair":
            return "修复中，可参与核心弱转强"
        if state in ("fermentation", "acceleration"):
            return "主线发酵，积极参与核心"
        if state == "start":
            return "启动阶段，观察龙头确认"
        return "未知"
