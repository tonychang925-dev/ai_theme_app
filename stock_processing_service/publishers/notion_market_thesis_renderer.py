from __future__ import annotations

from typing import Any

from stock_processing_service.publishers.notion_block_builder import NotionBlockBuilder


class NotionMarketThesisRenderer:
    """Render only a validated Market Thesis read model."""

    _INTERNAL_LABELS = {
        "no_trade": "不交易",
        "short_term_sentiment_dead": "短线情绪冰点",
        "downtrend_rebound": "下跌趋势中的反弹",
        "mainline_tradable": "主线具备结构性机会",
        "dead": "情绪冰点",
    }

    @classmethod
    def build(cls, thesis: Any) -> list[dict[str, Any]]:
        if not cls.is_ready(thesis):
            return []
        assert isinstance(thesis, dict)
        primary = thesis["primary_thesis"]
        blocks = [
            NotionBlockBuilder.heading_2("市场认知首页"),
            NotionBlockBuilder.callout(
                cls._humanize(primary["statement"]),
                icon="🧠",
            ),
        ]

        hypothesis_results = cls._texts(thesis.get("hypothesis_results"))
        if hypothesis_results:
            blocks.append(NotionBlockBuilder.heading_3("昨日假设结果"))
            blocks.extend(
                NotionBlockBuilder.bullet(cls._humanize(item))
                for item in hypothesis_results[:3]
            )

        changes = cls._texts(thesis.get("key_belief_changes"))
        if changes:
            blocks.append(NotionBlockBuilder.heading_3("今日关键变化"))
            blocks.extend(
                NotionBlockBuilder.bullet(cls._humanize(item))
                for item in changes[:3]
            )

        scenarios = [
            row for row in thesis.get("scenarios") or [] if isinstance(row, dict)
        ]
        invalidations = cls._texts(thesis.get("invalidation_conditions"))
        if scenarios or invalidations:
            blocks.append(NotionBlockBuilder.heading_3("明日情景与失效条件"))
            for scenario in scenarios[:2]:
                condition = cls._humanize(str(scenario.get("condition") or ""))
                result = cls._humanize(str(scenario.get("expected_result") or ""))
                if condition and result:
                    blocks.append(
                        NotionBlockBuilder.bullet(f"如果：{condition}；那么：{result}")
                    )
            for condition in invalidations[:3]:
                blocks.append(
                    NotionBlockBuilder.bullet(
                        f"失效条件：{cls._humanize(condition)}"
                    )
                )

        permission = str(thesis.get("trading_permission") or "").strip()
        if permission:
            blocks.append(NotionBlockBuilder.heading_3("交易权限"))
            blocks.append(
                NotionBlockBuilder.paragraph(cls._humanize(permission))
            )
        return blocks

    @classmethod
    def is_ready(cls, thesis: Any) -> bool:
        if not isinstance(thesis, dict):
            return False
        if thesis.get("schema_version") != "market_thesis.v1":
            return False
        if thesis.get("status") != "ready":
            return False
        if int(thesis.get("unsupported_claim_count") or 0) != 0:
            return False
        primary = thesis.get("primary_thesis")
        if not isinstance(primary, dict):
            return False
        statement = str(primary.get("statement") or "").strip()
        refs = primary.get("evidence_refs")
        return bool(statement and isinstance(refs, list) and refs)

    @staticmethod
    def _texts(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @classmethod
    def _humanize(cls, value: str) -> str:
        text = value
        for code, label in cls._INTERNAL_LABELS.items():
            text = text.replace(code, label)
        return text
