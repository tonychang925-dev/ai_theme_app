from __future__ import annotations

import logging
import os
from typing import Any

from stock_processing_service.application.services.market_cognition.replay import (
    MarketCognitionReplay,
)
from stock_processing_service.publishers.notion_block_builder import NotionBlockBuilder
from stock_processing_service.publishers.notion_market_thesis_renderer import (
    NotionMarketThesisRenderer,
)
from stock_processing_service.publishers.notion_post_market_report_renderer import (
    PostMarketNotionReportRenderer,
)
from stock_processing_service.publishers.notion_publish_models import NotionPublishResult


class NotionPostMarketRecapPublisher:
    """Publish existing SPS snapshots without recomputing report data."""

    _logger = logging.getLogger(__name__)

    def __init__(
        self,
        token: str,
        database_id: str,
        client: Any = None,
        *,
        title_property: str = "标题",
        trade_date_property: str = "交易日期",
        report_type_property: str = "报告类型",
        report_id_property: str = "report_id",
        snapshot_version_property: str = "snapshot_version",
        summary_property: str = "摘要",
        status_property: str = "状态",
        overwrite_mode: str = "archive_and_recreate",
    ) -> None:
        if not token and client is None:
            raise ValueError("missing NOTION_TOKEN")
        if not database_id:
            raise ValueError("missing NOTION_DATABASE_ID")

        if client is None:
            from notion_client import Client

            client = Client(auth=token, notion_version="2022-06-28")

        self._client = client
        self._database_id = database_id
        self._title_prop = title_property
        self._trade_date_prop = trade_date_property
        self._report_type_prop = report_type_property
        self._report_id_prop = report_id_property
        self._snapshot_version_prop = snapshot_version_property
        self._summary_prop = summary_property
        self._status_prop = status_property
        self._overwrite_mode = overwrite_mode

    @classmethod
    def from_env(cls, client: Any = None) -> "NotionPostMarketRecapPublisher":
        return cls(
            token=os.getenv("NOTION_TOKEN", "").strip(),
            database_id=os.getenv("NOTION_DATABASE_ID", "").strip(),
            client=client,
            title_property=os.getenv("NOTION_PROP_TITLE", "标题").strip() or "标题",
            trade_date_property=os.getenv("NOTION_PROP_TRADE_DATE", "交易日期").strip() or "交易日期",
            report_type_property=os.getenv("NOTION_PROP_REPORT_TYPE", "报告类型").strip() or "报告类型",
            report_id_property=os.getenv("NOTION_PROP_REPORT_ID", "report_id").strip() or "report_id",
            snapshot_version_property=os.getenv("NOTION_PROP_SNAPSHOT_VERSION", "snapshot_version").strip()
            or "snapshot_version",
            summary_property=os.getenv("NOTION_PROP_SUMMARY", "摘要").strip() or "摘要",
            status_property=os.getenv("NOTION_PROP_STATUS", "状态").strip() or "状态",
        )

    @staticmethod
    def _make_report_id(trade_date: str) -> str:
        return f"post_market_recap:{trade_date}"

    def _query_existing_page(self, report_id: str) -> dict[str, Any] | None:
        body: dict[str, Any] = {
            "filter": {
                "property": self._report_id_prop,
                "rich_text": {"equals": report_id},
            },
            "page_size": 5,
        }
        response = self._client.request(
            f"/databases/{self._database_id}/query",
            "POST",
            body=body,
        )
        results = response.get("results") or []
        return results[0] if results else None

    def _archive_page(self, page_id: str) -> None:
        self._client.pages.update(page_id=page_id, archived=True)

    def _create_page(
        self,
        trade_date: str,
        title: str,
        report_id: str,
        snapshot_version: str,
        summary: str,
        report_type: str = "post_market_recap",
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {
            self._title_prop: {"title": NotionBlockBuilder._rich_text(title, limit=120)},
            self._trade_date_prop: {"date": {"start": trade_date}},
            self._report_type_prop: {"select": {"name": report_type}},
            self._report_id_prop: {"rich_text": NotionBlockBuilder._rich_text(report_id)},
            self._snapshot_version_prop: {
                "rich_text": NotionBlockBuilder._rich_text(snapshot_version)
            },
            self._summary_prop: {"rich_text": NotionBlockBuilder._rich_text(summary)},
            self._status_prop: {"select": {"name": "已发布"}},
        }
        return self._client.pages.create(
            parent={"database_id": self._database_id},
            properties=properties,
        )

    def _append_children(self, page_id: str, blocks: list[dict[str, Any]]) -> None:
        for chunk in NotionBlockBuilder.chunk_blocks(blocks):
            self._client.blocks.children.append(block_id=page_id, children=chunk)

    @classmethod
    def _extract_recap_doc(cls, payload: dict[str, Any]) -> dict[str, Any]:
        recap_doc = payload.get("recap_doc")
        if isinstance(recap_doc, dict) and recap_doc:
            return recap_doc
        if isinstance(payload, dict) and (
            payload.get("schema_version")
            or payload.get("engine_summary")
            or payload.get("daily_review_v2")
        ):
            return payload
        return {}

    @classmethod
    def build_blocks(
        cls,
        payload: dict[str, Any],
        trade_date: str,
        *,
        render_mode: str | None = None,
    ) -> list[dict[str, Any]]:
        """Build legacy evidence blocks and optionally prepend a thesis homepage."""
        legacy_blocks = PostMarketNotionReportRenderer(payload, trade_date).build()
        mode = (
            str(render_mode or os.getenv("M8_NOTION_RENDER_MODE", "legacy_only"))
            .strip()
            .lower()
        )
        if mode not in {"legacy_only", "cognition_shadow", "dual_layer"}:
            mode = "legacy_only"
        if mode == "legacy_only":
            return legacy_blocks

        cognition = payload.get("market_cognition")
        if "market_cognition" not in payload:
            replay = MarketCognitionReplay.run(payload, trade_date)
            if replay.status == "ready" and replay.thesis is not None:
                cognition = replay.thesis.to_dict()
            else:
                cls._logger.warning(
                    "M8 cognition preview unavailable trade_date=%s stage=%s diagnostics=%s",
                    trade_date,
                    replay.failed_stage,
                    replay.diagnostics,
                )
        if mode == "cognition_shadow":
            cls._logger.info(
                "M8 cognition shadow trade_date=%s ready=%s",
                trade_date,
                NotionMarketThesisRenderer.is_ready(cognition),
            )
            return legacy_blocks

        thesis_blocks = NotionMarketThesisRenderer.build(cognition)
        if not thesis_blocks:
            return legacy_blocks
        if legacy_blocks and legacy_blocks[0].get("type") == "heading_1":
            return [
                legacy_blocks[0],
                *thesis_blocks,
                NotionBlockBuilder.divider(),
                *legacy_blocks[1:],
            ]
        return [*thesis_blocks, NotionBlockBuilder.divider(), *legacy_blocks]

    def _build_pre_market_blocks(
        self,
        payload: dict[str, Any],
        trade_date: str,
    ) -> list[dict[str, Any]]:
        del trade_date  # The snapshot already carries its own data window.
        B = NotionBlockBuilder
        sections = payload.get("sections") or {}
        diagnostics = payload.get("diagnostics") or {}
        blocks: list[dict[str, Any]] = []

        blocks.append(B.heading_2("一、今日重大事件"))
        major = sections.get("major_events") or []
        if major:
            for event in major[:10]:
                title = str(event.get("title") or "?")
                summary = str(event.get("summary") or "")
                theme = str(event.get("theme_name") or "")
                source = str(event.get("source_channel") or "")
                blocks.append(B.callout(f"**{title}**\n{summary}\n🏷 {theme} | {source}", icon="📰"))
        else:
            blocks.append(B.empty_paragraph("暂无重大事件"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("二、重点题材"))
        themes = sections.get("matched_themes") or []
        if themes:
            for theme in themes[:10]:
                name = str(theme.get("theme_name") or "?")
                count = int(theme.get("event_count") or 0)
                blocks.append(B.bullet(f"**{name}** — {count} 条事件"))
        else:
            blocks.append(B.empty_paragraph("暂无匹配题材"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("三、事件驱动机会"))
        opportunities = sections.get("event_driven_opportunities") or []
        if opportunities:
            for opportunity in opportunities[:5]:
                theme = str(opportunity.get("theme_name") or "?")
                for stock in (opportunity.get("stocks") or [])[:3]:
                    name = str(stock.get("stock_name") or stock.get("stock_id") or "?")
                    level = str(stock.get("level") or "?")
                    score = str(stock.get("score") or "?")
                    blocks.append(B.bullet(f"{theme} → {name} [{level}档, {score}分]"))
        else:
            blocks.append(B.empty_paragraph("暂无事件驱动机会"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("四、风险预警"))
        risks = sections.get("risk_alerts") or []
        if risks:
            for risk in risks[:5]:
                reason = str(risk.get("reason") or "?")
                level = str(risk.get("alert_level") or "?")
                stock = str(risk.get("stock_name") or "")
                blocks.append(B.callout(f"**[{level.upper()}] {stock}** — {reason}", icon="⚠️"))
        else:
            blocks.append(B.empty_paragraph("暂无风险预警"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("五、公告机会"))
        alerts = sections.get("opportunity_alerts") or []
        if alerts:
            for alert in alerts[:5]:
                reason = str(alert.get("reason") or "?")
                stock = str(alert.get("stock_name") or "")
                amount = str(alert.get("amount") or "")
                extra = f" 💰{amount}" if amount else ""
                blocks.append(B.bullet(f"**{stock}** — {reason}{extra}"))
        else:
            blocks.append(B.empty_paragraph("暂无公告机会"))
        blocks.append(B.divider())

        source_breakdown = diagnostics.get("source_breakdown") or {}
        window = diagnostics.get("pre_market_window") or {}
        blocks.append(
            B.callout(
                f"📊 数据诊断\nmatched: {source_breakdown.get('matched_by_source', {})}\n"
                f"intel_raw: {source_breakdown.get('intel_raw_announcements', 0)} "
                f"matched: {source_breakdown.get('intel_matched_announcements', 0)}\n"
                f"window: {window.get('start_at', '?')} ~ {window.get('end_at', '?')}",
                icon="📊",
            )
        )
        return blocks

    def publish_snapshot(
        self,
        row: dict[str, Any],
        payload: dict[str, Any],
        *,
        force: bool = False,
        dry_run: bool = False,
        report_type: str = "post_market_recap",
    ) -> NotionPublishResult:
        trade_date = str(row.get("trade_date") or "")
        snapshot_version = str(row.get("snapshot_version") or "unknown")
        report_id = (
            self._make_report_id(trade_date)
            if report_type == "post_market_recap"
            else f"pre_market_brief:{trade_date}"
        )
        existing = self._query_existing_page(report_id)

        if dry_run:
            return NotionPublishResult(
                page_id=existing["id"] if existing else "",
                page_url=existing.get("url", "") if existing else "",
                action=f"dry_run:{'would_recreate' if existing else 'would_create'}",
                report_id=report_id,
                report_type=report_type,
                trade_date=trade_date,
            )

        action = "created"
        if existing:
            if force:
                self._archive_page(existing["id"])
                action = "recreated"
            else:
                return NotionPublishResult(
                    page_id=existing["id"],
                    page_url=existing.get("url", ""),
                    action="exists",
                    report_id=report_id,
                    report_type=report_type,
                    trade_date=trade_date,
                )

        title = (
            f"{trade_date} 盘后复盘"
            if report_type == "post_market_recap"
            else f"{trade_date} 盘前必读"
        )
        page = self._create_page(
            trade_date=trade_date,
            title=title,
            report_id=report_id,
            snapshot_version=snapshot_version,
            summary=self._build_summary(payload),
            report_type=report_type,
        )

        blocks = (
            self._build_pre_market_blocks(payload, trade_date)
            if report_type == "pre_market_brief"
            else self.build_blocks(payload, trade_date)
        )
        self._append_children(page["id"], blocks)

        return NotionPublishResult(
            page_id=page["id"],
            page_url=page.get("url", ""),
            action=action,
            report_id=report_id,
            report_type=report_type,
            trade_date=trade_date,
        )

    @classmethod
    def _build_summary(cls, payload: dict[str, Any]) -> str:
        recap_doc = cls._extract_recap_doc(payload)
        if not recap_doc:
            return "盘后快照为空"
        v2 = recap_doc.get("daily_review_v2")
        v2 = v2 if isinstance(v2, dict) else {}
        engine = recap_doc.get("engine_summary") or v2.get("engine_summary") or {}
        essentials = recap_doc.get("daily_recap_essentials") or v2.get("daily_recap_essentials") or {}
        market = recap_doc.get("market_summary") or v2.get("market_summary") or {}
        for value in (
            engine.get("conclusion"),
            essentials.get("headline"),
            market.get("conclusion"),
            market.get("market_overview"),
        ):
            text = str(value or "").strip()
            if text:
                return text[:240]
        return "DailyReview V2 盘后复盘"
