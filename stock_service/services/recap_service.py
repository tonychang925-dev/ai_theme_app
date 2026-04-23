from __future__ import annotations

import json
from pathlib import Path

from stock_service.models import MarketReport
from stock_service.repositories.report_repository import ReportRepository
from stock_service.services.hot_money_activity_service import HOT_MONEY_SEAT_RULES


def _canonical_stock_id(value: str) -> str:
    raw = str(value or "").strip().upper()
    if "." in raw:
        raw = raw.split(".", 1)[0]
    return raw


def _to_float(value) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _short_text(value: str, limit: int = 34) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit]}..."


def _sanitize_inline_text(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return "--"
    return (
        text.replace("\r", " ")
        .replace("\n", " ")
        .replace("\t", " ")
        .replace("；", "、")
        .replace(";", "、")
    ).strip() or "--"


def _summarize_in_billions(value) -> str:
    amount = _to_float(value) / 1e8
    return f"{amount:.2f}亿"


def _pattern_text(pattern_labels) -> str:
    labels = [str(x).strip() for x in (pattern_labels or []) if str(x).strip()]
    return "/".join(labels[:3]) if labels else "--"


def _flag_text(value) -> str:
    if value is None:
        return "--"
    try:
        return str(int(value))
    except Exception:
        return str(value)


def _is_numeric_theme_name(value) -> bool:
    text = str(value or "").strip()
    return bool(text) and text.isdigit()


def _needs_theme_name_resolution(value) -> bool:
    return not str(value or "").strip() or _is_numeric_theme_name(value)


def _theme_kline_summary(candidates: list[dict], recent_rank: dict | None = None) -> str:
    if not candidates:
        return "--"
    front = list(candidates[:3])
    limit_up_count = sum(1 for item in front if bool(item.get("is_limit_up")))
    avg_volume_ratio = sum(_to_float(item.get("volume_ratio")) for item in front) / max(len(front), 1)
    positions = [str(item.get("position_label") or "").strip() for item in front if str(item.get("position_label") or "").strip()]
    patterns: list[str] = []
    for item in front:
        for label in item.get("pattern_labels") or []:
            text = str(label or "").strip()
            if text and text not in patterns:
                patterns.append(text)
    signals: list[str] = []
    if limit_up_count >= 2:
        signals.append("前排连板强")
    elif limit_up_count == 1:
        signals.append("前排有板")
    if any("高位分歧" in item for item in positions):
        signals.append("高位分歧")
    elif any("高位强势" in item for item in positions):
        signals.append("高位强势")
    elif any("平台突破" in item or "突破" in item for item in patterns):
        signals.append("平台突破")
    elif any("低位" in item for item in positions):
        signals.append("低位启动")
    if avg_volume_ratio >= 1.8:
        signals.append(f"量能放大{avg_volume_ratio:.2f}")
    elif avg_volume_ratio >= 1.2:
        signals.append(f"量能温和放大{avg_volume_ratio:.2f}")
    if patterns:
        signals.append("/".join(patterns[:2]))
    if recent_rank:
        latest_pct = _to_float(recent_rank.get("latest_pct_chg"))
        latest_his_pct = _to_float(recent_rank.get("latest_his_pct_chg"))
        positive_days = int(recent_rank.get("positive_days") or 0)
        recent_days = int(recent_rank.get("recent_days") or 0)
        red_days = int(recent_rank.get("red_days") or 0)
        heat_name = str(recent_rank.get("latest_heat_name") or "").strip()
        if latest_his_pct >= 15:
            signals.append(f"5日累计强{latest_his_pct:.1f}%")
        elif latest_his_pct >= 5:
            signals.append(f"5日累计走强{latest_his_pct:.1f}%")
        elif latest_his_pct <= -5:
            signals.append(f"5日走弱{latest_his_pct:.1f}%")
        if recent_days > 0:
            signals.append(f"{recent_days}日{positive_days}涨{red_days}红")
        if latest_pct >= 5:
            signals.append(f"当日强{latest_pct:.1f}%")
        elif latest_pct <= -3:
            signals.append(f"当日转弱{latest_pct:.1f}%")
        if heat_name:
            signals.append(f"热度{heat_name}")
    return "；".join(signals[:3]) if signals else "--"


def _extract_hot_money_from_seat_summaries(seat_summary: list[str]) -> str:
    items: list[str] = []
    for seat in seat_summary or []:
        raw = str(seat or "").strip()
        if not raw:
            continue
        matched = None
        for rule in HOT_MONEY_SEAT_RULES:
            if rule.pattern in raw:
                matched = rule
                break
        if matched is None:
            continue
        direction = "买入" if "买入席位" in raw else "卖出" if "卖出席位" in raw else ""
        amount = ""
        marker = "净额 "
        if marker in raw:
            try:
                amount_value = float(raw.split(marker, 1)[1].strip())
                amount = f"{amount_value / 1e8:.2f}亿"
            except Exception:
                amount = ""
        parts = [matched.hot_money_name]
        if direction:
            parts.append(direction)
        if amount:
            parts.append(amount)
        text = "".join(parts).strip()
        if text and text not in items:
            items.append(text)
    return "、".join(items[:2]) if items else "--"


def _extract_hot_money_entries(seat_summary: list[str]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for seat in seat_summary or []:
        raw = str(seat or "").strip()
        if not raw:
            continue
        matched = None
        for rule in HOT_MONEY_SEAT_RULES:
            if rule.pattern in raw:
                matched = rule
                break
        if matched is None:
            continue
        side = "买入" if "买入席位" in raw else "卖出" if "卖出席位" in raw else "--"
        net_amount = 0.0
        marker = "净额 "
        if marker in raw:
            try:
                net_amount = float(raw.split(marker, 1)[1].strip())
            except Exception:
                net_amount = 0.0
        key = (matched.hot_money_name, side, f"{net_amount:.2f}")
        if key in seen:
            continue
        seen.add(key)
        result.append(
            {
                "hot_money_name": matched.hot_money_name,
                "side": side,
                "net_amount": net_amount,
            }
        )
    return result


def _summarize_institutions(seat_summary: list[str]) -> str:
    items: list[str] = []
    for seat in seat_summary or []:
        raw = str(seat or "").strip()
        if not raw:
            continue
        if "机构专用" not in raw and "机构" not in raw:
            continue
        direction = "买入" if "买入席位" in raw else "卖出" if "卖出席位" in raw else ""
        amount = ""
        marker = "净额 "
        if marker in raw:
            try:
                amount_value = float(raw.split(marker, 1)[1].strip())
                amount = f"{amount_value / 1e8:.2f}亿"
            except Exception:
                amount = ""
        label = "机构"
        if direction:
            label += direction
        if amount:
            label += amount
        if label not in items:
            items.append(label)
    return "、".join(items[:2]) if items else "--"


class RecapService:
    def __init__(self, repository: ReportRepository):
        self.repository = repository
        self._stock_detail_cache: dict[str, str] = {}

    def _stock_detail_path(self, stock_id: str) -> Path:
        return self.repository.config.project_root / "theme_data_complete" / "stock_details" / f"{_canonical_stock_id(stock_id)}_detail.json"

    def _load_stock_remark(self, stock_id: str) -> str:
        canonical = _canonical_stock_id(stock_id)
        if canonical in self._stock_detail_cache:
            return self._stock_detail_cache[canonical]
        path = self._stock_detail_path(stock_id)
        remark = ""
        try:
            obj = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            data = obj.get("data") or {}
            remark = str(data.get("remark") or "").strip()
        except Exception:
            remark = ""
        self._stock_detail_cache[canonical] = remark
        return remark

    def _parse_rank_order(self, candidate: dict) -> int:
        for item in candidate.get("evidence") or []:
            text = str(item)
            if text.startswith("题材内排序 "):
                try:
                    return int(text.replace("题材内排序 ", "").strip())
                except Exception:
                    return 0
        return 0

    def _describe_purity(self, candidate: dict) -> str:
        remark = _short_text(self._load_stock_remark(candidate.get("stock_id", "")))
        if remark:
            return f"主营关联：{remark}"
        rank_order = self._parse_rank_order(candidate)
        if candidate.get("role_label") == "龙头":
            return f"题材内排序 {rank_order or 1}，当前被识别为核心映射"
        if rank_order:
            return f"题材内排序 {rank_order}，映射度位于前排"
        return "主营映射待补充，当前按题材内排序给分"

    def _derive_board_nature(self, candidate: dict) -> str:
        open_price = _to_float(candidate.get("open_price"))
        high_price = _to_float(candidate.get("high_price"))
        low_price = _to_float(candidate.get("low_price"))
        close_price = _to_float(candidate.get("day_close_price"))
        pre_close = _to_float(candidate.get("pre_close"))
        open_pct = ((open_price / pre_close) - 1) * 100 if pre_close and open_price else 0.0
        is_limit_up = bool(candidate.get("is_limit_up"))
        if is_limit_up:
            if open_price and high_price and low_price and close_price:
                if abs(open_price - high_price) < 1e-4 and abs(open_price - low_price) < 1e-4 and abs(open_price - close_price) < 1e-4:
                    return "一字板"
            if open_pct >= 3:
                return "高开强封板"
            if open_pct > 0:
                return "高开换手板"
            if open_pct < 0:
                return "低开分歧板"
            return "平开换手板"
        pct_chg = _to_float(candidate.get("day_pct_chg"))
        if pct_chg >= 8:
            return "大阳领涨"
        if pct_chg >= 5:
            return "强势前排"
        if pct_chg >= 0:
            return "跟随上行"
        return "走弱掉队"

    def _describe_leading(self, candidate: dict) -> str:
        rank_order = self._parse_rank_order(candidate)
        pct_chg = _to_float(candidate.get("day_pct_chg"))
        board_nature = self._derive_board_nature(candidate)
        pieces = [f"封板性质 {board_nature}", f"涨幅 {pct_chg:.2f}%"]
        if rank_order:
            pieces.append(f"题材内排序 {rank_order}")
        return "；".join(pieces)

    def _describe_capital(self, candidate: dict) -> str:
        main_net_inflow = _to_float(candidate.get("main_net_inflow")) / 1e8
        day_amount = _to_float(candidate.get("day_amount")) / 1e8
        turnover_rate = _to_float(candidate.get("turnover_rate"))
        volume_ratio = _to_float(candidate.get("volume_ratio"))
        return (
            f"主力净流入 {main_net_inflow:.2f}亿；"
            f"成交额 {day_amount:.2f}亿；"
            f"换手 {turnover_rate:.2f}%；"
            f"量比 {volume_ratio:.2f}"
        )

    def _describe_structure(self, candidate: dict) -> str:
        position_label = str(candidate.get("position_label") or "--")
        pattern_labels = [str(x) for x in (candidate.get("pattern_labels") or []) if str(x).strip()]
        if pattern_labels:
            return f"{position_label}；{'/'.join(pattern_labels)}"
        return position_label

    def _describe_resilience(self, candidate: dict) -> str:
        position_label = str(candidate.get("position_label") or "")
        trend_strength = _to_float(candidate.get("trend_strength_score"))
        pct_chg = _to_float(candidate.get("day_pct_chg"))
        is_limit_up = bool(candidate.get("is_limit_up"))
        if position_label == "高位分歧":
            core = "处于高位分歧，承接要求更高"
        elif is_limit_up:
            core = "涨停收强，日内承接偏强"
        elif trend_strength >= 70:
            core = "趋势未破，回踩承接较稳"
        elif pct_chg >= 5:
            core = "前排保持强势，承接尚可"
        elif pct_chg >= 0:
            core = "红盘承接一般，需次日确认"
        else:
            core = "走弱承接偏弱"
        return f"按当日强度+趋势分定义；{core}"

    def _collect_subject_keys(self, *row_groups: list[dict]) -> list[str]:
        keys: set[str] = set()
        for rows in row_groups:
            for row in rows or []:
                subject_key = str(row.get("subject_key") or "").strip()
                if subject_key:
                    keys.add(subject_key)
        return sorted(keys)

    async def _resolve_theme_name_map(self, subject_keys: list[str]) -> dict[str, str]:
        resolver = getattr(self.repository, "fetch_theme_name_map", None)
        if not resolver:
            return {}
        try:
            return await resolver(subject_keys)
        except Exception:
            return {}

    async def _optional_fetch(self, method_name: str, default, *args, **kwargs):
        fetcher = getattr(self.repository, method_name, None)
        if not fetcher:
            return default
        return await fetcher(*args, **kwargs)

    def _apply_theme_names(self, rows: list[dict], theme_name_map: dict[str, str]) -> None:
        for row in rows or []:
            subject_key = str(row.get("subject_key") or "").strip()
            resolved_name = str(theme_name_map.get(subject_key) or "").strip()
            if resolved_name and (_needs_theme_name_resolution(row.get("theme_name")) or resolved_name != subject_key):
                row["theme_name"] = resolved_name

    async def build_pre_market_report(self, trade_date: str) -> MarketReport:
        plans = await self.repository.fetch_pre_market_execution_plans(trade_date, limit=30, include_avoid=False)
        recent_validations = await self.repository.fetch_recent_auction_signal_validations(trade_date, limit=12)

        highlights = []
        focus_themes = []
        watch_stocks = []
        invalid_lines = []
        auction_lines = []
        validation_lines = []

        for row in plans[:6]:
            highlights.append(f"{row['theme_name']}：{row['action_today']} / {row['action_bias']}")
        for row in plans:
            focus_themes.append(
                f"{row['theme_name']}：{row['theme_status']}；动作 {row['action_today']}；偏向 {row['action_bias']}"
            )
            if row.get("leader_stock_name"):
                watch_stocks.append(f"{row['theme_name']}：{row['watch_reason']}")
            if row.get("auction_signal_level"):
                reject = row.get("auction_hard_reject_reason") or "--"
                auction_lines.append(
                    f"{row['theme_name']}：{row.get('auction_focus_stock_name') or row.get('leader_stock_name') or '--'}；"
                    f"{row['auction_signal_level']} / {row.get('auction_signal_type') or '--'}；"
                    f"竞价动作 {row.get('auction_action_today') or '--'}；"
                    f"分数 {float(row.get('auction_signal_score') or 0):.2f}；"
                    f"否决 {reject}"
                )
            invalids = row.get("invalid_conditions") or []
            if invalids:
                invalid_lines.append(f"{row['theme_name']}：{invalids[0]}")
        for row in recent_validations:
            validation_lines.append(
                f"{row['theme_name']}：{row['stock_name']}；"
                f"{row['auction_signal_level']} / {row['signal_type']}；"
                f"收盘 {float(row.get('close_pct') or 0):.2f}% / "
                f"结果 {row['validation_result']}"
            )

        return MarketReport(
            report_type="pre_market",
            trade_date=trade_date,
            title=f"{trade_date} 盘前必读",
            summary="基于盘前承接验证真源表生成的次日执行清单。",
            highlights=highlights[:8],
            sections=[
                ("可做主线与支线", focus_themes[:12]),
                ("盘前重点盯盘个股", watch_stocks[:12]),
                ("竞价确认", auction_lines[:12]),
                ("竞价验证回看", validation_lines[:12]),
                ("失效条件", invalid_lines[:12]),
            ],
        )

    async def build_post_market_report(self, trade_date: str) -> MarketReport:
        market_environment = await self.repository.fetch_market_environment_judgement(trade_date)
        theme_environments = await self.repository.fetch_theme_environment_judgements(trade_date, limit=30)
        mainlines = await self.repository.fetch_mainline_judgements(trade_date, limit=30)
        cycles = await self.repository.fetch_cycle_judgements(trade_date, limit=30)
        transitions = await self._optional_fetch("fetch_mainline_state_transitions", [], trade_date, limit=40)
        theme_recent_ranks = await self._optional_fetch("fetch_theme_recent_rank_stats", [], trade_date, lookback_days=5)
        candidates = await self.repository.fetch_leader_candidates(trade_date, limit=120)
        llm_judgements = await self.repository.fetch_leader_llm_judgements(trade_date, limit=1000)
        dragon_tigers = await self.repository.fetch_dragon_tiger_objects(trade_date, limit=120)
        recent_dragon_tiger_stats = await self._optional_fetch("fetch_recent_dragon_tiger_stats", [], trade_date, lookback_days=7)
        theme_capital_flows = await self._optional_fetch("fetch_theme_capital_flow_top", [], trade_date, limit=50)
        stock_capital_flows = await self._optional_fetch("fetch_stock_main_net_inflow_top", [], trade_date, limit=20)
        money_flows = await self.repository.fetch_money_flow_enhanced(trade_date, limit=120)
        abnormal_signals = await self.repository.fetch_stock_abnormal_signals(trade_date, limit=120)
        hot_money_activities = await self.repository.fetch_hot_money_activities(trade_date, limit=300)
        subject_theme_links = await self.repository.fetch_subject_theme_links_for_stocks(
            trade_date,
            [str(row["stock_id"]) for row in dragon_tigers],
        )

        theme_name_map = await self._resolve_theme_name_map(
            self._collect_subject_keys(
                theme_environments,
                mainlines,
                cycles,
                transitions,
                candidates,
                llm_judgements,
                theme_capital_flows,
                stock_capital_flows,
                money_flows,
                abnormal_signals,
                hot_money_activities,
                subject_theme_links,
            )
        )
        for rows in (
            theme_environments,
            mainlines,
            cycles,
            transitions,
            candidates,
            llm_judgements,
            theme_capital_flows,
            stock_capital_flows,
            money_flows,
            abnormal_signals,
            hot_money_activities,
            subject_theme_links,
        ):
            self._apply_theme_names(rows, theme_name_map)

        cycle_map = {row["subject_key"]: row for row in cycles}
        candidate_map: dict[str, list[dict]] = {}
        for row in candidates:
            candidate_map.setdefault(row["subject_key"], []).append(row)
        stock_theme_links: dict[str, list[dict]] = {}
        for row in subject_theme_links:
            stock_theme_links.setdefault(_canonical_stock_id(row["stock_id"]), []).append(row)
        llm_map = {row["subject_key"]: row for row in llm_judgements}
        dragon_tiger_map = {_canonical_stock_id(row["stock_id"]): row for row in dragon_tigers}
        hot_money_map: dict[tuple[str, str], list[dict]] = {}
        for row in hot_money_activities:
            hot_money_map.setdefault((str(row["subject_key"]), _canonical_stock_id(row["stock_id"])), []).append(row)
        dragon_tiger_stat_map = {
            _canonical_stock_id(row["stock_id"]): row
            for row in recent_dragon_tiger_stats
        }
        money_flow_map = {
            (row["subject_key"], _canonical_stock_id(row["stock_id"])): row
            for row in money_flows
        }
        mainline_alive_map = {str(row["subject_key"]): bool(row.get("final_mainline_alive")) for row in mainlines}
        mainline_strength_map = {str(row["subject_key"]): float(row.get("mainline_strength_score") or 0.0) for row in mainlines}
        theme_capital_flow_map = {
            str(row["subject_key"]): row
            for row in theme_capital_flows
        }
        theme_recent_rank_map = {
            str(row["subject_key"]): row
            for row in theme_recent_ranks
        }

        theme_lines = []
        cycle_lines = []
        transition_lines = []
        leader_lines = []
        theme_capital_flow_lines = []
        stock_capital_flow_lines = []
        dragon_tiger_lines = []
        money_flow_lines = []
        abnormal_lines = []
        watchlist_lines = []
        theme_environment_lines = []
        market_environment_lines = []
        if market_environment:
            market_environment_lines.append(
                f"市场偏向 {market_environment['market_bias']}；动作 {market_environment['action_bias']}；环境总分 {float(market_environment.get('market_health_score') or 0):.2f}"
            )
            market_environment_lines.append(
                f"{market_environment.get('breadth_status', '--')}；{market_environment.get('short_term_sentiment_status', '--')}；"
                f"{market_environment.get('relay_sentiment_status', '--')}；{market_environment.get('intraday_fade_status', '--')}"
            )
            for item in (market_environment.get("evidence") or [])[:4]:
                market_environment_lines.append(str(item))

        def _llm_reason_map(subject_key: str) -> dict[str, dict]:
            row = llm_map.get(subject_key) or {}
            judgement_json = row.get("judgement_json") or {}
            if isinstance(judgement_json, str):
                try:
                    judgement_json = json.loads(judgement_json)
                except Exception:
                    judgement_json = {}
            items = judgement_json.get("per_stock_reasoning") or []
            result: dict[str, dict] = {}
            for item in items:
                stock_id = _canonical_stock_id(item.get("stock_id"))
                if not stock_id:
                    continue
                result[stock_id] = {
                    "role_label": str(item.get("role_label") or "").strip(),
                    "reason": str(item.get("reason") or "").strip(),
                }
            return result

        def _llm_final_role(subject_key: str, stock_id: str) -> str:
            row = llm_map.get(subject_key) or {}
            canonical = _canonical_stock_id(stock_id)
            mapping = {
                _canonical_stock_id(row.get("leader_stock_id")): "龙头",
                _canonical_stock_id(row.get("runner_up_stock_id")): "龙二",
                _canonical_stock_id(row.get("card_position_stock_id")): "卡位",
                _canonical_stock_id(row.get("supplement_stock_id")): "补涨",
                _canonical_stock_id(row.get("eliminated_stock_id")): "淘汰",
            }
            return mapping.get(canonical, "")

        def _ordered_candidates(subject_key: str) -> list[dict]:
            rows = list(candidate_map.get(subject_key, []))
            llm_row = llm_map.get(subject_key) or {}
            preferred_ids = [
                _canonical_stock_id(llm_row.get("leader_stock_id")),
                _canonical_stock_id(llm_row.get("runner_up_stock_id")),
                _canonical_stock_id(llm_row.get("card_position_stock_id")),
                _canonical_stock_id(llm_row.get("supplement_stock_id")),
                _canonical_stock_id(llm_row.get("eliminated_stock_id")),
            ]
            preferred_ids = [item for item in preferred_ids if item]
            if not preferred_ids:
                return rows
            by_id = {_canonical_stock_id(item["stock_id"]): item for item in rows}
            ordered: list[dict] = []
            seen: set[str] = set()
            for stock_id in preferred_ids:
                candidate = by_id.get(stock_id)
                if not candidate:
                    continue
                ordered.append(candidate)
                seen.add(stock_id)
            for item in rows:
                stock_id = _canonical_stock_id(item["stock_id"])
                if stock_id in seen:
                    continue
                ordered.append(item)
            return ordered

        for row in theme_environments:
            theme_environment_lines.append(
                f"{row['theme_name']}：{row['board_health_status']}；{row['board_effect_status']}；"
                f"{row['leader_support_status']}；{row['follow_strength_status']}；动作 {row['action_bias']}"
            )

        for row in theme_capital_flows:
            cycle = cycle_map.get(row["subject_key"], {})
            theme_env = next((item for item in theme_environments if str(item.get("subject_key")) == str(row["subject_key"])), {})
            kline_summary = _theme_kline_summary(
                _ordered_candidates(row["subject_key"]),
                theme_recent_rank_map.get(str(row["subject_key"])),
            )
            theme_capital_flow_lines.append(
                f"{row['theme_name']}：subject_key {row['subject_key']}；状态 {row.get('final_cycle_state', '--')}；"
                f"总净流入 {_summarize_in_billions(row.get('main_net_inflow_sum'))}；"
                f"前3净流入 {_summarize_in_billions(row.get('top3_main_net_inflow_sum'))}；"
                f"龙头净流入 {_summarize_in_billions(row.get('leader_main_net_inflow'))}；"
                f"流入股 {int(row.get('positive_inflow_stock_count') or 0)}；"
                f"题材K线 {kline_summary}；"
                f"阶段 {cycle.get('primary_cycle_stage', '--')}；动作 {theme_env.get('action_bias', '--')}"
            )

        for row in stock_capital_flows:
            stock_capital_flow_lines.append(
                f"{row['stock_name']}({row['stock_id']})：{row['theme_name']}；"
                f"主力净流入 {_summarize_in_billions(row.get('main_net_inflow'))}；"
                f"题材内排名 {int(row.get('rank_order') or 0)}；"
                f"涨幅 {float(row.get('pct_chg') or 0):.2f}%；"
                f"龙头 {'是' if row.get('is_leader') else '否'}；"
                f"flag {_flag_text(row.get('current_flag'))}"
            )
        for row in mainlines:
            cycle = cycle_map.get(row["subject_key"], {})
            theme_capital = theme_capital_flow_map.get(str(row["subject_key"]), {})
            llm_reasoning = _llm_reason_map(row["subject_key"])
            theme_kline_summary = _theme_kline_summary(
                _ordered_candidates(row["subject_key"]),
                theme_recent_rank_map.get(str(row["subject_key"])),
            )
            theme_lines.append(
                f"{row['theme_name']}：subject_key {row['subject_key']}；层级 main；主线存活 {'是' if row.get('final_mainline_alive') else '否'}；"
                f"状态 {row.get('final_cycle_state', '--')}；"
                f"主线强度 {float(row.get('mainline_strength_score') or 0):.2f}；"
                f"退潮风险 {float(row.get('fade_risk_score') or 0):.2f}；"
                f"总净流入 {_summarize_in_billions(theme_capital.get('main_net_inflow_sum'))}；"
                f"龙头净流入 {_summarize_in_billions(theme_capital.get('leader_main_net_inflow'))}；"
                f"题材K线 {theme_kline_summary}"
            )
            cycle_lines.append(
                f"{row['theme_name']}：阶段 {row.get('final_cycle_state', cycle.get('primary_cycle_stage', '--'))}；"
                f"退潮观察 {'是' if row.get('fade_watch') else '否'}；退潮确认 {'是' if row.get('fade_confirmed') else '否'}"
            )
            for candidate in _ordered_candidates(row["subject_key"])[:4]:
                flow = money_flow_map.get((row["subject_key"], _canonical_stock_id(candidate["stock_id"])))
                flow_suffix = ""
                if flow:
                    flow_suffix = f"；资金 {flow['money_flow_tier']} / {flow['role_enhanced']}"
                kline_parts = []
                if candidate.get("position_label"):
                    kline_parts.append(f"K线位置 {candidate['position_label']}")
                pattern_labels = candidate.get("pattern_labels") or []
                if pattern_labels:
                    kline_parts.append(f"K线形态 {'/'.join(str(x) for x in pattern_labels)}")
                score_parts = [
                    f"正宗性 {float(candidate.get('purity_score') or 0):.2f}×25%｜{self._describe_purity(candidate)}",
                    f"领涨性 {float(candidate.get('leading_score') or 0):.2f}×25%｜{self._describe_leading(candidate)}",
                    f"资金量能 {float(candidate.get('capital_score') or 0):.2f}×20%｜{self._describe_capital(candidate)}",
                    f"结构位置 {float(candidate.get('structure_score') or 0):.2f}×15%｜{self._describe_structure(candidate)}",
                    f"抗跌承接 {float(candidate.get('resilience_score') or 0):.2f}×15%｜{self._describe_resilience(candidate)}",
                ]
                evidence_items = [str(item) for item in (candidate.get("evidence") or []) if str(item).strip()]
                evidence_summary = "；".join(evidence_items[:4]) if evidence_items else "--"
                llm_item = llm_reasoning.get(_canonical_stock_id(candidate["stock_id"])) or {}
                llm_row = llm_map.get(row["subject_key"]) or {}
                raw_llm_role = (
                    llm_item.get("role_label")
                    or _llm_final_role(row["subject_key"], candidate["stock_id"])
                    or ""
                )
                display_role = raw_llm_role if raw_llm_role else str(candidate.get("role_label") or "--")

                llm_reason = _sanitize_inline_text(
                    llm_item.get("reason")
                    or llm_row.get("reasoning_summary")
                    or "未生成LLM个股理由，当前回退规则候选说明"
                )
                leader_status = _sanitize_inline_text(
                    llm_row.get("leader_status")
                    or ("未生成LLM裁决（回退规则角色）" if not raw_llm_role else "")
                    or "--"
                )
                confirmation_basis = _sanitize_inline_text(
                    llm_row.get("confirmation_basis")
                    or ("规则候选回退（当日LLM未覆盖该题材）" if not raw_llm_role else "")
                    or "--"
                )
                llm_role = raw_llm_role or display_role
                kline_suffix = f"；{'；'.join(kline_parts)}" if kline_parts else ""
                leader_lines.append(
                    f"{row['theme_name']}：{display_role} {candidate['stock_name']}({candidate['stock_id']})；"
                    f"综合分 {float(candidate.get('composite_score') or 0):.2f}；"
                    f"{'；'.join(score_parts)}"
                    f"{flow_suffix}{kline_suffix}；LLM裁决角色 {llm_role}；LLM确认状态 {leader_status}；确认依据 {confirmation_basis}；LLM理由 {llm_reason}；评分依据 {evidence_summary}"
                )
            leader = next(
                (candidate for candidate in candidate_map.get(row["subject_key"], []) if int(candidate.get("candidate_rank") or 0) == 1),
                None,
            )
            if leader:
                flow = money_flow_map.get((row["subject_key"], _canonical_stock_id(leader["stock_id"])))
                if flow:
                    explanation_lines = [str(x) for x in (flow.get("explanation") or []) if str(x).strip()]
                    explanation_core = explanation_lines[0] if explanation_lines else ""
                    kline_lines = [line for line in explanation_lines if line.startswith("K线")]
                    explanation = "；".join([part for part in [explanation_core, *kline_lines] if part])
                    money_flow_lines.append(
                        f"{row['theme_name']}：{leader['stock_name']}；{flow['role_enhanced']}；资金分层 {flow['money_flow_tier']}；得分 {float(flow.get('money_flow_score') or 0):.2f}；{explanation}"
                    )

        transition_counts = {"upgrade": 0, "downgrade": 0, "fade": 0, "flat": 0}
        for row in transitions:
            t = str(row.get("transition_type") or "flat")
            transition_counts[t] = transition_counts.get(t, 0) + 1
            flags = [str(x) for x in (row.get("trigger_flags") or []) if str(x).strip()]
            transition_lines.append(
                f"{row['theme_name']}：{row.get('from_state', '--')} -> {row.get('to_state', '--')}；"
                f"迁移 {t}；置信度 {float(row.get('confidence') or 0):.2f}；"
                f"触发 {('/'.join(flags) if flags else '--')}"
            )

        dragon_seen: set[tuple[str, str]] = set()
        dragon_hot_money_groups: dict[str, list[str]] = {}
        for dragon_tiger in dragon_tigers:
            stock_id = _canonical_stock_id(dragon_tiger["stock_id"])
            linked_candidates = stock_theme_links.get(stock_id, [])
            if not linked_candidates:
                continue
            seat_summary = dragon_tiger.get("seat_summary") or []
            best_linked = sorted(
                linked_candidates,
                key=lambda item: (
                    0 if mainline_alive_map.get(str(item.get("subject_key") or "")) else 1,
                    -mainline_strength_map.get(str(item.get("subject_key") or ""), 0.0),
                    0 if bool(item.get("is_leader")) else 1,
                    int(item.get("rank_order") or 9999),
                    str(item.get("theme_name") or ""),
                ),
            )[0]
            for linked in linked_candidates:
                hot_items = sorted(
                    hot_money_map.get((str(linked["subject_key"]), stock_id), []),
                    key=lambda item: abs(float(item.get("net_amount") or 0.0)),
                    reverse=True,
                )[:2]
                derived_hot_items = [
                    {
                        "hot_money_name": item["hot_money_name"],
                        "side": item["side"],
                        "net_amount": float(item.get("net_amount") or 0.0),
                    }
                    for item in hot_items
                ] or _extract_hot_money_entries(seat_summary)
                institution_line = _summarize_institutions(seat_summary)
                for hot in derived_hot_items:
                    key = (str(hot["hot_money_name"]), stock_id)
                    if key in dragon_seen:
                        continue
                    dragon_seen.add(key)
                    dragon_hot_money_groups.setdefault(str(hot["hot_money_name"]), []).append(
                        f"{best_linked['theme_name']} / {best_linked['stock_name']}({best_linked['stock_id']}) / {hot['side']}{_summarize_in_billions(hot.get('net_amount'))}"
                    )

        for hot_money_name, items in sorted(dragon_hot_money_groups.items(), key=lambda x: x[0]):
            dragon_tiger_lines.append(
                f"{hot_money_name}：{'；'.join(items[:8])}"
            )

        for row in abnormal_signals:
            labels = [str(x) for x in (row.get("abnormal_labels") or []) if str(x).strip()]
            evidence = [str(x) for x in (row.get("evidence") or []) if str(x).strip()]
            hot_names = [str(x) for x in (row.get("hot_money_buy_names") or []) if str(x).strip()]
            capital_note_parts = []
            if _to_float(row.get("main_net_inflow")) > 0:
                capital_note_parts.append(
                    f"主力净流入 {_summarize_in_billions(row.get('main_net_inflow'))}"
                )
            if int(row.get("main_net_inflow_rank_in_theme") or 0) > 0:
                capital_note_parts.append(f"题材内净流入排名 {int(row.get('main_net_inflow_rank_in_theme') or 0)}")
            if hot_names:
                capital_note_parts.append(f"游资买入 {'/'.join(hot_names[:3])}")
            if _to_float(row.get("institution_net_buy")) > 0 and int(row.get("institution_seat_count") or 0) > 0:
                capital_note_parts.append(
                    f"机构净买 {_summarize_in_billions(row.get('institution_net_buy'))} / {int(row.get('institution_seat_count') or 0)}席"
                )
            abnormal_lines.append(
                f"{row['theme_name']}：{row['stock_name']}({row['stock_id']})；"
                f"异动分 {float(row.get('abnormal_composite_score') or 0):.2f}；"
                f"换手率 {float(row.get('turnover_rate') or 0):.2f}%；"
                f"量比 {next((item.replace('量比 ', '') for item in evidence if item.startswith('量比 ')), '--')}；"
                f"成交量/50日均量 {float(row.get('volume_ratio_to_ma50') or 0):.2f}；"
                f"资金 {' / '.join(capital_note_parts) if capital_note_parts else '--'}；"
                f"标签 {'/'.join(labels) if labels else '--'}；"
                f"结论 {row.get('conclusion') or '--'}"
            )

        watchlist_entries: list[tuple[int, str]] = []
        seen_watch_keys: set[tuple[str, str, str]] = set()

        def push_watch(category: str, priority: int, line: str, subject_key: str, stock_id: str) -> None:
            key = (category, str(subject_key), _canonical_stock_id(stock_id))
            if key in seen_watch_keys:
                return
            seen_watch_keys.add(key)
            watchlist_entries.append((priority, f"{category}：{line}"))

        llm_role_map = {
            (
                str(subject_key),
                _canonical_stock_id(stock_id),
            ): (item.get("role_label") or _llm_final_role(subject_key, stock_id) or "--")
            for subject_key, items in candidate_map.items()
            for item in items
            for stock_id in [_canonical_stock_id(item.get("stock_id"))]
        }

        cycle_stage_map = {
            str(row["subject_key"]): str(row.get("primary_cycle_stage") or "--")
            for row in cycles
        }
        theme_env_map = {
            str(row["subject_key"]): row
            for row in theme_environments
        }
        abnormal_map = {
            (str(row["subject_key"]), _canonical_stock_id(row["stock_id"])): row
            for row in abnormal_signals
        }

        for subject_key, items in candidate_map.items():
            cycle_stage = cycle_stage_map.get(str(subject_key), "--")
            mainline_alive = mainline_alive_map.get(str(subject_key), False)
            theme_env = theme_env_map.get(str(subject_key), {})
            action_bias = str(theme_env.get("action_bias") or "--")
            for candidate in items[:4]:
                stock_id = _canonical_stock_id(candidate["stock_id"])
                llm_role = llm_role_map.get((str(subject_key), stock_id), str(candidate.get("role_label") or "--"))
                abnormal = abnormal_map.get((str(subject_key), stock_id), {})
                dragon_stats = dragon_tiger_stat_map.get(stock_id, {})
                recent_dragon_days = int(dragon_stats.get("dragon_tiger_days_lookback") or 0)
                current_flag = candidate.get("current_flag")
                pattern_labels = list(candidate.get("pattern_labels") or [])
                pattern_text = _pattern_text(pattern_labels)
                position_label = str(candidate.get("position_label") or "--")
                volume_ratio = _to_float(candidate.get("volume_ratio"))
                is_limit_up = bool(candidate.get("is_limit_up"))
                abnormal_score = _to_float(abnormal.get("abnormal_composite_score"))
                abnormal_labels = [str(x) for x in (abnormal.get("abnormal_labels") or []) if str(x).strip()]
                theme_name = str(
                    candidate.get("theme_name")
                    or theme_name_map.get(str(subject_key))
                    or subject_key
                )
                stock_name = candidate["stock_name"]
                catalyst = abnormal.get("conclusion") or "--"

                if recent_dragon_days >= 2 and llm_role in {"龙头", "龙二", "卡位"}:
                    push_watch(
                        "龙虎榜弱转强观察",
                        10,
                        f"{theme_name}｜{stock_name}({stock_id})｜subject_key {subject_key}｜角色 {llm_role}｜近7日龙虎榜 {recent_dragon_days} 天｜"
                        f"阶段 {cycle_stage}｜位置 {position_label}｜形态 {pattern_text}｜flag {_flag_text(current_flag)}｜"
                        f"催化 {catalyst}",
                        str(subject_key),
                        stock_id,
                    )

                if (
                    mainline_alive
                    and action_bias in {"可主做", "可做弱转强", "可观察"}
                    and llm_role in {"龙头", "龙二", "卡位"}
                    and (volume_ratio >= 1.2 or abnormal_score >= 60 or int(current_flag or 0) > 2)
                ):
                    push_watch(
                        "弱转强观察",
                        20,
                        f"{theme_name}｜{stock_name}({stock_id})｜subject_key {subject_key}｜角色 {llm_role}｜阶段 {cycle_stage}｜动作 {action_bias}｜"
                        f"量比 {volume_ratio:.2f}｜形态 {pattern_text}｜flag {_flag_text(current_flag)}｜"
                        f"异动 {'/'.join(abnormal_labels[:3]) if abnormal_labels else '--'}",
                        str(subject_key),
                        stock_id,
                    )

                if (
                    mainline_alive
                    and llm_role in {"龙头", "龙二", "卡位"}
                    and (is_limit_up or volume_ratio >= 1.5 or recent_dragon_days >= 1)
                ):
                    push_watch(
                        "强势延续观察",
                        30,
                        f"{theme_name}｜{stock_name}({stock_id})｜subject_key {subject_key}｜角色 {llm_role}｜阶段 {cycle_stage}｜"
                        f"涨停 {'是' if is_limit_up else '否'}｜量比 {volume_ratio:.2f}｜近7日龙虎榜 {recent_dragon_days} 天｜"
                        f"形态 {pattern_text}",
                        str(subject_key),
                        stock_id,
                    )

                if (
                    int(current_flag or 0) == -1
                    or (
                        candidate.get("candidate_rank", 99) >= 2
                        and volume_ratio >= 1.3
                        and pattern_labels
                    )
                ):
                    push_watch(
                        "潜力预备观察",
                        40,
                        f"{theme_name}｜{stock_name}({stock_id})｜subject_key {subject_key}｜位置 {position_label}｜形态 {pattern_text}｜"
                        f"量比 {volume_ratio:.2f}｜flag {_flag_text(current_flag)}｜"
                        f"异动分 {abnormal_score:.2f}",
                        str(subject_key),
                        stock_id,
                    )

        watchlist_lines = [line for _, line in sorted(watchlist_entries, key=lambda item: (item[0], item[1]))][:24]

        sections = [
            ("大盘环境总结", market_environment_lines[:8]),
            ("板块环境总结", theme_environment_lines[:15]),
            ("主线与支线", theme_lines[:15]),
        ]
        if theme_capital_flow_lines:
            sections.append(("主线资金流入前10", theme_capital_flow_lines[:10]))
        sections.append(("周期与动作", cycle_lines[:15]))
        if transition_lines:
            sections.append(("主线迁移监控", transition_lines[:20]))
        sections.append(("强势股分层", leader_lines[:20]))
        if watchlist_lines:
            sections.append(("次日观察清单", watchlist_lines[:24]))
        if stock_capital_flow_lines:
            sections.append(("主线股票资金流入前20", stock_capital_flow_lines[:20]))
        sections.extend(
            [
                ("当日异动股与资金行为", abnormal_lines[:30]),
                ("资金行为增强", money_flow_lines[:20]),
                ("龙虎榜", dragon_tiger_lines[:40]),
            ]
        )

        return MarketReport(
            report_type="post_market",
            trade_date=trade_date,
            title=f"{trade_date} 盘后复盘",
            summary="基于主线、周期、龙头三张真源表生成的盘后复盘摘要。",
            highlights=(
                market_environment_lines[:2]
                + [
                    (
                        f"主线迁移：升级 {transition_counts.get('upgrade', 0)} / "
                        f"降级 {transition_counts.get('downgrade', 0)} / "
                        f"退潮 {transition_counts.get('fade', 0)} / "
                        f"平级 {transition_counts.get('flat', 0)}"
                    )
                ]
                + theme_lines[:3]
            )[:6],
            sections=sections,
        )
