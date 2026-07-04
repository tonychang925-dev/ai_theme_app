from __future__ import annotations

import re
from numbers import Real
from typing import Any

from stock_processing_service.application.services.engine_report_adapter import EngineReportAdapter
from stock_processing_service.publishers.notion_block_builder import NotionBlockBuilder


class PostMarketNotionReportRenderer:
    """Render the DailyReview V2 decision view into Notion blocks.

    Business sections are content-driven. Missing or partial upstream modules
    are consolidated in the final data-quality section instead of producing
    empty headings throughout the report.
    """

    _PLACEHOLDER_PREFIXES = ("暂无", "无结构化", "unknown", "未知", "--")
    _MODULE_LABELS = {
        "theme_reviews": "主线题材",
        "market_summary": "市场摘要",
        "strong_stock_reviews": "强势股",
        "theme_capital_reviews": "题材资金",
        "stock_capital_reviews": "个股资金",
        "money_flow_reviews": "资金行为",
        "dragon_tiger_reviews": "龙虎榜",
    }
    _FIELD_LABELS = {
        "event_score": "事件分",
        "market_score": "市场分",
    }
    _TRADE_MODE_LABELS = {
        "no_trade": "不交易",
        "observe_only": "仅观察",
        "defensive": "防守",
        "normal": "正常交易",
    }
    _BLOCKING_RULE_LABELS = {
        "short_term_sentiment_dead": "短线情绪冰点",
        "broad_market_regime_bearish_adverse": "大盘环境不支持交易",
        "market_risk": "市场风险阻断",
    }
    _BROAD_MARKET_LABELS = {
        "downtrend_rebound": "下跌趋势中的反弹",
        "bearish_adverse": "弱势逆风",
        "range": "区间震荡",
        "uptrend": "上升趋势",
    }
    _SENTIMENT_LABELS = {
        "dead": "情绪冰点",
        "weak": "偏弱",
        "neutral": "中性",
        "strong": "偏强",
    }
    _MAINLINE_ENV_LABELS = {
        "mainline_tradable": "主线具备结构性机会",
        "mainline_weak": "主线偏弱",
        "no_mainline": "无有效主线",
    }
    _LIFECYCLE_LABELS = {
        "start": "启动",
        "divergence": "分歧",
        "acceleration": "加速",
        "fade_watch": "退潮观察",
        "fade_confirmed": "退潮确认",
    }
    _NARRATIVE_CODE_LABELS = {
        **_BLOCKING_RULE_LABELS,
        **_BROAD_MARKET_LABELS,
        **_MAINLINE_ENV_LABELS,
        **_TRADE_MODE_LABELS,
        **_SENTIMENT_LABELS,
        **_LIFECYCLE_LABELS,
    }

    def __init__(self, payload: dict[str, Any], trade_date: str) -> None:
        recap_doc = payload.get("recap_doc")
        if isinstance(recap_doc, dict) and recap_doc:
            self._doc = recap_doc
        elif isinstance(payload, dict) and payload.get("schema_version"):
            self._doc = payload
        else:
            self._doc = {}
        v2 = self._doc.get("daily_review_v2")
        self._v2 = v2 if isinstance(v2, dict) else {}
        theme_name_map = self._value("theme_name_map", {})
        self._theme_name_map = theme_name_map if isinstance(theme_name_map, dict) else {}
        self._render_issues: list[list[str]] = []
        self._adapter = EngineReportAdapter(self._doc)
        self._trade_date = trade_date
        self._B = NotionBlockBuilder

    def build(self) -> list[dict[str, Any]]:
        blocks = [self._B.heading_1(f"{self._trade_date} 盘后复盘")]
        for renderer in (
            self._render_trade_conclusion,
            self._render_market_summary,
            self._render_daily_essentials,
            self._render_market_environment,
            self._render_limit_up_structure,
            self._render_mainline_states,
            self._render_new_highs,
            self._render_capital_validation,
            self._render_core_stocks,
            self._render_next_day_plan,
            self._render_data_quality,
        ):
            section = renderer()
            if section:
                if len(blocks) > 1:
                    blocks.append(self._B.divider())
                blocks.extend(section)
        return blocks

    def _value(self, key: str, default: Any = None) -> Any:
        value = self._doc.get(key)
        if value is None or value == {} or value == []:
            value = self._v2.get(key)
        return default if value is None else value

    @classmethod
    def _text(cls, value: Any) -> str:
        return "" if value is None else str(value).strip()

    @classmethod
    def _meaningful_text(cls, value: Any) -> bool:
        text = cls._text(value)
        return bool(text) and not text.lower().startswith(cls._PLACEHOLDER_PREFIXES)

    @staticmethod
    def _dict_list(value: Any) -> list[dict[str, Any]]:
        return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []

    @staticmethod
    def _number(value: Any, default: float = 0.0) -> float:
        if isinstance(value, bool):
            return default
        if isinstance(value, Real):
            return float(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _money(cls, value: Any) -> str:
        number = cls._number(value)
        absolute = abs(number)
        if absolute >= 100_000_000:
            return f"{number / 100_000_000:.2f}亿"
        if absolute >= 10_000:
            return f"{number / 10_000:.0f}万"
        return f"{number:.0f}"

    @classmethod
    def _display(cls, value: Any, fallback: str = "--") -> str:
        text = cls._text(value)
        return text if text else fallback

    def _human_theme(self, *values: Any, subject_key: Any = "") -> str:
        normalized_subject_key = self._text(subject_key)
        mapped_subject = self._text(
            self._theme_name_map.get(normalized_subject_key)
        )
        if mapped_subject and not mapped_subject.isdigit():
            return mapped_subject
        candidates = [*values, subject_key]
        for value in candidates:
            text = self._text(value)
            if not text:
                continue
            mapped = self._text(self._theme_name_map.get(text))
            if mapped and not mapped.isdigit():
                return mapped
            if not text.isdigit():
                return text
        return "--"

    @classmethod
    def _localized(cls, value: Any, labels: dict[str, str]) -> str:
        text = cls._text(value)
        return labels.get(text, text or "--")

    @classmethod
    def _compact_catalyst(cls, value: Any) -> str:
        text = re.sub(r"\s+", " ", cls._text(value))
        title_match = re.match(r"^【(?:驱动事件：)?([^】]+)】", text)
        if title_match:
            text = title_match.group(1)
        else:
            text = re.split(r"[。；]", text, maxsplit=1)[0]
        text = re.sub(r"（新闻来源：[^）]+）", "", text).strip()
        return text[:77] + "..." if len(text) > 80 else text

    @classmethod
    def _narrative(cls, value: Any) -> str:
        text = cls._text(value)
        for code, label in sorted(
            cls._NARRATIVE_CODE_LABELS.items(),
            key=lambda item: len(item[0]),
            reverse=True,
        ):
            text = re.sub(
                rf"(?<![A-Za-z0-9_]){re.escape(code)}(?![A-Za-z0-9_])",
                label,
                text,
            )
        text = text.replace("短线情绪 情绪冰点", "短线情绪冰点")
        text = text.replace("主线环境 主线具备结构性机会", "主线具备结构性机会")
        text = text.replace("交易模式 不交易", "交易模式为不交易")
        text = text.replace("阻断规则 短线情绪冰点", "阻断原因为短线情绪冰点")
        return text

    def _render_trade_conclusion(self) -> list[dict[str, Any]]:
        engine_summary = self._value("engine_summary", {})
        if not isinstance(engine_summary, dict) or not engine_summary:
            return []

        conclusion = self._adapter.notion_trade_conclusion()
        allow_trade = bool(conclusion.get("allow_trade"))
        position_limit = max(0.0, self._number(conclusion.get("position_limit")))
        blocks = [
            self._B.heading_2("交易结论"),
            self._B.callout(
                f'{"✅ 允许交易" if allow_trade else "🚫 不交易"}'
                f' | 模式：{self._localized(conclusion.get("trade_mode"), self._TRADE_MODE_LABELS)}'
                f" | 仓位上限：{position_limit:.0%}"
                f' | 阻断：{self._localized(conclusion.get("blocking_rule") or "无", self._BLOCKING_RULE_LABELS)}',
                icon="🎯",
            ),
        ]
        if self._meaningful_text(conclusion.get("conclusion")):
            blocks.append(self._B.paragraph(f"结论：{self._text(conclusion['conclusion'])}"))
        reasons = [self._text(item) for item in conclusion.get("reasons") or [] if self._meaningful_text(item)]
        if reasons:
            blocks.append(self._B.paragraph("依据：" + "；".join(reasons[:4])))
        if self._meaningful_text(conclusion.get("next_day_strategy")):
            blocks.append(self._B.paragraph(f"次日策略：{self._text(conclusion['next_day_strategy'])}"))
        return blocks

    def _render_market_summary(self) -> list[dict[str, Any]]:
        summary = self._value("market_summary", {})
        if not isinstance(summary, dict):
            return []
        conclusion = summary.get("conclusion") or summary.get("market_overview")
        highlights = [self._text(item) for item in summary.get("highlights") or [] if self._meaningful_text(item)]
        risks = [self._text(item) for item in summary.get("risk_flags") or summary.get("risk_notes") or [] if self._meaningful_text(item)]
        engine_summary = self._value("engine_summary", {})
        summary_bias = self._text(summary.get("action_bias"))
        conflicts_with_gate = (
            isinstance(engine_summary, dict)
            and bool(engine_summary)
            and not bool(engine_summary.get("allow_trade"))
            and summary_bias not in {"", "防守", "观望", "仅观察", "不交易"}
        )
        if conflicts_with_gate:
            conclusion = ""
            self._render_issues.append(
                ["市场摘要", "结论冲突", "1", "市场摘要与交易结论冲突，已以交易引擎为准"]
            )
        if not self._meaningful_text(conclusion) and not highlights and not risks:
            return []

        blocks = [self._B.heading_2("市场摘要")]
        if self._meaningful_text(conclusion):
            blocks.append(self._B.callout(self._text(conclusion), icon="🧭"))
        for item in highlights[:5]:
            blocks.append(self._B.bullet(item))
        for item in risks[:3]:
            blocks.append(self._B.callout(item, icon="⚠️"))
        return blocks

    def _render_daily_essentials(self) -> list[dict[str, Any]]:
        essentials = self._adapter.notion_daily_recap_essentials()
        if not isinstance(essentials, dict):
            return []
        headline = essentials.get("headline")
        points = [self._text(item) for item in essentials.get("summary_points") or [] if self._meaningful_text(item)]
        strategy = essentials.get("next_day_strategy")
        if not self._meaningful_text(headline) and not points and not self._meaningful_text(strategy):
            return []

        blocks = [self._B.heading_2("今日复盘要点")]
        if self._meaningful_text(headline):
            blocks.append(self._B.callout(self._narrative(headline), icon="📝"))
        for point in points[:5]:
            blocks.append(self._B.bullet(self._narrative(point)))
        if self._meaningful_text(strategy) and not self._value("engine_summary", {}):
            blocks.append(self._B.paragraph(f"次日策略：{self._narrative(strategy)}"))
        return blocks

    def _render_market_environment(self) -> list[dict[str, Any]]:
        environment = self._adapter.notion_market_environment()
        fields = (
            environment.get("broad_market_regime"),
            environment.get("short_term_sentiment"),
            environment.get("mainline_environment"),
        )
        if not any(self._meaningful_text(value) for value in fields):
            return []
        index_ready = bool(environment.get("index_data_ready"))
        index_count = int(environment.get("index_count") or 0)
        raw_environment = self._value("market_regime_review", {})
        explicit_index_ready = (
            raw_environment.get("index_data_ready")
            if isinstance(raw_environment, dict)
            else None
        )
        index_ready = explicit_index_ready if isinstance(explicit_index_ready, bool) else index_count > 0
        return [
            self._B.heading_2("市场环境"),
            self._B.callout(
                f"大盘：{self._localized(fields[0], self._BROAD_MARKET_LABELS)}"
                f" | 情绪：{self._localized(fields[1], self._SENTIMENT_LABELS)}"
                f" | 主线：{self._localized(fields[2], self._MAINLINE_ENV_LABELS)}"
                f" | 指数数据：{'就绪' if index_ready else '缺失'}（{index_count}）",
                icon="📈",
            ),
        ]

    def _render_limit_up_structure(self) -> list[dict[str, Any]]:
        ladder = self._adapter.notion_limit_up_ladder()
        theme_events = self._adapter.notion_limit_up_theme_events()
        board_rows = [
            row
            for row in self._dict_list(ladder.get("board_rows") if isinstance(ladder, dict) else [])
            if int(self._number(row.get("stock_count"))) > 0 or self._dict_list(row.get("stocks"))
        ]
        event_rows = [
            row
            for row in self._dict_list(
                theme_events.get("rows") if isinstance(theme_events, dict) else []
            )
            if self._text(row.get("theme_name")) not in {"", "热", "其他", "未分类", "未知"}
        ]
        ladder_summary = ladder.get("summary") if isinstance(ladder, dict) else None
        event_summary = theme_events.get("summary") if isinstance(theme_events, dict) else None
        if not board_rows and not event_rows and not self._meaningful_text(ladder_summary) and not self._meaningful_text(event_summary):
            return []

        blocks = [self._B.heading_2("涨停结构")]
        if self._meaningful_text(ladder_summary):
            blocks.append(self._B.callout(self._text(ladder_summary), icon="🔥"))
        if board_rows:
            rows = []
            for row in board_rows[:10]:
                stocks = self._dict_list(row.get("stocks"))
                stock_text = " / ".join(
                    self._display(stock.get("stock_name") or stock.get("stock_id"))
                    for stock in stocks[:4]
                )
                themes = " / ".join(
                    dict.fromkeys(
                        self._text(stock.get("theme_name"))
                        for stock in stocks[:4]
                        if self._meaningful_text(stock.get("theme_name"))
                    )
                )
                rows.append(
                    [
                        self._display(row.get("board_label")),
                        self._display(row.get("stock_count"), "0"),
                        stock_text or "--",
                        themes or "--",
                    ]
                )
            blocks.extend(self._B.table(["梯队", "数量", "代表股", "题材"], rows))
        if self._meaningful_text(event_summary):
            blocks.append(self._B.paragraph(self._text(event_summary)))
        if event_rows:
            rows = []
            for row in event_rows[:8]:
                stocks = self._dict_list(row.get("representative_stocks"))
                events = [
                    event
                    for event in self._dict_list(row.get("catalyst_events"))
                    if self._meaningful_text(event.get("match_reason"))
                    or (
                        self._meaningful_text(row.get("theme_name"))
                        and self._text(row.get("theme_name"))
                        in self._text(event.get("summary"))
                        and f"与{self._text(row.get('theme_name'))}无关"
                        not in self._text(event.get("summary"))
                    )
                ]
                rows.append(
                    [
                        self._display(row.get("theme_name")),
                        self._display(row.get("limit_up_count"), "0"),
                        " / ".join(self._display(stock.get("stock_name") or stock.get("stock_id")) for stock in stocks[:3]) or "--",
                        "；".join(
                            compact
                            for event in events[:2]
                            if (compact := self._compact_catalyst(event.get("summary")))
                        )
                        or "--",
                    ]
                )
            blocks.extend(self._B.table(["题材", "涨停数", "代表股", "催化"], rows))
        return blocks

    def _render_mainline_states(self) -> list[dict[str, Any]]:
        mainlines = self._dict_list(self._adapter.notion_mainline_states())
        if not mainlines:
            theme_reviews = self._dict_list(self._value("theme_reviews", []))
            mainlines = [
                {
                    "mainline_name": row.get("theme_name"),
                    "lifecycle_state": row.get("final_cycle_state") or row.get("theme_stage"),
                    "mainline_trade_alive": row.get("final_mainline_alive"),
                    "strong_pool_count": len(self._dict_list(row.get("leader_stocks"))),
                    "action_advice": row.get("action_advice"),
                    "conclusion": row.get("conclusion"),
                }
                for row in theme_reviews
            ]
        matrix = self._value("limit_up_theme_matrix", {})
        matrix_columns = self._dict_list(
            matrix.get("columns") if isinstance(matrix, dict) else []
        )
        active_keys = {
            self._text(row.get("subject_key"))
            for row in matrix_columns
            if row.get("active_mainline") and self._meaningful_text(row.get("subject_key"))
        }
        active_names = {
            self._text(row.get("theme_name"))
            for row in matrix_columns
            if row.get("active_mainline") and self._meaningful_text(row.get("theme_name"))
        }
        mainlines = [
            row
            for row in mainlines
            if any(
                int(self._number(row.get(field))) > 0
                for field in ("strong_pool_count", "d1_count", "focus_count")
            )
            and (
                not matrix_columns
                or self._text(
                    row.get("canonical_subject_key") or row.get("subject_key")
                )
                in active_keys
                or self._text(row.get("mainline_name") or row.get("theme_name"))
                in active_names
            )
        ]
        if not mainlines:
            return []

        engine_summary = self._value("engine_summary", {})
        global_trade_allowed = not (
            isinstance(engine_summary, dict)
            and engine_summary
            and not bool(engine_summary.get("allow_trade"))
        )
        rows = []
        for row in mainlines[:15]:
            rows.append(
                [
                    self._display(row.get("mainline_name") or row.get("theme_name")),
                    self._localized(
                        row.get("lifecycle_state") or row.get("final_cycle_state"),
                        self._LIFECYCLE_LABELS,
                    ),
                    (
                        "可交易"
                        if global_trade_allowed and row.get("mainline_trade_alive")
                        else "仅观察"
                    ),
                    self._display(row.get("strong_pool_count"), "0"),
                    (
                        self._display(row.get("action_advice") or row.get("conclusion"))
                        if global_trade_allowed
                        else "等待解除全局交易阻断"
                    ),
                ]
            )
        return [self._B.heading_2("主线状态"), *self._B.table(["主线", "周期", "状态", "强股池", "建议"], rows)]

    def _render_new_highs(self) -> list[dict[str, Any]]:
        summary = self._adapter.notion_new_high_summary()
        if not isinstance(summary, dict):
            return []
        raw_industries = self._dict_list(summary.get("industry_summary"))
        industries = [
            row
            for row in raw_industries
            if self._text(row.get("industry_name")) not in {"", "未分类", "未知"}
        ]
        representatives = self._dict_list(summary.get("representative_stocks"))
        today_count = int(self._number(summary.get("today_count")))
        summary_text = summary.get("summary")
        if len(industries) != len(raw_industries):
            industry_names = [
                self._text(row.get("industry_name"))
                for row in industries[:3]
                if self._meaningful_text(row.get("industry_name"))
            ]
            stock_names = [
                self._text(row.get("stock_name") or row.get("stock_id"))
                for row in representatives[:4]
                if self._meaningful_text(row.get("stock_name") or row.get("stock_id"))
            ]
            parts = [f"今日创新高 {today_count} 家"]
            if industry_names:
                parts.append(f"已分类行业集中在 {'、'.join(industry_names)}")
            if stock_names:
                parts.append(f"代表股 {'、'.join(stock_names)}")
            summary_text = "；".join(parts) + "。"
        if not industries and not representatives and today_count <= 0 and not self._meaningful_text(summary_text):
            return []

        blocks = [self._B.heading_2("创新高与行业趋势")]
        if self._meaningful_text(summary_text):
            blocks.append(self._B.callout(self._text(summary_text), icon="📊"))
        if industries:
            rows = []
            for row in industries[:8]:
                stocks = self._dict_list(row.get("representative_stocks"))
                rows.append(
                    [
                        self._display(row.get("industry_name")),
                        self._display(row.get("count"), "0"),
                        " / ".join(self._display(stock.get("stock_name") or stock.get("stock_id")) for stock in stocks[:3]) or "--",
                    ]
                )
            blocks.extend(self._B.table(["行业", "数量", "代表股"], rows))
        return blocks

    def _render_capital_validation(self) -> list[dict[str, Any]]:
        seat = self._adapter.notion_seat_money_summary()
        seat = seat if isinstance(seat, dict) else {}
        institution_buys = self._dict_list(seat.get("institution_top_buys"))
        institution_sells = self._dict_list(seat.get("institution_top_sells"))
        hot_money_buys = self._dict_list(seat.get("hot_money_top_buys"))
        hot_money_sells = self._dict_list(seat.get("hot_money_top_sells"))
        theme_capital = [
            row
            for row in self._dict_list(self._value("theme_capital_reviews", []))
            if any(
                abs(self._number(row.get(field))) > 0
                for field in ("total_inflow", "top3_inflow", "leader_inflow")
            )
        ]
        stock_capital = [
            row
            for row in self._dict_list(self._value("stock_capital_reviews", []))
            if abs(self._number(row.get("main_net_inflow"))) > 0
        ]
        institution_stock_keys = {
            self._text(row.get("stock_id") or row.get("stock_name"))
            for row in [*institution_buys, *institution_sells]
        }
        institution_stock_names = {
            self._text(row.get("stock_name"))
            for row in [*institution_buys, *institution_sells]
        }
        dragon_tiger = [
            row
            for row in self._dict_list(self._value("dragon_tiger_reviews", []))
            if self._text(row.get("stock_id") or row.get("stock_name")) not in institution_stock_keys
            and self._text(row.get("stock_name")) not in institution_stock_names
        ]
        summary = seat.get("summary")
        if not any((institution_buys, institution_sells, hot_money_buys, hot_money_sells, theme_capital, stock_capital, dragon_tiger)) and not self._meaningful_text(summary):
            return []

        blocks = [self._B.heading_2("资金验证")]
        if self._meaningful_text(summary):
            blocks.append(self._B.callout(self._text(summary), icon="💰"))

        seat_rows: list[list[str]] = []
        for label, entries in (
            ("机构买入", institution_buys),
            ("机构卖出", institution_sells),
        ):
            for row in entries[:3]:
                seat_rows.append(
                    [
                        label,
                        self._display(row.get("stock_name") or row.get("stock_id")),
                        self._money(row.get("net_buy")),
                        self._human_theme(
                            row.get("theme_name"),
                            subject_key=row.get("subject_key"),
                        ),
                    ]
                )
        hot_money_by_name: dict[str, dict[str, Any]] = {}
        for row in [*hot_money_buys, *hot_money_sells]:
            name = self._text(row.get("hot_money_name"))
            if name and name not in hot_money_by_name:
                hot_money_by_name[name] = row
        for name, row in list(hot_money_by_name.items())[:6]:
            net_buy = self._number(row.get("net_buy"))
            representative_entries = self._dict_list(
                row.get("buy_entries") if net_buy >= 0 else row.get("sell_entries")
            )
            themes = list(
                dict.fromkeys(
                    self._human_theme(
                        entry.get("theme_name"),
                        subject_key=entry.get("subject_key"),
                    )
                    for entry in representative_entries
                )
            )
            themes = [theme for theme in themes if theme != "--"]
            seat_rows.append(
                [
                    "游资净买入" if net_buy >= 0 else "游资净卖出",
                    name,
                    self._money(net_buy),
                    " / ".join(themes[:2]) or "--",
                ]
            )
        if seat_rows:
            blocks.extend(self._B.table(["席位", "对象", "净额", "题材"], seat_rows))

        if theme_capital:
            rows = [
                [
                    self._human_theme(
                        row.get("theme_name"),
                        subject_key=row.get("subject_key"),
                    ),
                    self._money(row.get("total_inflow")),
                    self._money(row.get("top3_inflow")),
                    self._display(row.get("cycle_stage")),
                ]
                for row in theme_capital[:8]
            ]
            blocks.append(self._B.toggle("题材资金 Top", self._B.table(["题材", "净流入", "Top3", "周期"], rows)))

        if stock_capital:
            ranked = sorted(stock_capital, key=lambda row: self._number(row.get("main_net_inflow")), reverse=True)
            rows = [
                [
                    self._display(row.get("stock_name") or row.get("stock_id")),
                    self._human_theme(
                        row.get("theme_name"),
                        subject_key=row.get("subject_key"),
                    ),
                    self._money(row.get("main_net_inflow")),
                    "是" if row.get("is_leader") else "否",
                ]
                for row in ranked[:10]
            ]
            blocks.append(self._B.toggle("个股资金 Top", self._B.table(["股票", "题材", "主力净流入", "龙头"], rows)))

        if dragon_tiger:
            rows = [
                [
                    self._display(row.get("stock_name") or row.get("stock_id")),
                    self._display(row.get("seat_type")),
                    self._money(row.get("net_buy")),
                    self._display(row.get("side_summary") or row.get("reason")),
                ]
                for row in dragon_tiger[:10]
            ]
            blocks.append(self._B.toggle("龙虎榜", self._B.table(["股票", "席位", "净买入", "结论"], rows)))
        return blocks

    def _render_core_stocks(self) -> list[dict[str, Any]]:
        decisions = self._dict_list(self._value("strong_stock_decision_reviews", []))
        candidates = [
            row
            for row in decisions
            if self._text(row.get("role")).lower() != "reject"
            and self._text(row.get("role_label")) != "淘汰"
        ]
        if not candidates:
            return []
        ranked = sorted(
            candidates,
            key=lambda row: max(self._number(row.get("core_score")), self._number(row.get("watch_score"))),
            reverse=True,
        )
        rows = [
            [
                self._display(row.get("stock_name") or row.get("stock_id")),
                self._human_theme(
                    row.get("theme_name"),
                    subject_key=row.get("subject_key"),
                ),
                self._display(row.get("role_label") or row.get("role")),
                self._display(row.get("core_score") or row.get("watch_score")),
                self._display(row.get("next_day_action")),
            ]
            for row in ranked[:12]
        ]
        return [self._B.heading_2("核心标的"), *self._B.table(["股票", "题材", "角色", "评分", "次日动作"], rows)]

    def _render_next_day_plan(self) -> list[dict[str, Any]]:
        decision = self._value("post_market_decision_v2", {})
        decision = decision if isinstance(decision, dict) else {}
        d1_rows = self._dict_list(decision.get("weak_to_strong_d1_reviews"))
        focus_rows = self._dict_list(decision.get("next_day_focus_stocks"))
        watch_rows = self._dict_list(self._value("watchlist_reviews", []))
        watchlists = self._value("watchlists", {})
        one_to_two = watchlists.get("one_to_two", {}) if isinstance(watchlists, dict) else {}
        one_to_two_rows = self._dict_list(one_to_two.get("items") if isinstance(one_to_two, dict) else [])
        rows = d1_rows or focus_rows or watch_rows or one_to_two_rows
        if not rows:
            return []

        table_rows = []
        for row in rows[:15]:
            tomorrow_plan = row.get("tomorrow_plan")
            tomorrow_plan = tomorrow_plan if isinstance(tomorrow_plan, dict) else {}
            conditions = (
                row.get("buy_condition")
                or row.get("flags")
                or tomorrow_plan.get("confirmation_triggers")
                or tomorrow_plan.get("auction_watch")
                or []
            )
            if not isinstance(conditions, list):
                conditions = [conditions]
            watch_level = self._text(row.get("watch_level"))
            plan_type = (
                row.get("candidate_level")
                or row.get("category")
                or row.get("role_label")
                or (f"{watch_level}级观察" if watch_level else "")
                or row.get("plan_status")
            )
            table_rows.append(
                [
                    self._display(row.get("stock_name") or row.get("stock_id") or row.get("stock_code")),
                    self._human_theme(
                        row.get("theme_name"),
                        row.get("subject_name"),
                        subject_key=row.get("subject_key"),
                    ),
                    self._display(plan_type),
                    self._display(
                        self._narrative(
                            row.get("action")
                            or row.get("next_day_action")
                            or tomorrow_plan.get("expected_behavior")
                            or "观察"
                        )
                    ),
                    "；".join(
                        self._narrative(item)
                        for item in conditions[:2]
                        if self._meaningful_text(item)
                    )
                    or "--",
                ]
            )
        return [self._B.heading_2("次日计划"), *self._B.table(["股票", "题材", "类型", "动作", "条件"], table_rows)]

    def _render_data_quality(self) -> list[dict[str, Any]]:
        if not self._doc:
            return [
                self._B.heading_2("数据质量"),
                self._B.callout("盘后快照为空，未生成业务栏目。请先检查 DailyReview V2 生成链路。", icon="⚠️"),
            ]

        diagnostics = self._v2.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = self._doc.get("diagnostics")
        diagnostics = diagnostics if isinstance(diagnostics, dict) else {}
        coverage = diagnostics.get("module_coverage")
        coverage = coverage if isinstance(coverage, dict) else {}
        issues = list(self._render_issues)
        for module_name, detail in coverage.items():
            if not isinstance(detail, dict):
                continue
            status = self._text(detail.get("status")).lower()
            message = self._text(detail.get("message"))
            if status in {"", "ready"} or message == "no_dragon_tiger_day":
                continue
            if status == "empty":
                continue
            missing = detail.get("missing_fields") or detail.get("column_missing_fields") or []
            missing_text = "、".join(
                self._FIELD_LABELS.get(self._text(item), self._text(item))
                for item in missing
                if self._meaningful_text(item)
            )
            issues.append(
                [
                    self._MODULE_LABELS.get(self._text(module_name), self._text(module_name)),
                    {"partial": "部分可用", "failed": "失败", "error": "失败"}.get(status, status),
                    self._display(detail.get("row_count"), "0"),
                    (f"缺少字段：{missing_text}" if missing_text else "数据不完整"),
                ]
            )
        errors = [
            self._text(item)
            for item in diagnostics.get("errors") or []
            if self._meaningful_text(item) and "legacy" not in self._text(item).lower()
        ]
        warnings = [
            self._text(item)
            for item in diagnostics.get("warnings") or []
            if self._meaningful_text(item) and "legacy" not in self._text(item).lower()
        ]
        if not issues and not errors and not warnings:
            return []

        detail_blocks: list[dict[str, Any]] = []
        if issues:
            detail_blocks.extend(self._B.table(["模块", "状态", "行数", "说明"], issues[:20]))
        for item in errors[:5]:
            detail_blocks.append(self._B.callout(item, icon="❌"))
        for item in warnings[:5]:
            detail_blocks.append(self._B.paragraph(item))
        return [
            self._B.heading_2("数据质量"),
            self._B.toggle(f"查看数据缺口（{len(issues) + len(errors) + len(warnings)}）", detail_blocks),
        ]
