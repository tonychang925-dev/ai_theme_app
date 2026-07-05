from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ThemeCandidate:
    theme_name: str
    confidence: float
    matched_reason_tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ThemeMatch:
    primary_theme: str | None
    secondary_themes: list[str]
    matched_reason_tags: dict[str, list[str]]
    confidence: float
    candidates: list[ThemeCandidate] = field(default_factory=list)


class ReasonThemeResolver(Protocol):
    async def resolve(
        self,
        reason_tags: list[str],
        stock_code: str,
        stock_name: str,
    ) -> ThemeMatch:
        ...


DEFAULT_THEME_KEYWORDS: dict[str, tuple[str, ...]] = {
    "PCB/HBM产业链": (
        "PCB",
        "HDI",
        "覆铜板",
        "铜箔",
        "FCBGA",
        "HBM",
        "封装基板",
        "电子布",
        "钻针",
    ),
    "AI光通信": (
        "CPO",
        "光模块",
        "硅光",
        "光通信",
        "光纤",
        "光缆",
        "3.2T",
        "NPO",
    ),
    "AI算力基础设施": (
        "液冷",
        "数据中心",
        "AIDC",
        "AI服务器",
        "算力租赁",
        "智算中心",
        "算力服务",
        "AI云平台",
    ),
    "机器人": (
        "人形机器人",
        "工业机器人",
        "具身智能",
        "机器人线束",
        "机器人零部件",
        "机器人",
    ),
    "先进材料/固态电池": (
        "锆材料",
        "氧化锆",
        "碳化硅",
        "氮化铝",
        "陶瓷材料",
        "陶瓷载板",
        "固态电池",
        "PEEK",
    ),
    "有色资源/小金属": (
        "稀土",
        "钨",
        "铜",
        "高温合金",
        "有色",
        "锂",
        "钴",
        "钼",
        "小金属",
    ),
    "创新药/医疗": (
        "创新药",
        "医疗",
        "CRO",
        "医药",
        "减肥药",
        "中药",
        "流感",
        "眼科",
    ),
    "ST摘帽/重整/国资": (
        "摘帽",
        "重整",
        "预重整",
        "国资",
        "ST板块",
        "扭亏",
        "债务豁免",
    ),
    "商业航天/军工": (
        "商业航天",
        "军工",
        "航空装备",
        "无人机",
        "卫星",
    ),
    "低空经济": (
        "低空经济",
        "飞行汽车",
        "eVTOL",
        "无人机",
    ),
    "芯片产业链/半导体": (
        "芯片",
        "半导体",
        "存储",
        "封测",
        "光刻",
        "晶圆",
        "前驱体",
        "EEPROM",
        "VPD",
        "DRAM",
        "NAND",
        "HBM",
        "PCIe",
        "洁净室",
        "硅基",
        "化合物半导体",
        "显示驱动",
        "交换芯片",
        "芯片国产化",
        "存储芯片",
    ),
    "化工": (
        "磷化工",
        "氟化工",
        "化工供应链",
        "化学试剂",
        "制冷剂",
        "氢氟酸",
        "化工",
    ),
}


class RuleResolver:
    def __init__(self, theme_keywords: dict[str, tuple[str, ...]] | None = None) -> None:
        self._theme_keywords = theme_keywords or DEFAULT_THEME_KEYWORDS

    async def resolve(
        self,
        reason_tags: list[str],
        stock_code: str,
        stock_name: str,
    ) -> ThemeMatch:
        del stock_code, stock_name
        normalized_tags = [str(tag or "").strip() for tag in reason_tags if str(tag or "").strip()]
        candidates: list[ThemeCandidate] = []
        matched_by_theme: dict[str, list[str]] = {}
        for theme_name, keywords in self._theme_keywords.items():
            matched_tags: list[str] = []
            for tag in normalized_tags:
                tag_upper = tag.upper()
                if any(keyword.upper() in tag_upper for keyword in keywords):
                    matched_tags.append(tag)
            if matched_tags:
                score = len(set(matched_tags))
                confidence = min(0.95, 0.55 + score * 0.1)
                candidates.append(
                    ThemeCandidate(
                        theme_name=theme_name,
                        confidence=confidence,
                        matched_reason_tags=matched_tags,
                    )
                )
                matched_by_theme[theme_name] = matched_tags

        candidates.sort(key=lambda item: (item.confidence, len(item.matched_reason_tags)), reverse=True)
        primary_theme = candidates[0].theme_name if candidates else None
        secondary_themes = [candidate.theme_name for candidate in candidates[1:]]
        confidence = candidates[0].confidence if candidates else 0.0
        return ThemeMatch(
            primary_theme=primary_theme,
            secondary_themes=secondary_themes,
            matched_reason_tags=matched_by_theme,
            confidence=confidence,
            candidates=candidates,
        )


class EmbeddingResolver:
    async def resolve(
        self,
        reason_tags: list[str],
        stock_code: str,
        stock_name: str,
    ) -> ThemeMatch:
        del reason_tags, stock_code, stock_name
        return ThemeMatch(primary_theme=None, secondary_themes=[], matched_reason_tags={}, confidence=0.0)


class LLMResolver:
    async def resolve(
        self,
        reason_tags: list[str],
        stock_code: str,
        stock_name: str,
    ) -> ThemeMatch:
        del reason_tags, stock_code, stock_name
        return ThemeMatch(primary_theme=None, secondary_themes=[], matched_reason_tags={}, confidence=0.0)


class CompositeReasonThemeResolver:
    def __init__(self, resolvers: list[ReasonThemeResolver] | None = None) -> None:
        self._resolvers = resolvers or [RuleResolver()]

    async def resolve(
        self,
        reason_tags: list[str],
        stock_code: str,
        stock_name: str,
    ) -> ThemeMatch:
        for resolver in self._resolvers:
            match = await resolver.resolve(reason_tags, stock_code, stock_name)
            if match.primary_theme:
                return match
        return ThemeMatch(primary_theme=None, secondary_themes=[], matched_reason_tags={}, confidence=0.0)


def theme_match_to_evidence_rows(
    *,
    trade_date,
    stock_code: str,
    stock_name: str,
    reason_raw: str,
    reason_tags: list[str],
    source_name: str,
    source_trace_id: str,
    raw_snapshot_id: int | None,
    match: ThemeMatch,
) -> list[dict]:
    rows: list[dict] = []
    for candidate in match.candidates:
        rows.append(
            {
                "trade_date": trade_date,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "theme_name": candidate.theme_name,
                "source_name": source_name,
                "evidence_text": reason_raw,
                "reason_tags": reason_tags,
                "matched_reason_tags": candidate.matched_reason_tags,
                "primary_theme": candidate.theme_name == match.primary_theme,
                "confidence": candidate.confidence,
                "source_trace_id": source_trace_id,
                "raw_snapshot_id": raw_snapshot_id,
            }
        )
    return rows
