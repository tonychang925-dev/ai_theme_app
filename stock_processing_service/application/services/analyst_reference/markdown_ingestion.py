"""Phase 4.1 — Markdown Reference Ingestion.

Parses DeepSeek-structured analyst recap markdown files into
AnalystReferenceRecord.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .contracts import (
    AnalystReferenceRecord,
    EmotionLabel,
    ExternalEnvironment,
    LeaderState,
    LimitUpAttribution,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
    ThemeLifecycleEntry,
)


class MarkdownReferenceParser:
    """Parse analyst recap Markdown (DeepSeek structured format)."""

    def parse_file(self, path: str | Path, trade_date: date | None = None) -> AnalystReferenceRecord:
        """Parse a DeepSeek-structured analyst recap markdown file."""
        text = Path(path).read_text(encoding="utf-8")

        # Try to extract trade_date from content if not provided
        if trade_date is None:
            # Look for the FIRST occurrence of a date near "日期:" label
            m = re.search(r'日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)
            if m:
                trade_date = date.fromisoformat(m.group(1))
            elif re.search(r'7月7日|7/7', text[:500]):
                # Heuristic: file name or first section contains the date
                trade_date = date(2026, 7, 7)
            elif re.search(r'7月8日|7/8|7:8', text[:500]):
                trade_date = date(2026, 7, 8)
            else:
                # Fallback: first JSON date block
                m = re.search(r'"date":\s*"(\d{4}-\d{2}-\d{2})"', text)
                if m:
                    trade_date = date.fromisoformat(m.group(1))

        if trade_date is None:
            raise ValueError("Could not determine trade_date from document")

        record = AnalystReferenceRecord(
            trade_date=trade_date,
            source_type="markdown",
            source_path=str(path),
            raw_text=text[:10000],
        )

        # ── Try to parse the structured JSON sections ──
        json_blocks = re.findall(r'```\s*json\s*\n(.*?)\n```', text, re.DOTALL)
        json_data: dict = {}
        for block in json_blocks:
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                    # Merge identifiable sections
                    if "date" in data:
                        json_data["root"] = data
                    elif "indicator" in data:
                        json_data[data["indicator"]] = data
                    elif "relay_ecology" in data:
                        json_data["relay"] = data.get("relay_ecology", {})
                    elif "analyst_conclusion" in data:
                        json_data["conclusion"] = data.get("analyst_conclusion", {})
                    elif "external_market" in data:
                        json_data["external"] = data
            except json.JSONDecodeError:
                pass

        # ── Extract MarketFacts ──
        facts = self._parse_facts(text, json_data)
        record.market_facts = facts

        # ── Extract EmotionLabel ──
        emotion = self._parse_emotion(text, json_data, trade_date)
        record.emotion_label = emotion

        # ── Extract RelayLabel ──
        relay = self._parse_relay(text, json_data)
        record.relay_label = relay

        # ── Extract Strategy ──
        strategy = self._parse_strategy(text, json_data)
        record.strategy_label = strategy

        # ── Extract Theme Lifecycle (institution themes) ──
        record.theme_lifecycle = self._parse_theme_lifecycle(text)

        # ── Extract LimitUp Attribution ──
        record.limitup_attribution = self._parse_limitup_attr(text)

        # ── Extract Leader State ──
        record.leader_state = self._parse_leaders(text)

        # ── External Environment ──
        record.external_env = self._parse_external(text, json_data)

        # ── Status ──
        if facts.limit_up_count and emotion.market_phase:
            record.extraction_status = "complete"
            record.confidence = 0.90
        else:
            record.extraction_status = "partial"
            record.confidence = 0.60
            record.needs_review_fields = [
                f for f in ["limit_up_count", "market_phase"]
                if not getattr(facts, "limit_up_count", None) or not emotion.market_phase
            ]

        return record

    # ── Fact extractors ──

    def _parse_facts(self, text: str, json_data: dict) -> MarketFacts:
        facts = MarketFacts()

        # Try JSON first
        power_data = json_data.get("大盘势能", {})
        if power_data:
            dates = power_data.get("dates", [])
            values = power_data.get("limit_up_count", [])
            if dates and values:
                facts.limit_up_count = values[-1]  # last date is current
            chain_vals = power_data.get("chain_board_count", [])
            if chain_vals:
                facts.chain_board_count = chain_vals[-1]
            ratio_vals = power_data.get("market_up_ratio", [])
            if ratio_vals:
                facts.market_up_ratio = ratio_vals[-1]
            loss_vals = power_data.get("loss_effect_ratio", [])
            if loss_vals:
                facts.loss_effect_ratio = loss_vals[-1]
            comp_vals = power_data.get("composite_score", [])
            if comp_vals:
                facts.composite_score = comp_vals[-1]

        # Try root JSON
        root = json_data.get("root", {})
        if not facts.limit_up_count and "limit_up" in root:
            facts.limit_up_count = int(root["limit_up"])
        if not facts.max_board_height and "max_board" in root:
            facts.max_board_height = int(root["max_board"])

        # Try section 17 JSON
        for block in re.findall(r'```\s*json\s*\n(.*?)\n```', text, re.DOTALL):
            try:
                d = json.loads(block)
                f = d.get("facts", {})
                if f.get("limit_up_count"):
                    facts = MarketFacts(
                        limit_up_count=f.get("limit_up_count"),
                        chain_board_count=f.get("chain_board_count"),
                        max_board_height=f.get("max_board_height"),
                        active_capital_yi=f.get("active_capital_yi"),
                        market_up_ratio=f.get("market_up_ratio"),
                        loss_effect_ratio=f.get("loss_effect_ratio"),
                    )
                    break
            except json.JSONDecodeError:
                pass

        return facts

    def _parse_emotion(self, text: str, json_data: dict, trade_date: date) -> EmotionLabel:
        emotion = EmotionLabel()

        # Try root JSON
        root = json_data.get("root", {})
        if root:
            emotion.market_phase = root.get("market_phase", root.get("phase", ""))
            emotion.risk_level = root.get("risk", "")
            emotion.strategy = root.get("strategy", "")
            if "emotion_momentum" in root:
                emotion.emotion_momentum = float(root["emotion_momentum"])

        # Try section 14 JSON
        for block in re.findall(r'```\s*json\s*\n(.*?)\n```', text, re.DOTALL):
            try:
                d = json.loads(block)
                if "phase" in d and "risk" in d and "strategy" in d:
                    emotion.market_phase = d.get("phase", "")
                    emotion.risk_level = d.get("risk", "")
                    emotion.strategy = d.get("strategy", "")
                    break
            except json.JSONDecodeError:
                pass

        # Try emotion_label JSON
        em = json_data.get("emotion_label", {}) or json_data.get("emotion", {})
        if isinstance(em, dict):
            if em.get("phase"):
                emotion.market_phase = em["phase"]
            if em.get("risk"):
                emotion.risk_level = em["risk"]
            if em.get("emotion_momentum"):
                emotion.emotion_momentum = float(em["emotion_momentum"])
            if em.get("cycle_score"):
                emotion.cycle_score = int(em["cycle_score"])

        # Try regex from text
        if not emotion.emotion_momentum:
            m = re.search(r'"emotion_momentum":\s*(-?[\d.]+)', text)
            if m:
                emotion.emotion_momentum = float(m.group(1))

        return emotion

    def _parse_relay(self, text: str, json_data: dict) -> RelayLabel:
        relay = RelayLabel()

        # Try relay JSON section
        rl = json_data.get("relay", {}) or json_data.get("relay_label", {})
        if isinstance(rl, dict):
            relay.max_board_height = rl.get("max_board_height", rl.get("max_board"))
            relay.max_board_stock = rl.get("max_board_stock", "")
            relay.first_board_success_rate = rl.get("first_board_success_rate")
            relay.promotion_1_to_2 = rl.get("promotion_1_to_2")
            relay.promotion_2_to_3 = rl.get("promotion_2_to_3")
            relay.promotion_3_to_4 = rl.get("promotion_3_to_4")

        # Try root JSON
        root = json_data.get("root", {})
        if root.get("relay"):
            r = root["relay"]
            relay.max_board_height = r.get("max_board", relay.max_board_height)
            relay.promotion_1_to_2 = r.get("promotion_1_to_2", relay.promotion_1_to_2)
            relay.promotion_2_to_3 = r.get("promotion_2_to_3", relay.promotion_2_to_3)

        return relay

    def _parse_strategy(self, text: str, json_data: dict) -> StrategyLabel:
        strategy = StrategyLabel()

        # Try strategy_label JSON
        sl = json_data.get("strategy_label", {})
        if isinstance(sl, dict):
            strategy.allowed = sl.get("allowed", [])
            strategy.forbidden = sl.get("forbidden", [])
            strategy.watch_points = sl.get("watch_points", [])
            strategy.summary = sl.get("summary", "")

        # Try conclusion JSON
        conc = json_data.get("conclusion", {})
        if isinstance(conc, dict) and conc.get("strategy"):
            strategy.summary = conc["strategy"]

        # Try root JSON
        root = json_data.get("root", {})
        if root.get("strategy") and not strategy.summary:
            strategy.summary = root["strategy"]

        return strategy

    def _parse_theme_lifecycle(self, text: str) -> list[ThemeLifecycleEntry]:
        """Parse institution theme lifecycle tables from sections 9/10."""
        entries: list[ThemeLifecycleEntry] = []
        seen = set()

        # Find tables with 调整/启动 patterns
        for line in text.split("\n"):
            # Match lines like "| 华为昇腾950 | 调整第2天 | ..."
            m = re.match(r'\|\s*([^\s|]+[^\d|]+?)\s*\|\s*(.+?)\s*\|', line)
            if m:
                name = m.group(1).strip()
                state_text = m.group(2).strip()
                if name in seen or not name or len(name) > 20:
                    continue
                # Skip header rows
                if name in ("板块方向", "方向", "题材"):
                    continue

                seen.add(name)
                # Extract state and day count
                state = "观察"
                day_count = 0
                state_match = re.match(r'(调整|启动|修复|关注|观察).*?(\d+)', state_text)
                if state_match:
                    state = state_match.group(1)
                    day_count = int(state_match.group(2))

                entries.append(ThemeLifecycleEntry(
                    theme_name=name, state=state, day_count=day_count))

        return entries

    def _parse_limitup_attr(self, text: str) -> list[LimitUpAttribution]:
        """Parse limit-up classification. Simplified — extracts from sections 12/13."""
        attr_list: list[LimitUpAttribution] = []
        current_theme = ""
        seen = set()

        for line in text.split("\n"):
            # "## 13.2 算力 / 半导体产业链" or "## 机器人"
            m = re.match(r'#+\s*[\d.]*\s*(.+?)(?:产业链|概念|板块)?\s*$', line)
            if m:
                current_theme = m.group(1).strip()
                if current_theme and current_theme not in seen and len(current_theme) < 20:
                    seen.add(current_theme)
                    attr_list.append(LimitUpAttribution(
                        theme_name=current_theme, stock_count=0))
            # Stock table rows: "| 7板 | 603137 | 恒尚节能 | ..."
            elif current_theme and re.match(r'\|\s*(\d+板|首板)\s*\|', line):
                if attr_list:
                    attr_list[-1].stock_count += 1

        return attr_list

    def _parse_leaders(self, text: str) -> list[LeaderState]:
        """Extract leader/high-board stocks."""
        leaders: list[LeaderState] = []
        seen = set()

        # Match stock table rows with board heights
        for line in text.split("\n"):
            m = re.match(r'\|\s*(\d+板|首板)\s*\|\s*(\d{6})\s*\|\s*(\S+)', line)
            if m:
                code = m.group(2)
                name = m.group(3)
                if code in seen:
                    continue
                seen.add(code)
                board_str = m.group(1)
                board_h = int(board_str[0]) if board_str[0].isdigit() else 1

                leaders.append(LeaderState(
                    stock_code=code, stock_name=name,
                    board_height=board_h, role="龙头" if board_h >= 3 else ""))

        return leaders

    def _parse_external(self, text: str, json_data: dict) -> ExternalEnvironment:
        ext = ExternalEnvironment()

        # Try external_market JSON
        em = json_data.get("external", {})
        if isinstance(em, dict) and "external_market" in em:
            ext.korea_index = em.get("external_market", {}).get("market", {})

        # Try root JSON external_environment
        root = json_data.get("root", {})
        ee = root.get("external_environment", {})
        if ee:
            ext.korea_index = ee.get("korea_index", {})
            ext.us_market = ee.get("us_market", {})

        return ext
