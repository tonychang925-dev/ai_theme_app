"""Phase 4.1b — Markdown Reference Ingestion (Full Reference Parser).

Parses DeepSeek-structured analyst recap markdown files into
AnalystReferenceRecord with field-level evidence,
5-level extraction status, and ratio normalization.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from .contracts import (
    CORE_REQUIRED_FIELDS,
    FULL_REQUIRED_FIELDS,
    AnalystReferenceQuality,
    AnalystReferenceRecord,
    EmotionLabel,
    ExtractedField,
    ExternalEnvironment,
    ExtractionStatus,
    LeaderState,
    LimitUpAttribution,
    MarketFacts,
    RelayLabel,
    StrategyLabel,
    ThemeLifecycleEntry,
    normalize_int,
    normalize_ratio,
)


class MarkdownReferenceParser:
    """Parse analyst recap Markdown (DeepSeek structured format).

    Phase 4.1b: field-level evidence, 5-level status, ratio normalization,
    section-scoped theme parsing, stock detail extraction.
    """

    # ── Section markers for scoped parsing ──

    SECTION_INSTITUTION_THEMES = "机构资金审美方向"
    SECTION_HOT_MONEY_THEMES = "情绪资金"
    SECTION_LIMITUP_CLASSIFY = "涨停股分类"
    SECTION_STRATEGY = "策略建议|交易策略|次日计划"

    def parse_file(self, path: str | Path, trade_date: date | None = None) -> AnalystReferenceRecord:
        """Parse a DeepSeek-structured analyst recap markdown file."""
        text = Path(path).read_text(encoding="utf-8")

        # ── Determine trade_date ──
        if trade_date is None:
            trade_date = self._extract_trade_date(text, str(path))

        if trade_date is None:
            raise ValueError("Could not determine trade_date from document")

        record = AnalystReferenceRecord(
            trade_date=trade_date,
            source_type="markdown",
            source_path=str(path),
            raw_text=text[:10000],
        )

        # ── Priority 1: Parse structured JSON blocks ──
        json_data = self._extract_json_blocks(text)

        # ── Collect all extracted fields ──
        all_fields: list[ExtractedField] = []

        # ── Extract MarketFacts ──
        facts, f_fields = self._parse_facts(text, json_data)
        record.market_facts = facts
        all_fields.extend(f_fields)

        # ── Extract EmotionLabel ──
        emotion, e_fields = self._parse_emotion(text, json_data)
        record.emotion_label = emotion
        all_fields.extend(e_fields)

        # ── Extract RelayLabel ──
        relay, r_fields = self._parse_relay(text, json_data)
        record.relay_label = relay
        all_fields.extend(r_fields)

        # ── Extract Strategy (section-scoped) ──
        strategy, s_fields = self._parse_strategy(text, json_data)
        record.strategy_label = strategy
        all_fields.extend(s_fields)

        # ── Extract Theme Lifecycle (section-scoped) ──
        themes, t_fields = self._parse_theme_lifecycle(text)
        record.theme_lifecycle = themes
        all_fields.extend(t_fields)

        # ── Extract LimitUp Attribution with stock details ──
        lu_attr, lu_fields = self._parse_limitup_attr(text)
        record.limitup_attribution = lu_attr
        all_fields.extend(lu_fields)

        # ── Extract Leader State with role classification ──
        leaders, l_fields = self._parse_leaders(text, json_data)
        record.leader_state = leaders
        all_fields.extend(l_fields)

        # ── External Environment ──
        ext, x_fields = self._parse_external(text, json_data)
        record.external_env = ext
        all_fields.extend(x_fields)

        # ── Store field evidence ──
        record.extracted_fields = all_fields

        # ── Compute quality ═─
        record.compute_quality()
        record.sync_legacy_fields()

        return record

    # ── Helpers ──

    def _extract_trade_date(self, text: str, path: str) -> date | None:
        """Priority-ordered date extraction."""
        m = re.search(r'日期[：:]\s*(\d{4}-\d{2}-\d{2})', text)
        if m:
            return date.fromisoformat(m.group(1))
        if re.search(r'7月7日|7/7', text[:500]):
            return date(2026, 7, 7)
        if re.search(r'7月8日|7/8', text[:500]):
            return date(2026, 7, 8)
        m = re.search(r'"date":\s*"(\d{4}-\d{2}-\d{2})"', text)
        if m:
            return date.fromisoformat(m.group(1))
        return None

    def _extract_json_blocks(self, text: str) -> dict:
        """Priority 1: Extract all JSON blocks and index by identifiable keys."""
        json_data: dict = {}
        for block in re.findall(r'```\s*json\s*\n(.*?)\n```', text, re.DOTALL):
            try:
                data = json.loads(block)
                if isinstance(data, dict):
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
                    elif "facts" in data:
                        json_data.setdefault("facts_blocks", []).append(data["facts"])
                    elif "phase" in data:
                        json_data.setdefault("emotion_blocks", []).append(data)
            except json.JSONDecodeError:
                pass

        # Add missing: strategy_label + relay_ecology + minimal blocks
        for block in re.findall(r'```\s*json\s*\n(.*?)\n```', text, re.DOTALL):
            try:
                data = json.loads(block)
                if isinstance(data, dict):
                    if "strategy_label" in data:
                        json_data["strategy_label"] = data["strategy_label"]
                    if "allowed" in data and "forbidden" in data and "watch_points" in data:
                        json_data.setdefault("strategy_label", data)
                    # Standalone: {"limit_up": 33, ...} without standard wrapper
                    if "limit_up" in data and "root" not in json_data:
                        json_data["root"] = data
            except json.JSONDecodeError:
                pass

        return json_data

    def _section_bounds(self, text: str, section_pattern: str) -> tuple[int, int] | None:
        """Find start/end char offsets of a section by heading pattern.

        Only ##-level headings are treated as section boundaries;
        ### sub-sections are included within the parent section.

        Returns (start, end) or None if not found.
        """
        m = re.search(rf'^#+\s*[\d.]*\s*[^#]*?{section_pattern}[^#]*?$', text, re.MULTILINE)
        if not m:
            return None
        start = m.end()
        # Next section: only ## level (exactly two #), not ### sub-sections
        next_section = re.search(r'^##[^#]\s', text[start:], re.MULTILINE)
        if next_section:
            end = start + next_section.start()
        else:
            end = len(text)
        return (start, end)

    def _extract_section_text(self, text: str, section_pattern: str) -> str:
        """Extract text content of a specific section."""
        bounds = self._section_bounds(text, section_pattern)
        if bounds is None:
            return ""
        return text[bounds[0]:bounds[1]]

    def _make_field(self, field_path: str, value: object, unit: str | None,
                    section: str, evidence: str, confidence: float,
                    rule: str) -> ExtractedField:
        """Factory for ExtractedField with consistent formatting."""
        return ExtractedField(
            field_path=field_path,
            value=value,
            unit=unit,
            source_section=section,
            evidence_text=evidence[:200],
            confidence=confidence,
            parser_rule=rule,
        )

    # ── Fact extractors ──

    def _parse_facts(self, text: str, json_data: dict) -> tuple[MarketFacts, list[ExtractedField]]:
        """Priority: JSON block > root JSON > regex fallback."""
        facts = MarketFacts()
        fields: list[ExtractedField] = []

        # P1: JSON block "大盘势能"
        power_data = json_data.get("大盘势能", {})
        if power_data:
            dates = power_data.get("dates", [])
            vals = power_data.get("limit_up_count", [])
            if dates and vals:
                facts.limit_up_count = vals[-1]
                fields.append(self._make_field(
                    "market_facts.limit_up_count", facts.limit_up_count, "count",
                    "4. 大盘势能指标", f"limit_up_count dates={dates} vals={vals}", 0.98,
                    "json_block:大盘势能"))

            chain_vals = power_data.get("chain_board_count", [])
            if chain_vals:
                facts.chain_board_count = chain_vals[-1]
                fields.append(self._make_field(
                    "market_facts.chain_board_count", facts.chain_board_count, "count",
                    "4. 大盘势能指标", f"chain_board_count={chain_vals}", 0.95,
                    "json_block:大盘势能"))

            ratio_vals = power_data.get("market_up_ratio", [])
            if ratio_vals:
                facts.market_up_ratio = normalize_ratio(ratio_vals[-1])
                fields.append(self._make_field(
                    "market_facts.market_up_ratio", facts.market_up_ratio, "ratio",
                    "4. 大盘势能指标", f"market_up_ratio={ratio_vals}", 0.95,
                    "json_block:大盘势能"))

            maxb_vals = power_data.get("max_board_height", [])
            if maxb_vals:
                facts.max_board_height = normalize_int(maxb_vals[-1])
                fields.append(self._make_field(
                    "market_facts.max_board_height", facts.max_board_height, "board",
                    "4. 大盘势能指标", f"max_board_height={maxb_vals}", 0.95,
                    "json_block:大盘势能"))

            comp_vals = power_data.get("composite_score", [])
            if comp_vals:
                facts.composite_score = normalize_int(comp_vals[-1])
                fields.append(self._make_field(
                    "market_facts.composite_score", facts.composite_score, "score",
                    "4. 大盘势能指标", f"composite_score={comp_vals}", 0.95,
                    "json_block:大盘势能"))

        # P1: root JSON
        root = json_data.get("root", {})
        if not facts.limit_up_count and "limit_up" in root:
            facts.limit_up_count = normalize_int(root["limit_up"])
            fields.append(self._make_field(
                "market_facts.limit_up_count", facts.limit_up_count, "count",
                "root JSON", f"limit_up={root['limit_up']}", 0.95,
                "json_block:root"))
        if not facts.max_board_height and "max_board" in root:
            facts.max_board_height = normalize_int(root["max_board"])
            fields.append(self._make_field(
                "market_facts.max_board_height", facts.max_board_height, "board",
                "root JSON", f"max_board={root['max_board']}", 0.95,
                "json_block:root"))

        # P1: facts JSON blocks
        for fb in json_data.get("facts_blocks", []):
            if fb.get("limit_up_count"):
                facts.limit_up_count = normalize_int(fb["limit_up_count"])
                facts.max_board_height = normalize_int(fb.get("max_board_height"))
                facts.active_capital_yi = normalize_int(fb.get("active_capital_yi"))
                facts.chain_board_count = normalize_int(fb.get("chain_board_count"))
                facts.market_up_ratio = normalize_ratio(fb.get("market_up_ratio"))
                facts.loss_effect_ratio = normalize_ratio(fb.get("loss_effect_ratio"))
                fields.append(self._make_field(
                    "market_facts", str(fb), None,
                    "facts JSON block", json.dumps(fb)[:150], 0.90,
                    "json_block:facts"))
                break

        # P3: Regex fallback for active_capital_yi
        if not facts.active_capital_yi:
            m = re.search(r'活跃资金[：:]\s*(\d[\d,.]*)\s*亿', text)
            if m:
                facts.active_capital_yi = float(m.group(1).replace(",", ""))
                fields.append(self._make_field(
                    "market_facts.active_capital_yi", facts.active_capital_yi, "yi",
                    "inline text", m.group(0), 0.80,
                    "regex:active_capital"))

        return facts, fields

    def _parse_emotion(self, text: str, json_data: dict) -> tuple[EmotionLabel, list[ExtractedField]]:
        """Priority: root JSON > emotion JSON blocks > section JSON > regex."""
        emotion = EmotionLabel()
        fields: list[ExtractedField] = []

        # P1: root JSON
        root = json_data.get("root", {})
        if root:
            phase = root.get("market_phase", root.get("phase", ""))
            if phase:
                emotion.market_phase = phase
                fields.append(self._make_field(
                    "emotion_label.market_phase", phase, None,
                    "root JSON", f"phase={phase}", 0.95, "json_block:root"))
            risk = root.get("risk", "")
            if risk:
                emotion.risk_level = risk
                fields.append(self._make_field(
                    "emotion_label.risk_level", risk, None,
                    "root JSON", f"risk={risk}", 0.95, "json_block:root"))
            if "emotion_momentum" in root:
                emotion.emotion_momentum = float(root["emotion_momentum"])
                fields.append(self._make_field(
                    "emotion_label.emotion_momentum", emotion.emotion_momentum, "score",
                    "root JSON", f"emotion_momentum={root['emotion_momentum']}", 0.95,
                    "json_block:root"))
            strategy = root.get("strategy", "")
            if strategy:
                emotion.strategy = strategy
                fields.append(self._make_field(
                    "emotion_label.strategy", strategy, None,
                    "root JSON", strategy[:100], 0.90, "json_block:root"))

        # P1: emotion JSON blocks (phase+risk+strategy triple)
        for eb in json_data.get("emotion_blocks", []):
            if not emotion.market_phase and "phase" in eb:
                emotion.market_phase = eb["phase"]
                emotion.risk_level = eb.get("risk", "")
                fields.append(self._make_field(
                    "emotion_label", str(eb), None,
                    "emotion JSON block", json.dumps(eb)[:150], 0.92,
                    "json_block:emotion"))
                break

        # P1: emotion_label / emotion in json_data
        em = json_data.get("emotion_label", {}) or json_data.get("emotion", {})
        if isinstance(em, dict):
            if not emotion.market_phase and em.get("phase"):
                emotion.market_phase = em["phase"]
                fields.append(self._make_field(
                    "emotion_label.market_phase", em["phase"], None,
                    "emotion_label JSON", f"phase={em['phase']}", 0.90,
                    "json_block:emotion_label"))
            if not emotion.risk_level and em.get("risk"):
                emotion.risk_level = em["risk"]
                fields.append(self._make_field(
                    "emotion_label.risk_level", em["risk"], None,
                    "emotion_label JSON", f"risk={em['risk']}", 0.90,
                    "json_block:emotion_label"))
            if not emotion.emotion_momentum and em.get("emotion_momentum") is not None:
                emotion.emotion_momentum = float(em["emotion_momentum"])
                fields.append(self._make_field(
                    "emotion_label.emotion_momentum", emotion.emotion_momentum, "score",
                    "emotion_label JSON", f"emotion_momentum={em['emotion_momentum']}", 0.90,
                    "json_block:emotion_label"))
            if not emotion.cycle_score and em.get("cycle_score") is not None:
                emotion.cycle_score = normalize_int(em["cycle_score"])
                fields.append(self._make_field(
                    "emotion_label.cycle_score", emotion.cycle_score, "score",
                    "emotion_label JSON", f"cycle_score={em['cycle_score']}", 0.90,
                    "json_block:emotion_label"))

        # P3: regex fallback for emotion_momentum in text
        if emotion.emotion_momentum is None:
            m = re.search(r'"emotion_momentum":\s*(-?[\d.]+)', text)
            if m:
                emotion.emotion_momentum = float(m.group(1))
                fields.append(self._make_field(
                    "emotion_label.emotion_momentum", emotion.emotion_momentum, "score",
                    "raw text regex", m.group(0), 0.70, "regex:emotion_momentum"))

        return emotion, fields

    def _parse_relay(self, text: str, json_data: dict) -> tuple[RelayLabel, list[ExtractedField]]:
        """Parse relay ecology with ratio normalization."""
        relay = RelayLabel()
        fields: list[ExtractedField] = []

        def _set_relay(field_name: str, value: object, section: str, evidence: str, conf: float, rule: str):
            setattr(relay, field_name, value)
            fields.append(self._make_field(
                f"relay_label.{field_name}", value, "ratio" if "promotion" in field_name else None,
                section, evidence, conf, rule))

        # P1: relay JSON section
        rl = json_data.get("relay", {}) or json_data.get("relay_label", {})
        if isinstance(rl, dict):
            for key, attr in [
                ("max_board_height", "max_board_height"),
                ("max_board", "max_board_height"),
                ("max_board_stock", "max_board_stock"),
                ("first_board_success_rate", "first_board_success_rate"),
            ]:
                if rl.get(key) is not None:
                    if key in ("max_board_stock",):
                        val = rl[key]
                    elif "height" in attr or key in ("max_board", "max_board_height"):
                        val = normalize_int(rl[key])
                    elif "rate" in attr or "promotion" in key:
                        val = normalize_ratio(rl[key])
                    else:
                        val = rl[key]
                    if val is not None:
                        _set_relay(attr, val, "relay JSON", f"{key}={rl[key]}", 0.92, "json_block:relay")

            for key in ["promotion_1_to_2", "promotion_2_to_3", "promotion_3_to_4",
                        "promotion_4_to_5", "promotion_5_to_6", "promotion_6_to_7"]:
                if rl.get(key) is not None:
                    val = normalize_ratio(rl[key])
                    if val is not None:
                        _set_relay(key, val, "relay JSON", f"{key}={rl[key]}", 0.92, "json_block:relay")

        # P1: root JSON relay
        root = json_data.get("root", {})
        if root.get("relay"):
            r = root["relay"]
            if not relay.max_board_height and r.get("max_board"):
                _set_relay("max_board_height", normalize_int(r["max_board"]),
                           "root.relay JSON", f"max_board={r['max_board']}", 0.90, "json_block:root.relay")
            for key in ["promotion_1_to_2", "promotion_2_to_3"]:
                if r.get(key) is not None and getattr(relay, key) is None:
                    val = normalize_ratio(r[key])
                    if val is not None:
                        _set_relay(key, val, "root.relay JSON", f"{key}={r[key]}", 0.90, "json_block:root.relay")

        # P3: table regex for promotion rates
        for key in ["promotion_1_to_2", "promotion_2_to_3", "promotion_3_to_4"]:
            if getattr(relay, key) is None:
                pattern_map = {
                    "promotion_1_to_2": r'1\s*→\s*2.*?晋级率[：:]\s*(\d+\.?\d*\s*%?)',
                    "promotion_2_to_3": r'2\s*→\s*3.*?晋级率[：:]\s*(\d+\.?\d*\s*%?)',
                    "promotion_3_to_4": r'3\s*→\s*4.*?晋级率[：:]\s*(\d+\.?\d*\s*%?)',
                }
                m = re.search(pattern_map.get(key, ""), text)
                if m:
                    val = normalize_ratio(m.group(1))
                    if val is not None:
                        _set_relay(key, val, "table regex", m.group(0), 0.75, "regex:promotion_table")

        return relay, fields

    def _parse_strategy(self, text: str, json_data: dict) -> tuple[StrategyLabel, list[ExtractedField]]:
        """Parse strategy label — P1 JSON > P2 section-scoped markdown lists."""
        strategy = StrategyLabel()
        fields: list[ExtractedField] = []

        # P1: strategy_label JSON
        sl = json_data.get("strategy_label", {})
        if isinstance(sl, dict) and (sl.get("allowed") or sl.get("watch_points")):
            strategy.allowed = sl.get("allowed", [])
            strategy.forbidden = sl.get("forbidden", [])
            strategy.watch_points = sl.get("watch_points", [])
            strategy.summary = sl.get("summary", "")
            fields.append(self._make_field(
                "strategy_label", f"allowed={len(strategy.allowed)}, watch={len(strategy.watch_points)}",
                None, "strategy_label JSON", json.dumps(sl)[:200], 0.92,
                "json_block:strategy_label"))

        # P1: conclusion JSON
        conc = json_data.get("conclusion", {})
        if isinstance(conc, dict) and conc.get("strategy") and not strategy.summary:
            strategy.summary = conc["strategy"]
            fields.append(self._make_field(
                "strategy_label.summary", strategy.summary[:100], None,
                "conclusion JSON", str(conc)[:150], 0.90, "json_block:conclusion"))

        # P1: root JSON
        root = json_data.get("root", {})
        if root.get("strategy") and not strategy.summary:
            strategy.summary = root["strategy"]
            fields.append(self._make_field(
                "strategy_label.summary", strategy.summary[:100], None,
                "root JSON", root["strategy"][:150], 0.90, "json_block:root"))

        # P2: Section-scoped markdown lists (e.g. "## 交易策略")
        if not strategy.allowed and not strategy.watch_points:
            strat_section = self._extract_section_text(text, self.SECTION_STRATEGY)
            if strat_section:
                # Parse list items with Chinese label prefixes
                for line in strat_section.split("\n"):
                    stripped = line.strip()
                    item_m = re.match(r'[-*\d.]+\s*(.+)', stripped)
                    if not item_m:
                        continue
                    item_text = item_m.group(1).strip()

                    # Classify by prefix label
                    if re.match(r'允许[：:]', item_text):
                        strategy.allowed.append(re.sub(r'^允许[：:]\s*', '', item_text))
                    elif re.match(r'禁止[：:]|不交易[：:]', item_text):
                        strategy.forbidden.append(re.sub(r'^(禁止|不交易)[：:]\s*', '', item_text))
                    elif re.match(r'观察[：:]|锚定[：:]|关注[：:]', item_text):
                        strategy.watch_points.append(re.sub(r'^(观察|锚定|关注)[：:]\s*', '', item_text))
                    elif re.match(r'总结[：:]', item_text):
                        strategy.summary = re.sub(r'^总结[：:]\s*', '', item_text)

                if strategy.allowed or strategy.watch_points:
                    fields.append(self._make_field(
                        "strategy_label", f"section_parse: allowed={len(strategy.allowed)}, watch={len(strategy.watch_points)}",
                        None, "策略 section", strat_section[:150], 0.75,
                        "section_scoped:strategy_lists"))

        return strategy, fields

    def _extract_list_items(self, text: str, label_pattern: str) -> list[str]:
        """Extract markdown list items following a label match."""
        items: list[str] = []
        # Find the label
        m = re.search(rf'[#*\s]*[^{{\}}]*?{label_pattern}[^{{\}}]*?\n', text)
        if m:
            remaining = text[m.end():]
            # Collect list items (- xxx or * xxx or 1. xxx) until blank line
            for line in remaining.split("\n"):
                stripped = line.strip()
                if not stripped:
                    break
                item_m = re.match(r'[-*\d.]+\s*(.+)', stripped)
                if item_m:
                    item_text = item_m.group(1).strip()
                    if len(item_text) > 2 and item_text not in items:
                        items.append(item_text)
                elif items:
                    break  # non-list line after items collected
        return items

    def _parse_theme_lifecycle(self, text: str) -> tuple[list[ThemeLifecycleEntry], list[ExtractedField]]:
        """Section-scoped theme lifecycle parsing.

        Only parses within designated sections to avoid false positives
        from indicator tables or other non-theme markdown tables.
        """
        entries: list[ThemeLifecycleEntry] = []
        fields: list[ExtractedField] = []
        seen = set()

        # Collect section content from both institution and hot-money theme sections
        section_texts: list[tuple[str, str]] = []  # [(style, text)]
        inst_text = self._extract_section_text(text, self.SECTION_INSTITUTION_THEMES)
        if inst_text:
            section_texts.append(("institutional", inst_text))
        hot_text = self._extract_section_text(text, self.SECTION_HOT_MONEY_THEMES)
        if hot_text:
            section_texts.append(("hot_money", hot_text))

        # Also try limitup classify section for theme data
        lu_text = self._extract_section_text(text, self.SECTION_LIMITUP_CLASSIFY)
        if lu_text:
            section_texts.append(("limitup_theme", lu_text))

        for style, section_text in section_texts:
            for line in section_text.split("\n"):
                m = re.match(r'\|\s*([^\s|]+[^\d|]+?)\s*\|\s*(.+?)\s*\|', line)
                if not m:
                    continue
                name = m.group(1).strip()
                state_text = m.group(2).strip()
                if name in seen or not name or len(name) > 20:
                    continue
                if name in ("板块方向", "方向", "题材", "细分方向", "机构方向"):
                    continue
                # Skip indicator/data rows
                if re.match(r'^(涨停数|炸板数|跌停数|活跃资金|指标|日期)', name):
                    continue

                seen.add(name)
                state = "观察"
                day_count = 0
                state_match = re.match(r'(启动|调整|修复|关注|观察|分歧|加速|高潮|退潮|冰点|反弹|主升|回踩).*?(\d+)', state_text)
                if state_match:
                    state = state_match.group(1)
                    day_count = int(state_match.group(2))
                else:
                    # Try simpler pattern: just "启动" or "调整第N天"
                    state_simple = re.match(r'(启动|调整|修复|关注|观察)', state_text)
                    if state_simple:
                        state = state_simple.group(1)
                        day_m = re.search(r'(\d+)', state_text)
                        if day_m:
                            day_count = int(day_m.group(1))

                entries.append(ThemeLifecycleEntry(
                    theme_name=name, state=state, day_count=day_count, style=style))

        if entries:
            fields.append(self._make_field(
                "theme_lifecycle", f"{len(entries)} themes", "themes",
                "section-scoped parse", ", ".join(e.theme_name for e in entries[:10]),
                0.80, "section_scoped:theme_table"))

        return entries, fields

    def _parse_limitup_attr(self, text: str) -> tuple[list[LimitUpAttribution], list[ExtractedField]]:
        """Parse limit-up classification with per-stock details.

        Extracts: code, name, board, time, reason, theme.
        Priority: section-scoped within limitup classify sections, then full-text.
        """
        attr_list: list[LimitUpAttribution] = []
        fields: list[ExtractedField] = []
        current_theme = ""
        seen_themes = set()

        # Prefer section-scoped text
        section_text = self._extract_section_text(text, self.SECTION_LIMITUP_CLASSIFY)
        parse_text = section_text if section_text else text

        for line in parse_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # Section heading: "## 13.2 算力 / 半导体产业链" or "### 机器人概念"
            heading_m = re.match(r'#+\s*[\d.]*\s*(.+?)(?:产业链|概念|板块|方向)?\s*$', line)
            if heading_m and not line.startswith("|"):
                current_theme = heading_m.group(1).strip()
                # Filter out non-theme headings
                if (current_theme and current_theme not in seen_themes
                        and len(current_theme) < 20
                        and not re.match(r'^(涨停股分类|分类|总结|策略|指标|交易策略|外部环境|接力生态)', current_theme)):
                    seen_themes.add(current_theme)
                    attr_list.append(LimitUpAttribution(
                        theme_name=current_theme, stock_count=0))
                continue

            # Stock table row: "| 7板 | 603137 | 恒尚节能 | 14:23:06 | 算力/半导体产业链 | 拟收购存储公司 + 建筑幕墙 |"
            stock_m = re.match(
                r'\|\s*(\d+板|首板|炸板)\s*\|\s*(\d{6})\s*\|\s*(\S+?)\s*\|\s*(\S+?)\s*\|\s*(.*)', line)
            if stock_m and (current_theme or attr_list):
                board_str = stock_m.group(1)
                code = stock_m.group(2)
                name = stock_m.group(3)
                time_or_reason = stock_m.group(4)
                rest = stock_m.group(5).strip()

                # Try to parse remaining columns: time | theme | reason
                remaining_parts = [p.strip() for p in rest.split("|")]
                stock_time = ""
                stock_theme = current_theme
                stock_reason = ""

                if len(remaining_parts) >= 2:
                    stock_time = re.match(r'\d{2}:\d{2}', remaining_parts[0])
                    stock_time = stock_time.group(0) if stock_time else remaining_parts[0]
                    stock_theme = remaining_parts[0] if not re.match(r'\d{2}:\d{2}', remaining_parts[0]) else remaining_parts[1] if len(remaining_parts) > 1 else current_theme
                    stock_reason = remaining_parts[-1] if remaining_parts[-1] != stock_theme else ""
                elif len(remaining_parts) == 1:
                    stock_reason = remaining_parts[0]

                # The time_or_reason could be time or theme
                if re.match(r'\d{2}:\d{2}', time_or_reason):
                    stock_time = time_or_reason

                # Determine target
                target = current_theme or (remaining_parts[0] if remaining_parts and len(remaining_parts[0]) < 20 else "")

                if attr_list:
                    # Find matching theme entry
                    for attr in attr_list:
                        if attr.theme_name == target:
                            attr.stock_count += 1
                            board_h = int(board_str[0]) if board_str and board_str[0].isdigit() else 1
                            attr.board_heights.append(board_h)
                            attr.key_stocks.append({
                                "code": code, "name": name,
                                "board": board_str, "time": stock_time,
                                "theme": target, "reason": stock_reason,
                            })
                            break
                    else:
                        # Theme not yet in list — add it
                        new_attr = LimitUpAttribution(
                            theme_name=target, stock_count=1,
                            key_stocks=[{
                                "code": code, "name": name,
                                "board": board_str, "time": stock_time,
                                "theme": target, "reason": stock_reason,
                            }])
                        attr_list.append(new_attr)

        if attr_list:
            total_stocks = sum(a.stock_count for a in attr_list)
            fields.append(self._make_field(
                "limitup_attribution", f"{len(attr_list)} themes, {total_stocks} stocks",
                "stocks", "section-scoped", "; ".join(a.theme_name for a in attr_list[:5]),
                0.80, "section_scoped:limitup_table"))

        return attr_list, fields

    def _parse_leaders(self, text: str, json_data: dict) -> tuple[list[LeaderState], list[ExtractedField]]:
        """Extract leader stocks with role classification.

        Role hierarchy (best-effort):
          market_leader   — max_board in entire market
          theme_leader    — max_board within a theme
          pioneer         — first to limit-up in theme
          assistant_leade — 2+ boards, aids theme expansion
          follower        — same theme, lower board
          中军             — large-cap leader with volume
          补涨             — late-cycle replacement leader
          穿越             — leader surviving theme rotation
        """
        leaders: list[LeaderState] = []
        fields: list[ExtractedField] = []
        seen = set()
        max_board = 0

        # First pass: collect all leaders
        for line in text.split("\n"):
            m = re.match(r'\|\s*(\d+板|首板)\s*\|\s*(\d{6})\s*\|\s*(\S+)', line)
            if m:
                code = m.group(2)
                name = m.group(3)
                if code in seen:
                    continue
                seen.add(code)
                board_str = m.group(1)
                board_h = int(board_str[0]) if board_str and board_str[0].isdigit() else 1
                if board_h > max_board:
                    max_board = board_h

                # Try to extract theme from same row
                theme = ""
                rest = line.split("|")
                if len(rest) > 5:
                    theme_candidate = rest[5].strip()
                    if theme_candidate and len(theme_candidate) < 20:
                        theme = theme_candidate

                # Detect death type
                death_type = ""
                if "跌停" in line or "炸板" in line:
                    death_type = "FRIED" if "炸" in line else "LIMIT_DOWN"
                elif "天地" in line:
                    death_type = "HEAVEN_EARTH"

                leaders.append(LeaderState(
                    stock_code=code, stock_name=name,
                    board_height=board_h, board_str=board_str,
                    theme=theme, death_type=death_type))

        # Second pass: classify roles
        for leader in leaders:
            leader.role = self._classify_leader_role(leader, max_board, leaders)

        if leaders:
            fields.append(self._make_field(
                "leader_state", f"{len(leaders)} leaders", "stocks",
                "board tables", f"max_board={max_board}, top={leaders[0].stock_name if leaders else ''}",
                0.82, "section_parse:leaders"))

        return leaders, fields

    def _classify_leader_role(self, leader: LeaderState, max_board: int,
                               all_leaders: list[LeaderState]) -> str:
        """Classify a leader stock's role based on board height and context."""
        board_h = leader.board_height
        theme = leader.theme

        # Market leader: highest board in market
        if board_h == max_board and board_h >= 3:
            return "market_leader"

        # Theme leader: highest board within theme
        if theme:
            theme_max = max(
                (l.board_height for l in all_leaders if l.theme == theme), default=0)
            if board_h == theme_max and board_h >= 2:
                return "theme_leader"
            if board_h >= 2:
                # Assistant: 2+ boards in a theme with a higher leader
                if theme_max > board_h:
                    return "assistant_leader"
                return "follower"

        # Pioneer (first to limit up): board=1, likely new theme
        if board_h == 1 and leader.board_str == "首板":
            return "pioneer"

        # Fallback
        if board_h >= 5:
            return "market_leader"
        if board_h >= 3:
            return "theme_leader"
        return ""

    def _parse_external(self, text: str, json_data: dict) -> tuple[ExternalEnvironment, list[ExtractedField]]:
        ext = ExternalEnvironment()
        fields: list[ExtractedField] = []

        # P1: external_market JSON
        em = json_data.get("external", {})
        if isinstance(em, dict) and "external_market" in em:
            market_data = em.get("external_market", {}).get("market", {})
            if market_data:
                ext.korea_index = market_data
                fields.append(self._make_field(
                    "external_env.korea_index", str(market_data), None,
                    "external JSON", json.dumps(market_data)[:150], 0.90,
                    "json_block:external_market"))

        # P1: root JSON external_environment
        root = json_data.get("root", {})
        ee = root.get("external_environment", {})
        if ee:
            if ee.get("korea_index"):
                ext.korea_index = ee["korea_index"]
                fields.append(self._make_field(
                    "external_env.korea_index", str(ee["korea_index"]), None,
                    "root JSON", json.dumps(ee["korea_index"])[:150], 0.90,
                    "json_block:root.external_environment"))
            if ee.get("us_market"):
                ext.us_market = ee["us_market"]
                fields.append(self._make_field(
                    "external_env.us_market", str(ee["us_market"]), None,
                    "root JSON", json.dumps(ee["us_market"])[:150], 0.90,
                    "json_block:root.external_environment"))
            if ee.get("key_events"):
                ext.key_events = ee["key_events"]

        return ext, fields
