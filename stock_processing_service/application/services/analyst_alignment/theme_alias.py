"""Phase 4.2.2b — Theme Alias Resolver v1.

Normalizes AI direction names and analyst theme names for comparison.
Deterministic: alias map + token overlap + industry hints. No LLM.
"""

from __future__ import annotations


# ═══ Canonical Theme → Variants ═══
# Key: canonical name. Value: alternative names found in AI or analyst output.

THEME_ALIASES: dict[str, tuple[str, ...]] = {
    # ── 算力 / AI infrastructure ──
    "国产算力": ("国产服务器", "华为昇腾", "华为昇腾950", "AI服务器",
                 "算力", "算力基础设施", "人工智能硬件"),
    "液冷服务器": ("液冷", "数据中心液冷", "液冷散热"),
    "AI光纤": ("光纤", "光通信", "MPO"),

    # ── 半导体 / 芯片 ──
    "半导体设备": ("半导体", "半导体设备", "半导体硅片", "碳化硅",
                   "光刻胶", "六氟化钨", "靶材", "电子特气", "金刚石散热",
                   "半导体材料"),
    "存储芯片": ("存储", "存储芯片模组厂", "SST", "长鑫长江存储",
                 "存储扩产设备", "HBM"),
    "芯片设计": ("英伟达rubin架构", "英伟达Rubin液冷", "GPU"),

    # ── PCB / 电子元器件 ──
    "PCB": ("PCB印制电路板", "覆铜板", "PCB"),

    # ── 机器人 ──
    "机器人": ("人形机器人", "宇树机器人", "机器人概念", "机器视觉",
               "机器人电子皮肤"),

    # ── 消费 ──
    "消费": ("大消费", "旅游", "零售", "食品饮料"),

    # ── 电力 / 能源 ──
    "电力": ("电力运营", "电力设备", "储能", "光伏材料", "算电协同"),

    # ── 航天 / 军工 ──
    "航天": ("商业航天", "SpaceX", "卫星互联网", "卫星互联网-航天国家队",
             "军工"),

    # ── 通信 / 6G ──
    "通信": ("6G", "通信设备", "光模块", "cpo光模块", "共封装光学CPO"),

    # ── Other ──
    "磷化铟": ("磷化铟", "金属铟"),
    "可控核聚变": ("可控核聚变",),
    "洪涝/水利": ("水利", "洪涝", "台风概念"),
    "MLCC": ("MLCC电容", "MLCC"),
    "TGV": ("TGV玻璃基板封装", "玻璃基板"),
    "Token出海": ("Token出海",),

    # ── Misc normalizations ──
    "物理AI": ("AI物理", "物理AI"),
    "AIDC": ("数据中心", "AIDC"),
    "AI应用": ("AI应用", "人工智能应用"),
    "氟化工": ("氟化工",),
    "金属钨": ("金属钨", "钨"),
    "金属钼": ("金属钼", "钼"),
    "氧化锆": ("氧化锆", "锆"),
    "电子元器件": ("电子元器件", "元器件"),
}


# ═══ Industry Hints (broad categories) ═══

INDUSTRY_HINTS: dict[str, str] = {
    # Map specific themes to broader categories for fuzzy matching
    "国产算力": "科技硬件",
    "液冷服务器": "科技硬件",
    "AI光纤": "科技硬件",
    "半导体设备": "科技硬件",
    "存储芯片": "科技硬件",
    "芯片设计": "科技硬件",
    "PCB": "科技硬件",
    "磷化铟": "科技硬件",
    "MLCC": "科技硬件",
    "TGV": "科技硬件",
    "通信": "科技硬件",
    "机器人": "科技硬件",
    "物理AI": "科技硬件",
    "AIDC": "科技硬件",
    "AI应用": "科技硬件",
    "电子元器件": "科技硬件",
    "氟化工": "材料",
    "金属钨": "材料",
    "金属钼": "材料",
    "氧化锆": "材料",
    "消费": "消费",
    "电力": "能源",
    "航天": "军工航天",
    "军工": "军工航天",
    "洪涝/水利": "事件驱动",
    "可控核聚变": "能源",
    "Token出海": "科技硬件",
}


# ═══ Resolver ═══

class ThemeAliasResolver:
    """Normalize theme names for cross-source comparison."""

    def normalize(self, name: str) -> str:
        """Map a theme name to its canonical form.

        Returns the canonical name if found, else the original name.
        """
        name = name.strip()
        if not name:
            return name

        for canonical, aliases in THEME_ALIASES.items():
            if name == canonical or name in aliases:
                return canonical

        # Token-based fuzzy: check if any alias is a substring
        for canonical, aliases in THEME_ALIASES.items():
            for alias in aliases:
                if len(alias) >= 2 and alias in name:
                    return canonical
                if len(name) >= 2 and name in alias:
                    return canonical

        return name

    def normalize_set(self, names: set[str]) -> set[str]:
        """Normalize a set of theme names to canonical forms."""
        return {self.normalize(n) for n in names if n.strip()}

    def get_industry(self, canonical: str) -> str:
        """Get the industry hint for a canonical theme."""
        return INDUSTRY_HINTS.get(canonical, "")

    def industry_match_score(
        self, a_names: set[str], b_names: set[str]
    ) -> float:
        """Bonus score for matching industry categories, even if specific themes differ.

        Example: "国产算力"(科技硬件) vs "液冷服务器"(科技硬件) → partial credit.
        """
        a_canon = self.normalize_set(a_names)
        b_canon = self.normalize_set(b_names)
        a_industries = {self.get_industry(c) for c in a_canon if self.get_industry(c)}
        b_industries = {self.get_industry(c) for c in b_canon if self.get_industry(c)}
        if not a_industries or not b_industries:
            return 0.0
        overlap = a_industries & b_industries
        return len(overlap) / max(len(a_industries | b_industries), 1)

    def compare(
        self,
        analyst_names: set[str],
        ai_names: set[str],
    ) -> tuple[float, dict]:
        """Compare two sets of theme names with alias normalization.

        Returns (score, detail_dict).
        Score = 0.8 * normalized_jaccard + 0.2 * industry_match.
        """
        a_canon = self.normalize_set(analyst_names)
        b_canon = self.normalize_set(ai_names)

        if not a_canon and not b_canon:
            return 1.0, {"method": "both_empty"}

        if not a_canon:
            return 0.5, {"method": "analyst_empty", "ai_canonical": sorted(b_canon)}

        if not b_canon:
            return 0.0, {"method": "ai_empty", "analyst_canonical": sorted(a_canon)}

        overlap = a_canon & b_canon
        jaccard = len(overlap) / max(len(a_canon | b_canon), 1)
        industry = self.industry_match_score(analyst_names, ai_names)
        score = 0.8 * jaccard + 0.2 * industry

        return round(score, 4), {
            "method": "alias_normalized",
            "analyst_canonical": sorted(a_canon),
            "ai_canonical": sorted(b_canon),
            "overlap": sorted(overlap),
            "jaccard": round(jaccard, 3),
            "industry_match": round(industry, 3),
        }
