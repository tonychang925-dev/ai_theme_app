from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class NewChainPostMarketReportBuilder:
    """Build the embedded post-market report from SPS recap_doc only."""

    report_type: str = "post_market"

    def build(self, recap_doc: dict[str, Any]) -> dict[str, Any]:
        trade_date = str(recap_doc.get("trade_date") or "")
        candidate_count = self._int(recap_doc.get("candidate_count_total", recap_doc.get("candidate_count")))
        formal_count = self._int(recap_doc.get("candidate_count_formal"))
        observe_count = self._int(recap_doc.get("candidate_count_observe"))
        strong_watch_count = self._int(recap_doc.get("strong_watch_history_count"))
        pool_written = self._int(recap_doc.get("strong_watch_pool_written"))

        formal_candidates = list(recap_doc.get("formal_top_candidates") or [])
        observe_candidates = list(recap_doc.get("observe_candidates") or [])
        top_candidates = list(recap_doc.get("top_candidates") or [])
        promoted_pool = list(recap_doc.get("promoted_pool_preview") or [])
        strong_watch_history = list(recap_doc.get("strong_watch_history") or [])
        context = dict(recap_doc.get("report_context") or {})
        theme_name_map = dict(context.get("theme_name_map") or {})
        stock_fact_map = self._stock_fact_map(context.get("stock_facts") or [])
        cycles_by_theme = self._cycle_map(context.get("cycles") or [], theme_name_map)
        recap_stock_rows = self._recap_stock_rows(context)
        recap_strong_rows = self._recap_strong_rows(recap_stock_rows)
        recap_theme_rows = self._recap_theme_rows(context, recap_stock_rows)

        dependency_status = self._dependency_status(recap_doc)
        missing_dependencies = [name for name, ok in dependency_status.items() if not ok]
        subject_count = len(
            {
                NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
                for item in top_candidates + formal_candidates + observe_candidates
                if NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            }
        )
        top_stock_names = [
            str((item or {}).get("stock_name") or (item or {}).get("stock_id") or "")
            for item in (top_candidates or formal_candidates)[:5]
        ]
        top_stock_text = "、".join([name for name in top_stock_names if name]) or "暂无候选"

        highlights = [
            f"新链盘后快照已生成：A/B/C/D 依赖{'完整' if not missing_dependencies else '未完全命中'}",
            f"强势观察池跟踪 {strong_watch_count or pool_written} 条，弱转强候选 {candidate_count} 条",
            f"候选覆盖 {subject_count} 个题材，重点候选：{top_stock_text}",
        ]
        if missing_dependencies:
            highlights.append(f"新链依赖未完全命中：{','.join(missing_dependencies)}")

        sections = [
            {
                "heading": "大盘环境总结",
                "items": self._market_lines(
                    recap_doc=recap_doc,
                    context=context,
                    dependency_status=dependency_status,
                    candidate_count=candidate_count,
                    strong_watch_count=strong_watch_count,
                    pool_written=pool_written,
                ),
            },
            {
                "heading": "板块环境总结",
                "items": self._theme_environment_lines(top_candidates or formal_candidates, theme_name_map, cycles_by_theme, limit=12),
            },
            {
                "heading": "主线与支线",
                "items": (
                    _theme_lines_result := self._theme_lines(
                        recap_theme_rows,
                        theme_name_map,
                        cycles_by_theme,
                        stock_fact_map,
                        context,
                        limit=12,
                    )
                )[0],
            },
            {
                "heading": "主线资金流入前10",
                "items": self._theme_capital_lines(top_candidates or formal_candidates, theme_name_map, cycles_by_theme, context, limit=10),
            },
            {
                "heading": "周期与动作",
                "items": self._cycle_lines(top_candidates or promoted_pool, theme_name_map, cycles_by_theme, limit=12),
            },
            {
                "heading": "主线迁移监控",
                "items": self._transition_lines(top_candidates or promoted_pool, theme_name_map, cycles_by_theme, limit=12),
            },
            {
                "heading": "强势股分层",
                "items": self._strong_stock_lines(recap_strong_rows, theme_name_map, stock_fact_map, limit=20),
            },
            {
                "heading": "次日观察清单",
                "items": self._watchlist_lines(recap_stock_rows, theme_name_map, stock_fact_map, cycles_by_theme, limit=20),
            },
            {
                "heading": "主线股票资金流入前20",
                "items": self._stock_capital_lines(recap_stock_rows, theme_name_map, stock_fact_map, limit=20),
            },
            {
                "heading": "当日异动股与资金行为",
                "items": self._abnormal_lines(context.get("abnormal_signals") or top_candidates or formal_candidates, theme_name_map, limit=30),
            },
            {
                "heading": "资金行为增强",
                "items": NewChainPostMarketReportBuilder._money_flow_lines(context.get("money_flow") or top_candidates or formal_candidates, theme_name_map, stock_fact_map, limit=20),
            },
            {
                "heading": "龙虎榜",
                "items": self._dragon_tiger_lines(context.get("dragon_tiger") or [], theme_name_map, limit=20),
            },
        ]

        return {
            "report_type": self.report_type,
            "trade_date": trade_date,
            "title": f"{trade_date} 盘后复盘",
            "summary": (
                f"基于 stock_processing_service 新链 A/B/C/D 产物生成："
                f"强势观察池 {pool_written} 条，弱转强候选 {candidate_count} 条。"
            ),
            "highlights": highlights,
            "sections": sections,
            "metadata": {
                "source": "stock_processing_service.new_chain",
                "builder": "NewChainPostMarketReportBuilder",
                "snapshot_version": recap_doc.get("snapshot_version"),
                "candidate_source": recap_doc.get("candidate_source"),
                "layer_c_input_mode": recap_doc.get("layer_c_input_mode"),
                "dependency_status": dependency_status,
                "missing_new_chain_dependencies": missing_dependencies,
                "counts": {
                    "candidate_count": candidate_count,
                    "candidate_count_formal": formal_count,
                    "candidate_count_observe": observe_count,
                    "strong_watch_history_count": strong_watch_count,
                    "strong_watch_pool_written": pool_written,
                },
                "theme_line_debug": _theme_lines_result[1],
            },
        }

    def _dependency_status(self, recap_doc: dict[str, Any]) -> dict[str, bool]:
        return {
            "theme_cycle_judgement_v2": self._int(recap_doc.get("layer_b_cycle_hit_count")) > 0,
            "theme_mainline_identity_registry_or_mainline_state_daily": self._int(
                recap_doc.get("layer_a_identity_hit_count")
            )
            > 0,
            "strong_stock_watch_pool": (
                self._int(recap_doc.get("strong_watch_pool_written")) > 0
                or self._int(recap_doc.get("strong_watch_history_count")) > 0
                or self._int(recap_doc.get("strong_watch_promoted_count")) > 0
            ),
        }

    @staticmethod
    def _recap_stock_rows(context: dict[str, Any]) -> list[dict[str, Any]]:
        rows = [dict(row or {}) for row in context.get("stock_facts") or []]
        return sorted(
            rows,
            key=lambda item: (
                0 if item.get("is_leader") else 1,
                NewChainPostMarketReportBuilder._rank(item),
                -NewChainPostMarketReportBuilder._float(NewChainPostMarketReportBuilder._inflow(item)),
                -NewChainPostMarketReportBuilder._float(item.get("pct_chg")),
            ),
        )

    @staticmethod
    def _recap_theme_rows(context: dict[str, Any], stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if stock_rows:
            return stock_rows
        capital_rows = [dict(row or {}) for row in context.get("theme_capital_flow") or []]
        if capital_rows:
            return capital_rows
        return [dict(row or {}) for row in context.get("cycles") or []]

    @staticmethod
    def _recap_strong_rows(stock_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        leader_rows = [
            row
            for row in stock_rows
            if row.get("leader_composite_score") not in (None, "")
        ]
        return sorted(
            leader_rows,
            key=lambda item: (
                NewChainPostMarketReportBuilder._rank(
                    {"rank_order": item.get("leader_candidate_rank")}
                ),
                -NewChainPostMarketReportBuilder._float(item.get("leader_composite_score")),
            ),
        ) or stock_rows

    @staticmethod
    def _market_lines(
        *,
        recap_doc: dict[str, Any],
        context: dict[str, Any],
        dependency_status: dict[str, bool],
        candidate_count: int,
        strong_watch_count: int,
        pool_written: int,
    ) -> list[str]:
        market = dict(context.get("market") or {})
        dependency_text = "；".join(
            f"{name}={'ok' if ok else 'missing'}" for name, ok in dependency_status.items()
        )
        if market:
            return [
                (
                    f"市场偏向 {market.get('market_bias') or '--'}；动作 {market.get('action_bias') or '--'}；"
                    f"环境总分 {market.get('market_health_score') or '--'}"
                ),
                str(market.get("conclusion") or "市场结论待补充"),
                f"广度 {market.get('breadth_status') or '--'}；短线情绪 {market.get('short_term_sentiment_status') or '--'}；接力生态 {market.get('relay_sentiment_status') or '--'}",
                f"日内分歧 {market.get('intraday_fade_status') or '--'}",
                f"新链依赖状态：{dependency_text}",
            ]
        return [
            "新链盘后复盘已生成；报告来源 stock_processing_service A/B/C/D 快照，不再读取旧链 recap 表。",
            f"依赖状态：{dependency_text}",
            f"强势观察池写入 {pool_written} 条；历史跟踪 {strong_watch_count} 条；弱转强正式候选 {candidate_count} 条。",
            (
                f"输入模式 {recap_doc.get('layer_c_input_mode') or '--'}；"
                f"snapshot_version {recap_doc.get('snapshot_version') or '--'}。"
            ),
        ]

    @staticmethod
    def _theme_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        cycles_by_theme: dict[str, dict[str, Any]],
        stock_fact_map: dict[tuple[str, str], dict[str, Any]],
        context: dict[str, Any],
        *,
        limit: int,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """返回 (lines, debug).

        debug 每项包含该题材的分数字段来源，用于诊断「事件分/市场分为空」问题。
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            grouped.setdefault(theme, []).append(item)
        capital_by_subject = NewChainPostMarketReportBuilder._theme_capital_map(
            context.get("theme_capital_flow") or []
        )
        lines: list[str] = []
        debug: list[dict[str, Any]] = []

        # 有 cycle 数据的题材优先展示（事件分/市场分需要 cycle 数据）
        def _theme_rank(theme: str, items: list[dict[str, Any]]) -> tuple[int, float]:
            top_sk = str((items[0] or {}).get("subject_key") or "").strip() if items else ""
            has_cycle = 1 if cycles_by_theme.get(top_sk) else 0
            best = max((NewChainPostMarketReportBuilder._score(x) for x in items), default=0.0)
            # 有 cycle → 排在前面（has_cycle=0 means YES, 1 means NO for ascending sort）
            return (0 if has_cycle else 1, -best)

        ranked_themes = sorted(grouped.items(), key=lambda kv: _theme_rank(kv[0], kv[1]))
        for theme, items in ranked_themes[:limit]:
            top = sorted(items, key=lambda x: NewChainPostMarketReportBuilder._score(x), reverse=True)[:3]
            stocks = "、".join(str(x.get("stock_name") or x.get("stock_id") or "") for x in top)
            subject_key = str(top[0].get("subject_key") or "--") if top else "--"
            cycle = NewChainPostMarketReportBuilder._cycle_for(
                cycles_by_theme,
                subject_key=subject_key,
                theme=theme,
            )
            fact = NewChainPostMarketReportBuilder._fact_for(top[0] if top else {}, stock_fact_map)
            capital = capital_by_subject.get(subject_key, {})

            # 多源兜底：事件分 = mainline_strength_score
            # 来源优先级：cycle → theme_capital_flow → stock_fact → top item
            event_score = NewChainPostMarketReportBuilder._first_present(
                cycle.get("mainline_strength_score"),
                cycle.get("state_strength_score"),
                capital.get("mainline_strength_score"),
                fact.get("mainline_strength_score"),
                (top[0] or {}).get("mainline_strength_score") if top else None,
            )
            # 多源兜底：市场分 = fade_risk_score
            market_score = NewChainPostMarketReportBuilder._first_present(
                cycle.get("fade_risk_score"),
                capital.get("fade_risk_score"),
                fact.get("fade_risk_score"),
                (top[0] or {}).get("fade_risk_score") if top else None,
            )

            capital = capital_by_subject.get(subject_key, {})
            total_inflow = NewChainPostMarketReportBuilder._first_present(
                capital.get("main_net_inflow_sum"),
                NewChainPostMarketReportBuilder._inflow(fact),
            )
            leader_inflow = NewChainPostMarketReportBuilder._first_present(
                capital.get("leader_main_net_inflow"),
                NewChainPostMarketReportBuilder._inflow(fact),
            )

            debug.append({
                "theme": theme,
                "subject_key": subject_key,
                "cycle_found": bool(cycle),
                "cycle_keys": sorted(cycle.keys()) if cycle else [],
                "cycle_mainline_strength_score": cycle.get("mainline_strength_score"),
                "cycle_fade_risk_score": cycle.get("fade_risk_score"),
                "event_score_resolved": event_score,
                "market_score_resolved": market_score,
                "event_score_source": (
                    "cycle" if event_score == cycle.get("mainline_strength_score")
                    else "capital" if event_score == capital.get("mainline_strength_score")
                    else "fact" if fact and event_score == fact.get("mainline_strength_score")
                    else "top_item" if top and event_score == (top[0] or {}).get("mainline_strength_score")
                    else "none"
                ),
                "market_score_source": (
                    "cycle" if market_score == cycle.get("fade_risk_score")
                    else "capital" if market_score == capital.get("fade_risk_score")
                    else "fact" if fact and market_score == fact.get("fade_risk_score")
                    else "top_item" if top and market_score == (top[0] or {}).get("fade_risk_score")
                    else "none"
                ),
            })

            lines.append(
                f"{theme}：subject_key {subject_key}；层级 main；主线存活 {'是' if cycle.get('final_mainline_alive') is not False else '否'}；"
                f"状态 {cycle.get('final_cycle_state') or 'rebound'}；主线强度 {NewChainPostMarketReportBuilder._fmt(cycle.get('mainline_strength_score') or cycle.get('state_strength_score'))}；"
                f"退潮风险 {NewChainPostMarketReportBuilder._fmt(cycle.get('fade_risk_score'))}；"
                f"总净流入 {NewChainPostMarketReportBuilder._money(total_inflow)}；"
                f"龙头净流入 {NewChainPostMarketReportBuilder._money(leader_inflow)}；"
                f"题材K线 {NewChainPostMarketReportBuilder._kline_text(fact)}；代表股 {stocks or '--'}；事件 {NewChainPostMarketReportBuilder._fmt(event_score)}；市场 {NewChainPostMarketReportBuilder._fmt(market_score)}"
            )
        return (lines or ["暂无主线候选"], debug)

    @staticmethod
    def _theme_environment_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        cycles_by_theme: dict[str, dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        grouped = NewChainPostMarketReportBuilder._group_by_theme(rows, theme_name_map)
        lines: list[str] = []
        for theme, items in list(grouped.items())[:limit]:
            best = max((NewChainPostMarketReportBuilder._score(x) for x in items), default=0.0)
            action = "可主做" if best >= 98 else "可做弱转强" if best >= 90 else "可观察"
            health = "板块健康" if best >= 95 else "板块尚可"
            subj_key = str((items[0] or {}).get("subject_key") or "").strip() if items else ""
            cycle = NewChainPostMarketReportBuilder._cycle_for(
                cycles_by_theme,
                subject_key=subj_key,
                theme=theme,
            )
            fade = "退潮确认" if cycle.get("fade_confirmed") else "退潮观察" if cycle.get("fade_watch") else "退潮未确认"
            lines.append(f"{theme}：{health}；板块联动待竞价确认；龙头仍活跃；后排跟随待观察；{fade}；动作 {action}")
        return lines or ["暂无板块环境"]

    @staticmethod
    def _theme_capital_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        cycles_by_theme: dict[str, dict[str, Any]],
        context: dict[str, Any],
        *,
        limit: int,
    ) -> list[str]:
        grouped = NewChainPostMarketReportBuilder._group_by_theme(rows, theme_name_map)
        capital_rows = [dict(row or {}) for row in context.get("theme_capital_flow") or []]
        if capital_rows:
            best_by_theme = {
                theme: max((NewChainPostMarketReportBuilder._score(x) for x in items), default=0.0)
                for theme, items in grouped.items()
            }
            lines: list[str] = []
            for item in capital_rows[:limit]:
                theme = str(
                    item.get("resolved_theme_name")
                    or NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
                )
                subject_key = str(item.get("subject_key") or "--")
                state = str(item.get("final_cycle_state") or "rebound")
                total_inflow = item.get("main_net_inflow_sum")
                top3_inflow = item.get("top3_main_net_inflow_sum")
                leader_inflow = item.get("leader_main_net_inflow")
                action = "可主做" if best_by_theme.get(theme, 0.0) >= 98 else "可做弱转强"
                lines.append(
                    f"{theme}：subject_key {subject_key}；层级 main；状态 {state}；"
                    f"总净流入 {NewChainPostMarketReportBuilder._money(total_inflow)}；"
                    f"前3净流入 {NewChainPostMarketReportBuilder._money(top3_inflow)}；"
                    f"龙头净流入 {NewChainPostMarketReportBuilder._money(leader_inflow)}；"
                    f"流入股 {item.get('positive_inflow_stock_count') or 0}；"
                    f"题材K线 新链资金确认；资金集中度 {NewChainPostMarketReportBuilder._fmt(item.get('capital_focus_score'))}；"
                    f"阶段 {state}；动作 {action}"
                )
            return lines or ["暂无主线资金数据"]

        money_by_theme: dict[str, list[dict[str, Any]]] = {}
        for row in context.get("money_flow") or []:
            item = dict(row or {})
            theme = str(item.get("resolved_theme_name") or item.get("theme_name") or item.get("subject_key") or "未分类")
            money_by_theme.setdefault(theme, []).append(item)
        lines: list[str] = []
        for theme, items in list(grouped.items())[:limit]:
            subject_key = str(items[0].get("subject_key") or "--") if items else "--"
            best = max((NewChainPostMarketReportBuilder._score(x) for x in items), default=0.0)
            money_rows = money_by_theme.get(theme, [])
            total_inflow = sum(float(x.get("main_net_inflow") or 0) for x in money_rows)
            top3_inflow = sum(float(x.get("main_net_inflow") or 0) for x in money_rows[:3])
            leader_inflow = float((money_rows[0] or {}).get("main_net_inflow") or 0) if money_rows else 0.0
            cycle = NewChainPostMarketReportBuilder._cycle_for(
                cycles_by_theme,
                subject_key=subject_key,
                theme=theme,
            )
            lines.append(
                f"{theme}：subject_key {subject_key}；层级 main；状态 {cycle.get('final_cycle_state') or 'rebound'}；"
                f"总净流入 {NewChainPostMarketReportBuilder._money(total_inflow)}；前3净流入 {NewChainPostMarketReportBuilder._money(top3_inflow)}；龙头净流入 {NewChainPostMarketReportBuilder._money(leader_inflow)}；"
                f"流入股 {len(money_rows) or len(items)}；题材K线 新链强势池候选；阶段 {cycle.get('final_cycle_state') or 'rebound'}；"
                f"动作 {'可主做' if best >= 98 else '可做弱转强'}"
            )
        return lines or ["暂无主线资金数据"]

    @staticmethod
    def _cycle_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        cycles_by_theme: dict[str, dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        grouped: dict[str, str] = {}
        for row in rows:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            cycle = NewChainPostMarketReportBuilder._cycle_for(
                cycles_by_theme,
                subject_key=item.get("subject_key", ""),
                theme=NewChainPostMarketReportBuilder._theme_name(item, theme_name_map),
            )
            state = str(cycle.get("final_cycle_state") or item.get("final_cycle_state") or item.get("cycle_state") or "rebound")
            if theme not in grouped:
                grouped[theme] = state
        return [
            f"{theme}：阶段 {state}；退潮观察 否；退潮确认 否"
            for theme, state in list(grouped.items())[:limit]
        ] or ["暂无周期动作"]

    @staticmethod
    def _transition_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        cycles_by_theme: dict[str, dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        grouped: dict[str, str] = {}
        for row in rows:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            cycle = NewChainPostMarketReportBuilder._cycle_for(
                cycles_by_theme,
                subject_key=item.get("subject_key", ""),
                theme=NewChainPostMarketReportBuilder._theme_name(item, theme_name_map),
            )
            state = str(cycle.get("final_cycle_state") or item.get("final_cycle_state") or item.get("cycle_state") or "rebound")
            grouped.setdefault(theme, state)
        return [
            f"{theme}：{state} -> {state}；迁移 flat；置信度 60.00；触发 新链快照"
            for theme, state in list(grouped.items())[:limit]
        ] or ["暂无主线迁移数据"]

    @staticmethod
    def _strong_stock_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        stock_fact_map: dict[tuple[str, str], dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        lines: list[str] = []
        for row in rows[:limit]:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            fact = NewChainPostMarketReportBuilder._fact_for(item, stock_fact_map)
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "").strip()
            score = str(
                NewChainPostMarketReportBuilder._first_present(
                    fact.get("leader_composite_score"),
                    item.get("leader_composite_score"),
                    item.get("candidate_score"),
                    item.get("watch_score"),
                    "--",
                )
            ).strip()
            support_type = str(item.get("support_type") or fact.get("position_label") or "").strip()
            score_value = NewChainPostMarketReportBuilder._score(item)
            role = (
                "龙头"
                if fact.get("is_leader") or item.get("is_leader") or score_value >= 98
                else "龙二"
                if fact.get("rank_order") == 2 or item.get("rank_order") == 2 or score_value >= 90
                else "补涨"
            )
            money_score = NewChainPostMarketReportBuilder._first_present(
                fact.get("leader_capital_score"),       # Layer C: theme_leader_candidate.capital_score
                item.get("leader_capital_score"),
                fact.get("money_flow_score"),           # money_flow_enhanced
                fact.get("money_composite_score"),
                fact.get("abnormal_composite_score"),   # stock_abnormal_signal
                item.get("money_flow_score"),
                item.get("money_composite_score"),
                item.get("abnormal_composite_score"),
                # 不 fallback 到 D1 的 candidate_score/watch_score
                # 设计文档 §13.3.4：强势股分层主体不依赖 D1 候选池
            )
            lines.append(
                f"{theme}：{role} {stock_name or '--'}；综合分 {score}；"
                f"正宗性 {score}×25%｜新链候选强度；领涨性 {NewChainPostMarketReportBuilder._fmt(fact.get('pct_chg'))}；"
                f"资金量能 {NewChainPostMarketReportBuilder._fmt(money_score)}；"
                f"结构位置 {NewChainPostMarketReportBuilder._fmt(fact.get('trend_strength_score'))}；"
                f"抗跌承接 {NewChainPostMarketReportBuilder._fmt(fact.get('support_score') or item.get('support_score') or fact.get('trend_strength_score'))}；"
                f"资金 {fact.get('money_flow_tier') or '新链候选'} / {fact.get('role_enhanced') or fact.get('role_label') or '强势观察'}；"
                f"K线位置 {support_type or '--'}；K线形态 {NewChainPostMarketReportBuilder._pattern_text(fact)}；"
                f"评分依据 题材内排序 {fact.get('rank_order') or '--'}；涨跌幅 {NewChainPostMarketReportBuilder._fmt(fact.get('pct_chg'))}%；"
                f"换手率 {NewChainPostMarketReportBuilder._fmt(fact.get('turnover_rate'))}；量比 {NewChainPostMarketReportBuilder._fmt(fact.get('volume_ratio'))}"
            )
        return lines or ["暂无强势股候选"]

    @staticmethod
    def _watchlist_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        stock_fact_map: dict[tuple[str, str], dict[str, Any]],
        cycles_by_theme: dict[str, dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        lines: list[str] = []
        for row in rows[:limit]:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            fact = NewChainPostMarketReportBuilder._fact_for(item, stock_fact_map)
            cycle = NewChainPostMarketReportBuilder._cycle_for(
                cycles_by_theme,
                subject_key=item.get("subject_key", ""),
                theme=NewChainPostMarketReportBuilder._theme_name(item, theme_name_map),
            )
            subject_key = str(item.get("subject_key") or "--")
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "--")
            support_type = str(item.get("support_type") or fact.get("position_label") or "--")
            role = "龙头" if fact.get("is_leader") or item.get("is_leader") else "观察"
            lines.append(
                f"次日观察：{theme}｜{stock_name}｜subject_key {subject_key}｜角色 {role}｜"
                f"阶段 {cycle.get('final_cycle_state') or 'rebound'}｜动作 观察竞价承接｜"
                f"量比 {NewChainPostMarketReportBuilder._fmt(fact.get('volume_ratio'))}｜"
                f"形态 {NewChainPostMarketReportBuilder._pattern_text(fact) or support_type}｜flag {fact.get('current_flag') or '--'}"
            )
        return lines or ["暂无次日观察候选"]

    @staticmethod
    def _stock_capital_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        stock_fact_map: dict[tuple[str, str], dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        lines: list[str] = []
        for idx, row in enumerate(rows[:limit], start=1):
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            fact = NewChainPostMarketReportBuilder._fact_for(item, stock_fact_map)
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "--")
            stock_id = str(item.get("stock_id") or "")
            score = str(item.get("candidate_score") or item.get("watch_score") or "--")
            lines.append(
                f"{stock_name}({stock_id.split('.')[0] if stock_id else '--'})：{theme}；"
                f"主力净流入 {NewChainPostMarketReportBuilder._money(NewChainPostMarketReportBuilder._inflow(fact))}；"
                f"题材内排名 {fact.get('rank_order') or idx}；涨幅 {NewChainPostMarketReportBuilder._fmt(fact.get('pct_chg'))}%；"
                f"龙头 {'是' if fact.get('is_leader') else '否'}；flag {NewChainPostMarketReportBuilder._value_or_dash(fact.get('current_flag'))}；候选分 {score}"
            )
        return lines or ["暂无主线股票资金数据"]

    @staticmethod
    def _abnormal_lines(rows: list[Any], theme_name_map: dict[str, str], *, limit: int) -> list[str]:
        lines: list[str] = []
        for row in rows[:limit]:
            item = dict(row or {})
            theme = str(item.get("resolved_theme_name") or NewChainPostMarketReportBuilder._theme_name(item, theme_name_map))
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "--")
            score = str(item.get("abnormal_composite_score") or item.get("candidate_score") or item.get("watch_score") or "--")
            labels_text = NewChainPostMarketReportBuilder._labels_text(item.get("abnormal_labels")) or "弱转强/强势池"
            lines.append(
                f"{theme}：{stock_name}；异动分 {score}；换手率 {NewChainPostMarketReportBuilder._fmt(item.get('turnover_rate'))}%；"
                f"量比 --；成交量/50日均量 {NewChainPostMarketReportBuilder._fmt(item.get('volume_ratio_to_ma50'))}；"
                f"资金 主力净流入 {NewChainPostMarketReportBuilder._money(item.get('main_net_inflow'))} / 题材内净流入排名 {item.get('main_net_inflow_rank_in_theme') or '--'}；"
                f"标签 {labels_text}；结论 {item.get('conclusion') or item.get('abnormal_conclusion') or '--'}"
            )
        return lines or ["暂无当日异动数据"]

    @staticmethod
    def _money_flow_lines(
        rows: list[Any],
        theme_name_map: dict[str, str],
        stock_fact_map: dict[tuple[str, str], dict[str, Any]],
        *,
        limit: int,
    ) -> list[str]:
        lines: list[str] = []
        for row in rows[:limit]:
            item = dict(row or {})
            theme = str(item.get("resolved_theme_name") or NewChainPostMarketReportBuilder._theme_name(item, theme_name_map))
            fact = NewChainPostMarketReportBuilder._fact_for(item, stock_fact_map)
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "--")
            score = str(item.get("money_flow_score") or item.get("candidate_score") or item.get("watch_score") or "--")
            support_type = str(item.get("support_type") or fact.get("position_label") or "--")
            lines.append(
                f"{theme}：{stock_name}；{item.get('role_enhanced') or item.get('role_label') or '龙头观察'}；"
                f"资金分层 {item.get('money_flow_tier') or '--'}；得分 {score}；"
                f"角色 {item.get('role_label') or '候选'} -> {item.get('role_enhanced') or '龙头观察'}；K线位置 {support_type}；"
                f"K线形态 {NewChainPostMarketReportBuilder._pattern_text(fact)}"
            )
        return lines or ["暂无资金行为增强数据"]

    @staticmethod
    def _dragon_tiger_lines(rows: list[Any], theme_name_map: dict[str, str], *, limit: int) -> list[str]:
        grouped: dict[str, list[str]] = {}
        seen: set[tuple[str, str]] = set()
        for row in rows:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "--")
            stock_id = str(item.get("stock_id") or "").split(".")[0]
            if "net_amount" in item:
                entries = NewChainPostMarketReportBuilder._hot_money_entries(item.get("seat_summary"))
                for entry in entries:
                    key = (entry["hot_money_name"], stock_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    grouped.setdefault(entry["hot_money_name"], []).append(
                        f"{theme} / {stock_name}({stock_id}) / {entry['side']}{NewChainPostMarketReportBuilder._money(entry['net_amount'])}"
                    )
            else:
                grouped.setdefault("新链观察", []).append(f"{theme} / {stock_name} / 龙虎榜数据待同步")
        lines = [f"{name}：{'；'.join(items[:8])}" for name, items in sorted(grouped.items(), key=lambda x: x[0])]
        return lines or ["暂无龙虎榜新链数据"]

    @staticmethod
    def _pool_lines(rows: list[Any], *, limit: int) -> list[str]:
        lines: list[str] = []
        for row in rows[:limit]:
            item = dict(row or {})
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "").strip()
            subject_name = str(item.get("subject_name") or item.get("subject_key") or "").strip()
            watch_status = str(item.get("watch_status") or "").strip()
            watch_score = str(item.get("watch_score") or "").strip()
            parts = [
                part
                for part in (stock_name, subject_name, watch_status, f"watch={watch_score}" if watch_score else "")
                if part
            ]
            if parts:
                lines.append(" / ".join(parts))
        return lines or ["暂无强势池输入"]

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value or 0)
        except Exception:
            return 0.0

    @staticmethod
    def _rank(item: dict[str, Any]) -> int:
        try:
            return int(item.get("rank_order") or 9999)
        except Exception:
            return 9999

    @staticmethod
    def _score(item: dict[str, Any]) -> float:
        """取 stock_fact 的 Layer C 龙头综合分，不依赖 D1 candidate_score/watch_score。

        设计文档（第三阶段 §13.3.4）：
        「post_market_recap_snapshot 不以 D1 候选池作为复盘主体真源」
        """
        try:
            return float(
                item.get("leader_composite_score")
                or item.get("leader_capital_score")
                or 0
            )
        except Exception:
            return 0.0

    @staticmethod
    def _group_by_theme(rows: list[Any], theme_name_map: dict[str, str] | None = None) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            item = dict(row or {})
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map or {})
            grouped.setdefault(theme, []).append(item)
        return grouped

    @staticmethod
    def _theme_name(item: Any, theme_name_map: dict[str, str]) -> str:
        row = dict(item or {})
        subject_key = str(row.get("subject_key") or "").strip()
        raw = str(
            row.get("resolved_theme_name")
            or row.get("theme_name")
            or row.get("subject_name")
            or ""
        ).strip()
        if raw and raw != subject_key and not raw.isdigit():
            return raw
        mapped = str(theme_name_map.get(subject_key) or "").strip()
        if mapped and mapped != subject_key and not mapped.isdigit():
            return mapped
        return subject_key or raw or "未分类"

    @staticmethod
    def _stock_fact_map(rows: list[Any]) -> dict[tuple[str, str], dict[str, Any]]:
        result: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            item = dict(row or {})
            subject_key = str(item.get("subject_key") or "").strip()
            stock_keys = NewChainPostMarketReportBuilder._stock_key_variants(item.get("stock_id"))
            if not stock_keys:
                continue
            for stock_id in stock_keys:
                result[(subject_key, stock_id)] = item
        return result

    @staticmethod
    def _fact_for(item: Any, stock_fact_map: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
        row = dict(item or {})
        subject_key = str(row.get("subject_key") or "").strip()
        for stock_id in NewChainPostMarketReportBuilder._stock_key_variants(row.get("stock_id")):
            fact = stock_fact_map.get((subject_key, stock_id))
            if fact:
                return fact
        return {}

    @staticmethod
    def _stock_key_variants(value: Any) -> list[str]:
        raw = str(value or "").strip().upper()
        if not raw:
            return []
        base = raw.split(".")[0]
        return list(dict.fromkeys([raw, base]))

    @staticmethod
    def _theme_capital_map(rows: list[Any]) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row or {})
            subject_key = str(item.get("subject_key") or "").strip()
            if subject_key:
                result[subject_key] = item
        return result

    @staticmethod
    def _cycle_map(rows: list[Any], theme_name_map: dict[str, str]) -> dict[str, dict[str, Any]]:
        """以 subject_key 为主键构建 cycle 索引。

        sql_cycles 和 sql_stock_facts 的 theme_name 解析逻辑不同
        （前者优先 v2.theme_name，后者优先 vtb.theme_name），
        因此必须用 subject_key 作为可靠键，避免主题名不匹配导致 cycle 查找失败。
        """
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row or {})
            sk = str(item.get("subject_key") or "").strip()
            if not sk:
                continue
            # subject_key 是主键（可靠）
            if sk not in result:
                result[sk] = item
            # 同时用解析后的 theme_name 做别名，兼容旧调用
            theme = NewChainPostMarketReportBuilder._theme_name(item, theme_name_map)
            if theme and theme not in result:
                result[theme] = item
        return result

    @staticmethod
    def _cycle_for(
        cycles_by_theme: dict[str, dict[str, Any]],
        *,
        subject_key: str = "",
        theme: str = "",
    ) -> dict[str, Any]:
        """按 subject_key → theme 顺序查找 cycle 数据。"""
        if subject_key:
            item = cycles_by_theme.get(subject_key)
            if item:
                return item
        if theme:
            item = cycles_by_theme.get(theme)
            if item:
                return item
        return {}

    @staticmethod
    def _fmt(value: Any) -> str:
        if value in (None, ""):
            return "--"
        try:
            return f"{float(value):.2f}"
        except Exception:
            return str(value)

    @staticmethod
    def _money(value: Any) -> str:
        if value in (None, ""):
            return "--"
        try:
            return f"{float(value) / 100000000:.2f}亿"
        except Exception:
            return str(value)

    @staticmethod
    def _pattern_text(fact: dict[str, Any]) -> str:
        labels = fact.get("pattern_labels")
        if isinstance(labels, str) and labels.strip().startswith("["):
            try:
                import json
                labels = json.loads(labels)
            except Exception:
                pass
        if isinstance(labels, list):
            text = "/".join(str(x) for x in labels if str(x))
        else:
            text = str(labels or "").strip()
        extra = [
            str(fact.get(key) or "").strip()
            for key in ("volume_pattern_status", "breakout_status", "pullback_status", "risk_pattern_status")
            if str(fact.get(key) or "").strip()
        ]
        all_parts = [part for part in [text, *extra] if part and part != "[]"]
        return "/".join(dict.fromkeys(all_parts)) or "--"

    @staticmethod
    def _kline_text(fact: dict[str, Any]) -> str:
        parts = [
            str(fact.get("position_label") or "").strip(),
            str(fact.get("ma_alignment_status") or "").strip(),
            NewChainPostMarketReportBuilder._pattern_text(fact),
        ]
        return "；".join(part for part in parts if part and part != "--") or "--"

    @staticmethod
    def _inflow(fact: dict[str, Any]) -> Any:
        return fact.get("main_net_inflow") or fact.get("abnormal_main_net_inflow") or fact.get("institution_net_buy")

    @staticmethod
    def _first_present(*values: Any) -> Any:
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _value_or_dash(value: Any) -> str:
        if value is None or value == "":
            return "--"
        return str(value)

    @staticmethod
    def _labels_text(value: Any) -> str:
        if isinstance(value, list):
            return "/".join(str(x) for x in value if str(x))
        if isinstance(value, str) and value.strip().startswith("["):
            try:
                import json
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return "/".join(str(x) for x in parsed if str(x))
            except Exception:
                pass
        return str(value or "")

    @staticmethod
    def _hot_money_entries(value: Any) -> list[dict[str, Any]]:
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except Exception:
                value = [value]
        rows = value if isinstance(value, list) else []
        rules = (
            ("深圳益田路荣超商务中心", "赵老哥"),
            ("佛山季华六路", "佛山系"),
            ("上海茅台路", "作手新一"),
            ("成都北一环路", "成都系"),
            ("上海浦东新区银城中路", "方新侠"),
            ("上海分公司", "章盟主系"),
            ("杭州五星路", "孙哥"),
            ("湖里大道", "厦门湖里大道"),
            ("溧阳路", "养家系"),
            ("劳动路", "小鳄鱼系"),
        )
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for raw_value in rows:
            raw = str(raw_value or "").strip()
            if not raw:
                continue
            hot_money_name = ""
            for pattern, name in rules:
                if pattern in raw:
                    hot_money_name = name
                    break
            if not hot_money_name:
                continue
            side = "买入" if "买入席位" in raw else "卖出" if "卖出席位" in raw else "--"
            net_amount = 0.0
            if "净额 " in raw:
                try:
                    net_amount = float(raw.split("净额 ", 1)[1].strip())
                except Exception:
                    net_amount = 0.0
            key = (hot_money_name, side, f"{net_amount:.2f}")
            if key in seen:
                continue
            seen.add(key)
            result.append({"hot_money_name": hot_money_name, "side": side, "net_amount": net_amount})
        return result
