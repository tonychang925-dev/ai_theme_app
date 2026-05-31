"""PR-11G: TradingPermissionEngine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import (
    BroadMarketRegimeReview, ShortTermSentimentReview,
    MainlineEnvironmentReview, TradingPermissionReview,
)


@dataclass
class TradingPermissionEngine:
    def build(
        self, *,
        broad: BroadMarketRegimeReview,
        sentiment: ShortTermSentimentReview,
        mainline: MainlineEnvironmentReview,
    ) -> TradingPermissionReview:
        reasons: list[str] = []
        notes: list[str] = []
        allowed: list[str] = []
        forbidden: list[str] = []

        bm = broad.broad_market_regime
        st = sentiment.short_term_sentiment
        me = mainline.mainline_environment

        # ── no confirmed mainline ──
        if me == "no_confirmed_mainline":
            return TradingPermissionReview(allow_trade=False, trade_mode="no_trade",
                position_limit=0.0, no_trade_reasons=["无人工确认主线"],
                risk_notes=["当天无确认主线，等待人工确认"])

        # ── fading ──
        if me in {"mainline_fading"}:
            return TradingPermissionReview(allow_trade=False, trade_mode="no_trade",
                position_limit=0.0, no_trade_reasons=["确认主线已进入退潮或风险关闭"],
                risk_notes=["主线 fading，不参与"])

        # ── crash / bearish ──
        if bm in {"bearish_adverse", "crash_risk"}:
            return TradingPermissionReview(allow_trade=False, trade_mode="no_trade",
                position_limit=0.0, no_trade_reasons=[f"大盘环境={bm}，不支持交易"],
                risk_notes=notes)

        # ── sentiment dead ──
        if st == "dead":
            return TradingPermissionReview(allow_trade=False, trade_mode="no_trade",
                position_limit=0.0, no_trade_reasons=["短线情绪死亡"],
                risk_notes=["情绪冰点，不交易"])

        # ── watch only ──
        if me == "mainline_watch_only":
            return TradingPermissionReview(allow_trade=False, trade_mode="no_trade",
                position_limit=0.0, no_trade_reasons=["主线仅观察级"],
                risk_notes=["等待观察升级后再评估"])

        # ── downtrend rebound ──
        if bm == "downtrend_rebound":
            allowed = ["主线核心超短确认", "只看龙头/龙二承接"]
            forbidden = ["非主线追涨", "后排套利", "高位一致接力", "弱转强追买"]
            notes.append("大盘处于下降通道反抽，只允许核心超短")
            return TradingPermissionReview(allow_trade=True, trade_mode="ultra_short_only",
                position_limit=0.2, allowed_actions=allowed, forbidden_actions=forbidden,
                no_trade_reasons=[], risk_notes=notes)

        # ── sentiment retreat ──
        if st == "retreat":
            allowed = ["只允许核心前排观察"]
            forbidden = ["开新仓", "追涨", "套利"]
            notes.append("短线情绪退潮，需极度保守")
            return TradingPermissionReview(allow_trade=True, trade_mode="ultra_short_only",
                position_limit=0.15, allowed_actions=allowed, forbidden_actions=forbidden,
                no_trade_reasons=[], risk_notes=notes)

        # ── neutral choppy ──
        if bm == "neutral_choppy":
            allowed = ["主线核心", "核心弱转强", "前排分歧低吸"]
            forbidden = ["非主线追涨", "后排套利", "高位一致接力"]
            return TradingPermissionReview(allow_trade=True, trade_mode="mainline_core_only",
                position_limit=0.3, allowed_actions=allowed, forbidden_actions=forbidden,
                no_trade_reasons=[], risk_notes=notes)

        # ── bullish / normal default ──
        allowed = ["主线龙头", "龙二卡位", "主线核心弱转强", "前排分歧低吸"]
        forbidden = ["非主线杂毛追涨"]
        return TradingPermissionReview(allow_trade=True, trade_mode="mainline_active",
            position_limit=0.5, allowed_actions=allowed, forbidden_actions=forbidden,
            no_trade_reasons=[], risk_notes=["默认主做主线核心前排"])
