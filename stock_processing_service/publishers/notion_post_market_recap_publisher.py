from __future__ import annotations

import os
from typing import Any

from stock_processing_service.publishers.notion_block_builder import NotionBlockBuilder
from stock_processing_service.publishers.notion_publish_models import NotionPublishResult


class NotionPostMarketRecapPublisher:
    """将 SPS 盘后复盘 snapshot 发布到 Notion database。

    主数据源：recap_doc（SPS 原生结构化数据）。
    旧链 report 仅作为兼容折叠区兜底。
    """

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

            client = Client(auth=token)

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
            snapshot_version_property=os.getenv("NOTION_PROP_SNAPSHOT_VERSION", "snapshot_version").strip() or "snapshot_version",
            summary_property=os.getenv("NOTION_PROP_SUMMARY", "摘要").strip() or "摘要",
            status_property=os.getenv("NOTION_PROP_STATUS", "状态").strip() or "状态",
        )

    # ── report_id ──────────────────────────────────────────────

    @staticmethod
    def _make_report_id(trade_date: str) -> str:
        return f"post_market_recap:{trade_date}"

    # ── database page CRUD ─────────────────────────────────────

    def _query_existing_page(self, report_id: str) -> dict[str, Any] | None:
        body: dict[str, Any] = {
            "filter": {
                "property": self._report_id_prop,
                "rich_text": {"equals": report_id},
            },
            "page_size": 5,
        }
        resp = self._client.request(
            f"/v1/databases/{self._database_id}/query",
            "POST",
            body=body,
        )
        results = resp.get("results") or []
        return results[0] if results else None

    def _archive_page(self, page_id: str) -> None:
        self._client.pages.update(page_id=page_id, archived=True)

    def _create_page(self, trade_date: str, title: str, report_id: str, snapshot_version: str, summary: str) -> dict[str, Any]:
        properties: dict[str, Any] = {
            self._title_prop: {"title": NotionBlockBuilder._rich_text(title, limit=120)},
            self._trade_date_prop: {"date": {"start": trade_date}},
            self._report_type_prop: {"select": {"name": "post_market_recap"}},
            self._report_id_prop: {"rich_text": NotionBlockBuilder._rich_text(report_id)},
            self._snapshot_version_prop: {"rich_text": NotionBlockBuilder._rich_text(snapshot_version)},
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

    # ── block 构建（核心渲染逻辑）────────────────────────────────

    @classmethod
    def _extract_recap_doc(cls, payload: dict[str, Any]) -> dict[str, Any]:
        """从 payload 中提取 recap_doc（兼容多种存储形态）。"""
        recap_doc = payload.get("recap_doc")
        if isinstance(recap_doc, dict) and recap_doc:
            return recap_doc
        # fallback: payload 本身即为 recap_doc
        if payload.get("candidate_count") is not None or payload.get("top_candidates"):
            return payload
        return {}

    @classmethod
    def _extract_old_report(cls, payload: dict[str, Any]) -> dict[str, Any] | None:
        """提取旧链 report（兼容折叠区）。"""
        report = payload.get("report")
        if isinstance(report, dict) and report:
            return report
        recap_doc = payload.get("recap_doc")
        if isinstance(recap_doc, dict):
            report = recap_doc.get("report")
            if isinstance(report, dict) and report:
                return report
        return None

    @classmethod
    def _safe_str(cls, value: Any, fallback: str = "--") -> str:
        if value is None:
            return fallback
        return str(value)

    @classmethod
    def _safe_list(cls, value: Any) -> list[dict[str, Any]]:
        if isinstance(value, list):
            return value
        return []

    @classmethod
    def build_blocks(cls, payload: dict[str, Any], trade_date: str) -> list[dict[str, Any]]:
        """从 normalized payload 构造 Notion blocks。"""
        B = NotionBlockBuilder
        blocks: list[dict[str, Any]] = []

        recap_doc = cls._extract_recap_doc(payload)
        old_report = cls._extract_old_report(payload)

        # ── 标题 ──────────────────────────────────────────────
        blocks.append(B.heading_1(f"{trade_date} 盘后复盘"))

        # ── 一、复盘概览 ──────────────────────────────────────
        blocks.append(B.heading_2("一、复盘概览"))

        summary_stats: list[str] = []
        candidate_count = recap_doc.get("candidate_count", 0) if recap_doc else 0
        formal_count = recap_doc.get("candidate_count_formal", 0) if recap_doc else 0
        observe_count = (
            recap_doc.get("candidate_count_observe")
            or recap_doc.get("observe_candidates_count")
            or 0
        ) if recap_doc else 0
        watch_input = recap_doc.get("strong_watch_input_count", 0) if recap_doc else 0
        watch_promoted = recap_doc.get("strong_watch_promoted_count", 0) if recap_doc else 0
        watch_history = recap_doc.get("strong_watch_history_count", 0) if recap_doc else 0

        summary_stats = [
            B.summary_stat_line("候选总数", candidate_count),
            B.summary_stat_line("正式候选", formal_count),
            B.summary_stat_line("观察候选", observe_count),
            B.summary_stat_line("强势池输入", watch_input),
            B.summary_stat_line("晋级候选", watch_promoted),
            B.summary_stat_line("强势股历史", watch_history),
        ]
        for stat in summary_stats:
            blocks.append(B.callout(stat, icon="📊"))
        blocks.append(B.divider())

        # ── 二、弱转强候选 Top ────────────────────────────────
        blocks.append(B.heading_2("二、弱转强候选 Top"))
        top_candidates = cls._safe_list(recap_doc.get("top_candidates") if recap_doc else [])
        if top_candidates:
            headers = ["股票", "题材", "候选分", "候选等级", "转换类型", "证据摘要"]
            rows: list[list[str]] = []
            for c in top_candidates[:30]:
                evidence = c.get("evidence_rules") or []
                evidence_str = " / ".join(str(e) for e in evidence[:3]) if evidence else "--"
                rows.append([
                    cls._safe_str(c.get("stock_name", c.get("stock_id", ""))),
                    cls._safe_str(c.get("subject_name", c.get("subject_key", ""))),
                    cls._safe_str(c.get("candidate_score", c.get("score", ""))),
                    cls._safe_str(c.get("candidate_level", "")),
                    cls._safe_str(c.get("transition_type", "")),
                    evidence_str,
                ])
            blocks.extend(B.table(headers, rows))
        else:
            blocks.append(B.empty_paragraph("暂无弱转强候选数据"))
        blocks.append(B.divider())

        # ── 三、正式候选 ──────────────────────────────────────
        blocks.append(B.heading_2("三、正式候选"))
        formal_candidates = cls._safe_list(recap_doc.get("formal_top_candidates") if recap_doc else [])
        if formal_candidates:
            headers = ["股票", "题材", "候选分", "支撑类型"]
            rows: list[list[str]] = [
                [
                    cls._safe_str(c.get("stock_name", c.get("stock_id", ""))),
                    cls._safe_str(c.get("subject_key", "")),
                    cls._safe_str(c.get("candidate_score", "")),
                    cls._safe_str(c.get("support_type", "")),
                ]
                for c in formal_candidates[:20]
            ]
            blocks.extend(B.table(headers, rows))
        else:
            blocks.append(B.empty_paragraph("暂无正式候选数据"))
        blocks.append(B.divider())

        # ── 四、观察候选 ──────────────────────────────────────
        blocks.append(B.heading_2("四、观察候选"))
        observe_candidates = cls._safe_list(recap_doc.get("observe_candidates") if recap_doc else [])
        if observe_candidates:
            headers = ["股票", "题材", "候选分", "支撑类型", "支撑分", "证据"]
            rows: list[list[str]] = []
            for c in observe_candidates[:20]:
                evidence = c.get("evidence_rules") or []
                evidence_str = " / ".join(str(e) for e in evidence[:3]) if evidence else "--"
                rows.append([
                    cls._safe_str(c.get("stock_name", c.get("stock_id", ""))),
                    cls._safe_str(c.get("subject_name", c.get("subject_key", ""))),
                    cls._safe_str(c.get("candidate_score", "")),
                    cls._safe_str(c.get("support_type", "")),
                    cls._safe_str(c.get("support_score", "")),
                    evidence_str,
                ])
            blocks.extend(B.table(headers, rows))
        else:
            blocks.append(B.empty_paragraph("暂无观察候选数据"))
        blocks.append(B.divider())

        # ── 五、强势股观察池历史 ──────────────────────────────
        blocks.append(B.heading_2("五、强势股观察池历史"))
        strong_watch_history = cls._safe_list(recap_doc.get("strong_watch_history") if recap_doc else [])
        if strong_watch_history:
            headers = ["股票", "题材", "状态", "等级", "watch_score", "support_type"]
            rows: list[list[str]] = [
                [
                    cls._safe_str(h.get("stock_id", "")),
                    cls._safe_str(h.get("subject_key", "")),
                    cls._safe_str(h.get("watch_status", "")),
                    cls._safe_str(h.get("strong_grade", "")),
                    cls._safe_str(h.get("watch_score", "")),
                    cls._safe_str(h.get("support_type", "")),
                ]
                for h in strong_watch_history[:50]
            ]
            history_table = B.table(headers, rows)
            blocks.append(B.toggle("强势股观察池历史（展开查看）", history_table))
        else:
            blocks.append(B.empty_paragraph("暂无强势股历史数据"))
        blocks.append(B.divider())

        # ── 六、候选诊断 ──────────────────────────────────────
        blocks.append(B.heading_2("六、候选诊断"))
        diagnostics_list = cls._safe_list(recap_doc.get("candidate_diagnostics") if recap_doc else [])
        if diagnostics_list:
            headers = ["股票", "题材", "candidate_score", "support_type", "support_score", "rank"]
            rows: list[list[str]] = [
                [
                    cls._safe_str(d.get("stock_id", "")),
                    cls._safe_str(d.get("subject_key", "")),
                    cls._safe_str(d.get("candidate_score", "")),
                    cls._safe_str(d.get("support_type", "")),
                    cls._safe_str(d.get("support_score", "")),
                    cls._safe_str(d.get("candidate_rank", "")),
                ]
                for d in diagnostics_list[:40]
            ]
            diag_table = B.table(headers, rows)
            blocks.append(B.toggle("候选诊断明细（展开查看）", diag_table))
        else:
            blocks.append(B.empty_paragraph("暂无诊断数据"))
        blocks.append(B.divider())

        # ── 七、旧链文本报告（兼容折叠区）─────────────────────
        if old_report:
            blocks.append(B.heading_2("七、旧链文本报告（兼容）"))
            old_blocks: list[dict[str, Any]] = []
            old_summary = old_report.get("summary") or ""
            if old_summary:
                old_blocks.append(B.paragraph(old_summary))
            old_sections = old_report.get("sections") or []
            if isinstance(old_sections, list):
                for sec in old_sections[:30]:
                    heading = sec.get("heading", "") if isinstance(sec, dict) else str(sec)
                    items = sec.get("items", []) if isinstance(sec, dict) else []
                    if heading:
                        old_blocks.append(B.heading_3(str(heading)[:120]))
                    for item in items[:20]:
                        old_blocks.append(B.bullet(str(item)))
            if old_blocks:
                blocks.append(B.toggle("旧链文本报告（展开查看）", old_blocks))
            else:
                blocks.append(B.empty_paragraph("旧链报告无内容"))
        else:
            blocks.append(B.heading_2("七、旧链文本报告（兼容）"))
            blocks.append(B.empty_paragraph("旧链报告未嵌入（后续解耦后此区域将移除）"))

        return blocks

    # ── 主发布入口 ─────────────────────────────────────────────

    def publish_snapshot(
        self,
        row: dict[str, Any],
        payload: dict[str, Any],
        *,
        force: bool = False,
        dry_run: bool = False,
    ) -> NotionPublishResult:
        trade_date = str(row.get("trade_date") or "")
        snapshot_version = str(row.get("snapshot_version") or "unknown")
        report_id = self._make_report_id(trade_date)

        existing = self._query_existing_page(report_id)

        # dry_run 必须在任何写操作前判断，避免误 archive
        if dry_run:
            return NotionPublishResult(
                page_id=existing["id"] if existing else "",
                page_url=existing.get("url", "") if existing else "",
                action=f"dry_run:{'would_recreate' if existing else 'would_create'}",
                report_id=report_id,
                report_type="post_market_recap",
                trade_date=trade_date,
            )

        action = "created"
        if existing:
            if self._overwrite_mode == "archive_and_recreate":
                self._archive_page(existing["id"])
                action = "recreated"
            else:
                return NotionPublishResult(
                    page_id=existing["id"],
                    page_url=existing.get("url", ""),
                    action="exists",
                    report_id=report_id,
                    report_type="post_market_recap",
                    trade_date=trade_date,
                )

        title = f"{trade_date} 盘后复盘"
        summary = self._build_summary(payload)

        page = self._create_page(
            trade_date=trade_date,
            title=title,
            report_id=report_id,
            snapshot_version=snapshot_version,
            summary=summary,
        )

        blocks = self.build_blocks(payload, trade_date)
        self._append_children(page["id"], blocks)

        return NotionPublishResult(
            page_id=page["id"],
            page_url=page.get("url", ""),
            action=action,
            report_id=report_id,
            report_type="post_market_recap",
            trade_date=trade_date,
        )

    @classmethod
    def _build_summary(cls, payload: dict[str, Any]) -> str:
        recap_doc = cls._extract_recap_doc(payload)
        if not recap_doc:
            return "--"
        candidate_count = recap_doc.get("candidate_count", 0)
        formal_count = recap_doc.get("candidate_count_formal", 0)
        watch_input = recap_doc.get("strong_watch_input_count", 0)
        return f"候选 {candidate_count} | 正式 {formal_count} | 强势池输入 {watch_input}"
