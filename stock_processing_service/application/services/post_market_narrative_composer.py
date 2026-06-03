from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class MarketOverviewNarrative:
    headline: str
    core_points: list[str]
    market_state_summary: str
    index_summary: str
    sentiment_summary: str
    hotspot_summary: str
    risk_warning: str
    next_day_strategy: str
    source: str = "engine_template"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class MarketHotspotNarrative:
    headline: str
    core_points: list[str]
    strongest_themes: list[dict[str, Any]]
    rotation_themes: list[str]
    risk_themes: list[str]
    market_heat_summary: str
    next_day_focus: str
    source: str = "engine_template"
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class PostMarketNarrativeComposer:
    """把引擎字段转成可读的复盘开篇文案。

    只做解释，不做决策；所有交易判断仍来源于 engine_summary / market_regime_review / PDV2。
    """

    def compose_market_overview(
        self,
        *,
        engine_summary: dict[str, Any] | None,
        market_regime_review: dict[str, Any] | None,
        index_technical_reviews: list[dict[str, Any]] | None,
        mainline_daily_states: list[dict[str, Any]] | None,
        post_market_decision_v2: dict[str, Any] | None,
        market_overview_review: dict[str, Any] | None,
        market_summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        engine_summary = engine_summary or {}
        market_regime_review = market_regime_review or {}
        index_reviews = [row for row in (index_technical_reviews or []) if isinstance(row, dict)]
        mainlines = [row for row in (mainline_daily_states or []) if isinstance(row, dict)]
        pdv2 = post_market_decision_v2 or {}
        market_overview_review = market_overview_review or {}
        market_summary = market_summary or {}

        allow_trade = bool(engine_summary.get("allow_trade"))
        trade_mode = str(engine_summary.get("trade_mode") or market_regime_review.get("trade_mode") or "no_trade")
        d1_count = self._count_rows(pdv2.get("weak_to_strong_d1_reviews"))
        focus_count = self._count_rows(pdv2.get("next_day_focus_stocks"))
        mainline_count = len(mainlines)
        divergence_count, fade_count, watch_count = self._mainline_bucket_counts(mainlines)

        market_state_summary = self._market_state_summary(engine_summary, market_regime_review)
        index_summary = self._index_summary(index_reviews, market_regime_review)
        sentiment_summary = self._sentiment_summary(engine_summary, market_regime_review, market_summary)
        hotspot_summary = self._hotspot_summary(market_overview_review, mainlines, market_summary)
        risk_warning = self._risk_warning(engine_summary, market_regime_review, market_summary)
        next_day_strategy = self._next_day_strategy(engine_summary, market_regime_review, d1_count, focus_count)
        headline = self._headline(allow_trade, trade_mode, risk_warning, next_day_strategy)
        core_points = self._core_points(
            market_state_summary=market_state_summary,
            index_summary=index_summary,
            sentiment_summary=sentiment_summary,
            hotspot_summary=hotspot_summary,
            risk_warning=risk_warning,
            d1_count=d1_count,
            focus_count=focus_count,
            mainline_count=mainline_count,
            divergence_count=divergence_count,
            fade_count=fade_count,
            watch_count=watch_count,
        )

        source = "engine_template"
        if not (engine_summary or market_regime_review or index_reviews or mainlines or pdv2 or market_overview_review):
            source = "legacy_fallback"
        elif market_summary.get("diagnostics") and not engine_summary:
            source = "legacy_fallback"

        diagnostics = {
            "allow_trade": allow_trade,
            "trade_mode": trade_mode,
            "d1_count": d1_count,
            "focus_count": focus_count,
            "mainline_count": mainline_count,
            "divergence_count": divergence_count,
            "fade_count": fade_count,
            "watch_count": watch_count,
            "index_count": len(index_reviews),
            "hotspot_count": len((market_overview_review.get("theme_limitup_matrix") or {}).get("columns") or []),
        }

        return MarketOverviewNarrative(
            headline=headline,
            core_points=core_points,
            market_state_summary=market_state_summary,
            index_summary=index_summary,
            sentiment_summary=sentiment_summary,
            hotspot_summary=hotspot_summary,
            risk_warning=risk_warning,
            next_day_strategy=next_day_strategy,
            source=source,
            diagnostics=diagnostics,
        ).to_dict()

    def compose_market_hotspot(
        self,
        *,
        market_overview_review: dict[str, Any] | None,
        market_summary: dict[str, Any] | None,
        market_regime_review: dict[str, Any] | None,
        mainline_daily_states: list[dict[str, Any]] | None,
        engine_summary: dict[str, Any] | None,
        post_market_decision_v2: dict[str, Any] | None,
    ) -> dict[str, Any]:
        market_overview_review = market_overview_review or {}
        market_summary = market_summary or {}
        market_regime_review = market_regime_review or {}
        mainlines = [row for row in (mainline_daily_states or []) if isinstance(row, dict)]
        engine_summary = engine_summary or {}
        pdv2 = post_market_decision_v2 or {}

        matrix = market_overview_review.get("theme_limitup_matrix") if isinstance(market_overview_review.get("theme_limitup_matrix"), dict) else {}
        columns = [row for row in (matrix.get("columns") or []) if isinstance(row, dict)]
        columns.sort(
            key=lambda row: (
                -int(row.get("limit_up_count") or 0),
                0 if row.get("active_mainline") else 1,
                str(row.get("theme_name") or row.get("subject_key") or ""),
            )
        )

        strongest_themes: list[dict[str, Any]] = []
        rotation_themes: list[str] = []
        risk_themes: list[str] = []
        for row in columns[:6]:
            theme_name = self._clean_text(row.get("theme_name") or row.get("subject_key") or "题材")
            theme_item = {
                "theme_name": theme_name,
                "subject_key": self._clean_text(row.get("subject_key"), ""),
                "limit_up_count": int(row.get("limit_up_count") or 0),
                "active_mainline": bool(row.get("active_mainline")),
                "lifecycle_state": self._clean_text(row.get("lifecycle_state"), ""),
                "trade_action": self._clean_text(row.get("trade_action"), ""),
            }
            strongest_themes.append(theme_item)
            lifecycle = theme_item["lifecycle_state"].lower()
            action = theme_item["trade_action"]
            if not theme_item["active_mainline"] or action in {"轮动观察", "观察"}:
                rotation_themes.append(theme_name)
            if action in {"回避", "谨慎"} or lifecycle in {"fade", "fade_watch", "fade_confirmed"}:
                risk_themes.append(theme_name)

        top_names = [item["theme_name"] for item in strongest_themes[:3] if item.get("theme_name")]
        mainline_names = [
            self._clean_text(row.get("mainline_name") or row.get("canonical_subject_key") or "主线")
            for row in sorted(
                mainlines,
                key=lambda row: (
                    -float(row.get("mainline_strength_score") or 0),
                    -float(row.get("strong_pool_count") or 0),
                    str(row.get("mainline_name") or ""),
                ),
            )[:3]
        ]
        limit_up_total = int(market_overview_review.get("limit_up_total") or 0)
        theme_count = int((matrix.get("columns") and len(matrix.get("columns"))) or len(columns))
        active_mainline_count = sum(1 for row in columns if row.get("active_mainline"))
        d1_count = self._count_rows((pdv2 or {}).get("weak_to_strong_d1_reviews"))
        focus_count = self._count_rows((pdv2 or {}).get("next_day_focus_stocks"))

        allow_trade = bool(engine_summary.get("allow_trade"))
        trade_mode = self._clean_text(engine_summary.get("trade_mode") or market_regime_review.get("trade_mode"), "no_trade")
        headline = self._hotspot_headline(
            allow_trade=allow_trade,
            trade_mode=trade_mode,
            top_names=top_names,
            mainline_names=mainline_names,
        )
        market_heat_summary = self._hotspot_market_heat_summary(
            limit_up_total=limit_up_total,
            theme_count=theme_count,
            active_mainline_count=active_mainline_count,
            rotation_themes=rotation_themes,
            risk_themes=risk_themes,
        )
        core_points = [
            f"今日题材涨停总数 {limit_up_total}，热点题材数 {theme_count} 个，活跃主线 {active_mainline_count} 条。",
            f"强势题材集中在 {self._join_text(top_names[:3], '、') or '暂无明确热点聚焦'}。",
            f"轮动/观察题材包括 {self._join_text(rotation_themes[:3], '、') or '暂无'}。",
        ]
        if risk_themes:
            core_points.append(f"风险/退潮题材包括 {self._join_text(risk_themes[:3], '、') }。")
        if d1_count > 0:
            core_points.append(f"D1 候选 {d1_count} 只，focus {focus_count} 只。")
        if mainline_names:
            core_points.append(f"主线联动方向包括 {self._join_text(mainline_names[:3], '、')}。")
        next_day_focus = self._hotspot_next_day_focus(
            allow_trade=allow_trade,
            trade_mode=trade_mode,
            top_names=top_names,
            risk_themes=risk_themes,
        )

        source = "engine_template"
        if not (columns or mainlines or market_summary or market_overview_review):
            source = "legacy_fallback"

        diagnostics = {
            "limit_up_total": limit_up_total,
            "theme_count": theme_count,
            "active_mainline_count": active_mainline_count,
            "d1_count": d1_count,
            "focus_count": focus_count,
            "strongest_theme_count": len(strongest_themes),
        }
        return MarketHotspotNarrative(
            headline=headline,
            core_points=core_points[:5],
            strongest_themes=strongest_themes,
            rotation_themes=rotation_themes[:5],
            risk_themes=risk_themes[:5],
            market_heat_summary=market_heat_summary,
            next_day_focus=next_day_focus,
            source=source,
            diagnostics=diagnostics,
        ).to_dict()

    def compose_mainline_narrative(
        self,
        *,
        mainline_daily_states: list[dict[str, Any]] | None,
        market_regime_review: dict[str, Any] | None,
        engine_summary: dict[str, Any] | None,
        post_market_decision_v2: dict[str, Any] | None,
    ) -> dict[str, Any]:
        mainlines = [row for row in (mainline_daily_states or []) if isinstance(row, dict)]
        market_regime_review = market_regime_review or {}
        engine_summary = engine_summary or {}
        pdv2 = post_market_decision_v2 or {}

        divergence_mainlines: list[str] = []
        fade_mainlines: list[str] = []
        watch_only_mainlines: list[str] = []
        for row in sorted(
            mainlines,
            key=lambda row: (
                -float(row.get("mainline_strength_score") or 0),
                -float(row.get("strong_pool_count") or 0),
                str(row.get("mainline_name") or ""),
            ),
        ):
            name = self._clean_text(row.get("mainline_name") or row.get("canonical_subject_key") or "主线")
            lifecycle = str(row.get("lifecycle_state") or "").strip().lower()
            action = str(row.get("action_advice") or "").strip()
            if self._is_mainline_fade(lifecycle, action):
                fade_mainlines.append(name)
            elif self._is_mainline_divergence(lifecycle, action):
                divergence_mainlines.append(name)
            else:
                watch_only_mainlines.append(name)

        divergence_mainlines = self._unique_names(divergence_mainlines)
        fade_mainlines = self._unique_names(fade_mainlines)
        watch_only_mainlines = self._unique_names(watch_only_mainlines)

        headline_parts: list[str] = []
        if divergence_mainlines:
            headline_parts.append(f"{self._join_text(divergence_mainlines[:3], '、')}处于分歧阶段")
        if fade_mainlines:
            headline_parts.append(f"{self._join_text(fade_mainlines[:3], '、')}偏退潮")
        if watch_only_mainlines:
            headline_parts.append(f"{self._join_text(watch_only_mainlines[:3], '、')}以观察为主")

        allow_trade = bool(engine_summary.get("allow_trade"))
        trade_mode = self._clean_text(engine_summary.get("trade_mode") or market_regime_review.get("trade_mode"), "no_trade")
        if headline_parts:
            summary = "；".join(headline_parts) + "。"
        elif mainlines:
            summary = "主线结构已识别，但当前仍需结合资金回流和修复确认。"
        else:
            summary = "当前主线信息不足，先按市场总闸门观察。"

        if not allow_trade or trade_mode == "no_trade":
            action_summary = "市场环境不支持主动进攻，主线只做分歧修复与回流观察。"
        elif trade_mode in {"mainline_core_only", "mainline_tradable"}:
            action_summary = "围绕已确认主线核心参与，优先跟随修复和前排节奏。"
        elif trade_mode == "ultra_short_only":
            action_summary = "仅做超短试探，主线方向等待竞价和盘中确认。"
        else:
            action_summary = "主线与轮动并行观察，优先等待更清晰的资金确认。"

        core_points = [
            f"已识别主线 {len(mainlines)} 条，其中分歧 {len(divergence_mainlines)} 条、退潮 {len(fade_mainlines)} 条、观察 {len(watch_only_mainlines)} 条。",
            f"分歧主线关注 {self._join_text(divergence_mainlines[:3], '、') or '暂无'}。",
            f"退潮主线关注 {self._join_text(fade_mainlines[:3], '、') or '暂无'}。",
            f"观察主线关注 {self._join_text(watch_only_mainlines[:3], '、') or '暂无'}。",
        ]
        diagnostics = {
            "mainline_count": len(mainlines),
            "divergence_count": len(divergence_mainlines),
            "fade_count": len(fade_mainlines),
            "watch_only_count": len(watch_only_mainlines),
            "allow_trade": allow_trade,
            "trade_mode": trade_mode,
            "d1_count": self._count_rows(pdv2.get("weak_to_strong_d1_reviews")),
            "focus_count": self._count_rows(pdv2.get("next_day_focus_stocks")),
        }
        source = "engine_template" if mainlines else "fallback"
        return {
            "summary": summary,
            "core_points": core_points,
            "divergence_mainlines": divergence_mainlines,
            "fade_mainlines": fade_mainlines,
            "watch_only_mainlines": watch_only_mainlines,
            "action_summary": action_summary,
            "source": source,
            "diagnostics": diagnostics,
        }

    def compose_d1_narrative(
        self,
        *,
        engine_summary: dict[str, Any] | None,
        market_regime_review: dict[str, Any] | None,
        post_market_decision_v2: dict[str, Any] | None,
    ) -> dict[str, Any]:
        engine_summary = engine_summary or {}
        market_regime_review = market_regime_review or {}
        pdv2 = post_market_decision_v2 or {}

        d1_reviews = self._as_list(pdv2.get("weak_to_strong_d1_reviews"))
        focus_stocks = self._as_list(pdv2.get("next_day_focus_stocks"))
        candidate_count = len(d1_reviews)
        formal_count = len(focus_stocks)
        observe_count = max(candidate_count - formal_count, 0)
        allow_trade = bool(engine_summary.get("allow_trade"))
        trade_mode = self._clean_text(engine_summary.get("trade_mode") or market_regime_review.get("trade_mode"), "no_trade")

        if candidate_count > 0 and formal_count == 0:
            summary = f"弱转强模型筛出 {candidate_count} 只 D1 候选，但由于市场环境处于 {trade_mode}，全部降级为观察，不生成正式 focus。"
        elif formal_count > 0:
            summary = f"弱转强模型筛出 {candidate_count} 只 D1 候选，其中 {formal_count} 只进入次日重点确认。"
        elif candidate_count > 0:
            summary = f"弱转强模型筛出 {candidate_count} 只 D1 候选，当前先纳入观察池。"
        else:
            summary = "当前未形成可用的 D1 候选，继续等待盘后与次日确认。"

        if not allow_trade or trade_mode == "no_trade":
            confirmation_requirements = [
                "指数修复后再看承接强度",
                "主线资金回流并完成修复确认",
                "个股竞价承接达标且盘中不再快速转弱",
            ]
            invalid_conditions = [
                "指数继续走弱",
                "主线修复失败或资金不回流",
                "个股竞价承接不足或盘中跌破关键支撑",
            ]
            risk_warning = "当前市场环境不支持主动交易，D1 仅作为次日观察清单。"
        elif trade_mode in {"mainline_core_only", "mainline_tradable"}:
            confirmation_requirements = [
                "主线核心方向保持强度",
                "前排个股竞价和开盘承接不弱于预期",
                "盘中资金不从主线快速外溢",
            ]
            invalid_conditions = [
                "主线核心快速转弱",
                "前排个股开盘即失去承接",
                "热点切换过快导致模型失效",
            ]
            risk_warning = "当前可参与，但必须围绕主线核心执行，避免追高失真。"
        else:
            confirmation_requirements = [
                "竞价承接强于昨日",
                "盘中放量但不破关键支撑",
                "主线方向出现资金回流",
            ]
            invalid_conditions = [
                "竞价显著低于预期",
                "盘中直接失去承接",
                "主线资金快速退潮",
            ]
            risk_warning = "D1 仅适合在资金确认后跟随，避免把观察候选误作正式机会。"

        diagnostics = {
            "allow_trade": allow_trade,
            "trade_mode": trade_mode,
            "d1_count": candidate_count,
            "focus_count": formal_count,
            "observe_count": observe_count,
        }
        source = "engine_template" if (engine_summary or market_regime_review or pdv2) else "fallback"
        return {
            "summary": summary,
            "candidate_count": candidate_count,
            "focus_count": formal_count,
            "formal_count": formal_count,
            "observe_count": observe_count,
            "confirmation_requirements": confirmation_requirements,
            "invalid_conditions": invalid_conditions,
            "risk_warning": risk_warning,
            "source": source,
            "diagnostics": diagnostics,
        }

    @staticmethod
    def _clean_text(value: Any, default: str = "--") -> str:
        text = str(value or "").strip()
        return text or default

    @staticmethod
    def _join_text(values: list[Any], sep: str = "；") -> str:
        items = [str(item).strip() for item in values if str(item).strip()]
        return sep.join(items)

    @staticmethod
    def _count_rows(value: Any) -> int:
        return len(value) if isinstance(value, list) else 0

    @staticmethod
    def _safe_num(value: Any) -> float | None:
        try:
            if value in (None, ""):
                return None
            return float(value)
        except Exception:
            return None

    def _headline(
        self,
        allow_trade: bool,
        trade_mode: str,
        risk_warning: str,
        next_day_strategy: str,
    ) -> str:
        if not allow_trade:
            return "市场环境偏弱，当前不支持主动交易，以观察为主。"
        if trade_mode in {"mainline_core_only", "mainline_tradable"}:
            return "市场环境可参与，但需要围绕主线与热点节奏执行。"
        if "观察" in next_day_strategy:
            return "市场信号尚不充分，先观察主线修复与确认。"
        if risk_warning and risk_warning != "--":
            return f"市场环境仍需控制风险，{risk_warning}"
        return "市场状态可读，但仍需结合盘中修复节奏决定参与方式。"

    def _core_points(
        self,
        *,
        market_state_summary: str,
        index_summary: str,
        sentiment_summary: str,
        hotspot_summary: str,
        risk_warning: str,
        d1_count: int,
        focus_count: int,
        mainline_count: int,
        divergence_count: int,
        fade_count: int,
        watch_count: int,
    ) -> list[str]:
        points: list[str] = [market_state_summary, index_summary, sentiment_summary, hotspot_summary]
        if d1_count > 0:
            if focus_count > 0:
                points.append(f"弱转强模型筛出 {d1_count} 只 D1 候选，其中 {focus_count} 只进入次日重点观察。")
            else:
                points.append(f"弱转强模型筛出 {d1_count} 只 D1 候选，但全部停留在观察池，未生成正式 focus。")
        if mainline_count > 0:
            points.append(
                f"已识别 {mainline_count} 条主线状态，其中分歧 {divergence_count} 条、退潮 {fade_count} 条、观察 {watch_count} 条。"
            )
        if risk_warning and risk_warning != "--":
            points.append(f"风险提示：{risk_warning}")
        deduped: list[str] = []
        for item in points:
            cleaned = self._clean_text(item)
            if cleaned != "--" and cleaned not in deduped:
                deduped.append(cleaned)
        return deduped[:5]

    def _market_state_summary(self, engine_summary: dict[str, Any], market_regime_review: dict[str, Any]) -> str:
        allow_trade = bool(engine_summary.get("allow_trade"))
        trade_mode = self._clean_text(engine_summary.get("trade_mode") or market_regime_review.get("trade_mode"))
        broad = self._clean_text(market_regime_review.get("broad_market_regime"))
        short_term = self._clean_text(market_regime_review.get("short_term_sentiment"))
        mainline = self._clean_text(market_regime_review.get("mainline_environment"))
        blocking = self._clean_text(
            engine_summary.get("no_trade_blocking_rule") or market_regime_review.get("no_trade_blocking_rule"),
            "",
        )
        action = "允许交易" if allow_trade else "不支持主动交易"
        tail = f"；阻断规则 {blocking}" if not allow_trade and blocking else ""
        return f"市场状态：{broad}，短线情绪 {short_term}，主线环境 {mainline}，交易模式 {trade_mode}，当前{action}{tail}。"

    def _index_summary(self, index_reviews: list[dict[str, Any]], market_regime_review: dict[str, Any]) -> str:
        if not index_reviews:
            if market_regime_review.get("index_data_ready"):
                return "指数数据已就绪，但当前缺少可展示的指数技术细节。"
            return "指数数据暂缺，先按市场总闸门判断。"

        parts: list[str] = []
        for row in index_reviews[:3]:
            name = self._clean_text(row.get("index_name") or row.get("index_code") or "指数")
            trend = self._translate_trend(row.get("trend_state"))
            support = self._price_or_dash(row.get("nearest_support_level") or row.get("support_level"))
            resistance = self._price_or_dash(row.get("nearest_resistance_level") or row.get("resistance_level"))
            hint = self._clean_text(row.get("index_trade_hint"), "")
            parts.append(
                f"{name}{trend}，支撑 {support}，压力 {resistance}{('，' + hint) if hint and hint != '--' else ''}"
            )
        return "；".join(parts)

    def _sentiment_summary(
        self,
        engine_summary: dict[str, Any],
        market_regime_review: dict[str, Any],
        market_summary: dict[str, Any],
    ) -> str:
        market_bias = self._clean_text(market_summary.get("market_bias"), "")
        action_bias = self._clean_text(engine_summary.get("action_bias") or market_summary.get("action_bias"), "")
        breadth = self._clean_text(market_summary.get("breadth_status"), "")
        short_term = self._clean_text(market_summary.get("short_term_sentiment_status") or market_regime_review.get("short_term_sentiment"), "")
        relay = self._clean_text(market_summary.get("relay_sentiment_status"), "")
        fade = self._clean_text(market_summary.get("intraday_fade_status"), "")
        highlights = market_summary.get("highlights") if isinstance(market_summary.get("highlights"), list) else []
        risk_flags = market_summary.get("risk_flags") if isinstance(market_summary.get("risk_flags"), list) else []
        pieces = [
            f"市场定性 {market_bias}" if market_bias else "",
            f"操作倾向 {action_bias}" if action_bias else "",
            f"宽度 {breadth}" if breadth else "",
            f"短线情绪 {short_term}" if short_term else "",
            f"接力情绪 {relay}" if relay else "",
            f"日内退潮 {fade}" if fade else "",
        ]
        if highlights:
            pieces.append(f"核心摘要 {self._join_text(highlights[:2])}")
        if risk_flags:
            pieces.append(f"风险信号 {self._join_text(risk_flags[:2])}")
        parts = [piece for piece in pieces if piece]
        if parts:
            return "；".join(parts) + "。"
        return f"短线情绪 {self._clean_text(market_regime_review.get('short_term_sentiment'))}，市场状态由当前引擎闸门决定。"

    def _hotspot_summary(
        self,
        market_overview_review: dict[str, Any],
        mainlines: list[dict[str, Any]],
        market_summary: dict[str, Any],
    ) -> str:
        matrix = market_overview_review.get("theme_limitup_matrix") if isinstance(market_overview_review.get("theme_limitup_matrix"), dict) else {}
        columns = matrix.get("columns") if isinstance(matrix.get("columns"), list) else []
        if columns:
            ranked = sorted(
                [row for row in columns if isinstance(row, dict)],
                key=lambda row: (
                    -int(row.get("limit_up_count") or 0),
                    0 if row.get("active_mainline") else 1,
                    str(row.get("theme_name") or ""),
                ),
            )[:3]
            theme_parts: list[str] = []
            for row in ranked:
                theme = self._clean_text(row.get("theme_name") or row.get("subject_key") or "题材")
                count = int(row.get("limit_up_count") or 0)
                action = self._clean_text(row.get("trade_action"), "")
                lifecycle = self._clean_text(row.get("lifecycle_state"), "")
                detail = f"{theme} {count} 只涨停"
                if action and action != "--":
                    detail += f"（{action}）"
                if lifecycle and lifecycle != "--":
                    detail += f"，周期 {lifecycle}"
                theme_parts.append(detail)
            return f"今日热点集中在 {self._join_text(theme_parts, '、')}；主线仍需结合分歧修复确认。"

        if mainlines:
            top_mainlines = sorted(
                mainlines,
                key=lambda row: (
                    -float(row.get("mainline_strength_score") or 0),
                    -float(row.get("strong_pool_count") or 0),
                    str(row.get("mainline_name") or ""),
                ),
            )[:3]
            names = [self._clean_text(row.get("mainline_name") or row.get("canonical_subject_key") or "主线") for row in top_mainlines]
            return f"今日热点围绕 {self._join_text(names, '、')} 展开，当前更偏向观察主线修复而非主动扩张。"

        top_concepts = market_summary.get("mainstream_focus") if isinstance(market_summary.get("mainstream_focus"), list) else []
        if top_concepts:
            return f"今日热点主要集中在 {self._join_text(top_concepts[:3], '、')}。"

        return "今日热点方向暂未形成清晰聚焦，仍以主线修复和资金确认作为观察重点。"

    def _hotspot_headline(
        self,
        *,
        allow_trade: bool,
        trade_mode: str,
        top_names: list[str],
        mainline_names: list[str],
    ) -> str:
        top_text = self._join_text(top_names[:3], "、") or "热点"
        mainline_text = self._join_text(mainline_names[:3], "、")
        if not allow_trade:
            if mainline_text:
                return f"今日热点集中在 {top_text}，但整体仍以主线分歧修复和观察为主。"
            return f"今日热点集中在 {top_text}，但市场整体仍以观察为主。"
        if trade_mode in {"mainline_core_only", "mainline_tradable"}:
            return f"今日热点围绕 {top_text} 展开，需沿主线核心节奏参与。"
        if mainline_text:
            return f"今日热点围绕 {top_text} 展开，主线方向为 {mainline_text}。"
        return f"今日热点围绕 {top_text} 展开，需观察资金是否进一步向主线聚拢。"

    def _hotspot_market_heat_summary(
        self,
        *,
        limit_up_total: int,
        theme_count: int,
        active_mainline_count: int,
        rotation_themes: list[str],
        risk_themes: list[str],
    ) -> str:
        rotation_text = self._join_text(rotation_themes[:3], "、") or "暂无明显轮动主题"
        risk_text = self._join_text(risk_themes[:3], "、") or "暂无明显退潮主题"
        return (
            f"今日涨停 {limit_up_total} 只，热点题材 {theme_count} 个，活跃主线 {active_mainline_count} 条；"
            f"轮动主题 {rotation_text}；风险主题 {risk_text}。"
        )

    def _hotspot_next_day_focus(
        self,
        *,
        allow_trade: bool,
        trade_mode: str,
        top_names: list[str],
        risk_themes: list[str],
    ) -> str:
        focus_text = self._join_text(top_names[:3], "、") or "主线修复"
        risk_text = self._join_text(risk_themes[:2], "、")
        if not allow_trade:
            base = f"继续观察 {focus_text} 的修复持续性，等资金回流与主线确认后再决定是否参与。"
        elif trade_mode in {"mainline_core_only", "mainline_tradable"}:
            base = f"围绕 {focus_text} 的主线核心和前排节奏执行。"
        else:
            base = f"继续观察 {focus_text} 的资金延续与轮动强度。"
        if risk_text:
            return f"{base} 同时回避 {risk_text} 等退潮/风险主题。"
        return base

    def _risk_warning(
        self,
        engine_summary: dict[str, Any],
        market_regime_review: dict[str, Any],
        market_summary: dict[str, Any],
    ) -> str:
        risk_notes: list[str] = []
        risk_notes.extend(self._as_list(engine_summary.get("risk_notes")))
        risk_notes.extend(self._as_list(market_regime_review.get("no_trade_reasons")))
        risk_notes.extend(self._as_list(market_summary.get("risk_flags")))
        deduped: list[str] = []
        for item in risk_notes:
            cleaned = self._clean_text(item, "")
            if cleaned and cleaned not in deduped:
                deduped.append(cleaned)
        if deduped:
            return f"风险提示：{self._join_text(deduped[:3])}。"
        blocking = self._clean_text(engine_summary.get("no_trade_blocking_rule") or market_regime_review.get("no_trade_blocking_rule"), "")
        if blocking:
            return f"风险提示：当前阻断规则为 {blocking}。"
        return "风险提示：当前以观察为主，注意盘中修复失败和热点切换。"

    def _next_day_strategy(
        self,
        engine_summary: dict[str, Any],
        market_regime_review: dict[str, Any],
        d1_count: int,
        focus_count: int,
    ) -> str:
        strategy = self._clean_text(engine_summary.get("next_day_strategy"), "")
        if strategy and strategy != "--":
            if d1_count > 0 and focus_count == 0 and "观察" not in strategy:
                return f"{strategy}；D1 候选继续只做观察，不生成正式 focus。"
            return strategy
        if not bool(engine_summary.get("allow_trade")):
            return "不做新开仓，只观察主线是否修复，D1 候选仅进入观察池。"
        mode = self._clean_text(market_regime_review.get("trade_mode"), "normal")
        if mode == "ultra_short_only":
            return "仅做超短试探，严格等待竞价确认。"
        if mode in {"mainline_core_only", "mainline_tradable"}:
            return "聚焦主线核心与确认过的热点，非核心方向暂不追高。"
        return "按主线修复节奏执行，优先观察确认强度再决定参与方式。"

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

    @staticmethod
    def _unique_names(values: list[str]) -> list[str]:
        items: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            items.append(text)
        return items

    @staticmethod
    def _translate_trend(value: Any) -> str:
        key = str(value or "").strip()
        mapping = {
            "bullish_trend": "处于上升趋势",
            "bearish_trend": "处于下降趋势",
            "downtrend_rebound": "处于下跌反弹",
            "neutral_box": "处于震荡箱体",
            "bullish": "偏强",
            "bearish": "偏弱",
            "neutral": "中性",
        }
        return mapping.get(key, key and f"趋势 {key}" or "趋势未知")

    @staticmethod
    def _price_or_dash(value: Any) -> str:
        try:
            if value in (None, ""):
                return "--"
            return f"{float(value):.0f}"
        except Exception:
            return "--"

    def _mainline_bucket_counts(self, rows: list[dict[str, Any]]) -> tuple[int, int, int]:
        divergence = 0
        fade = 0
        watch = 0
        for row in rows:
            lifecycle = str(row.get("lifecycle_state") or "").strip().lower()
            action = str(row.get("action_advice") or "").strip().lower()
            if any(key in lifecycle for key in ("divergence", "repair")) or "分歧" in action:
                divergence += 1
            elif any(key in lifecycle for key in ("fade", "cooling", "down")) or "回避" in action:
                fade += 1
            else:
                watch += 1
        return divergence, fade, watch

    @staticmethod
    def _is_mainline_divergence(lifecycle: str, action: str) -> bool:
        return any(key in lifecycle for key in ("divergence", "repair", "start", "fermentation")) or "分歧" in action

    @staticmethod
    def _is_mainline_fade(lifecycle: str, action: str) -> bool:
        return any(key in lifecycle for key in ("fade", "cooling", "down")) or "回避" in action or "谨慎" in action
