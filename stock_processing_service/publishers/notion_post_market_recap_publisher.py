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
            f"/databases/{self._database_id}/query",
            "POST",
            body=body,
        )
        results = resp.get("results") or []
        return results[0] if results else None

    def _archive_page(self, page_id: str) -> None:
        self._client.pages.update(page_id=page_id, archived=True)

    def _create_page(self, trade_date: str, title: str, report_id: str, snapshot_version: str, summary: str, report_type: str = "post_market_recap") -> dict[str, Any]:
        properties: dict[str, Any] = {
            self._title_prop: {"title": NotionBlockBuilder._rich_text(title, limit=120)},
            self._trade_date_prop: {"date": {"start": trade_date}},
            self._report_type_prop: {"select": {"name": report_type}},
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
    @classmethod
    def _build_engine_sections(cls, adapter, B) -> list[dict[str, Any]]:
        """PR-14D: Build Notion blocks from engine report."""
        blocks: list[dict[str, Any]] = []

        # ── 交易结论 ──
        tc = adapter.notion_trade_conclusion()
        allow = tc["allow_trade"]
        blocks.append(B.heading_2("交易结论"))
        blocks.append(B.callout(
            f'{"✅ 允许交易" if allow else "🚫 不交易"} | 模式: {tc["trade_mode"]} | '
            f'仓位上限: {int(tc.get("position_limit", 0) * 100)}% | '
            f'阻断: {tc.get("blocking_rule") or "无"}',
            icon="🎯"
        ))
        if tc.get("reasons"):
            blocks.append(B.paragraph("原因：" + "；".join(tc["reasons"])))
        if tc.get("next_day_strategy"):
            blocks.append(B.paragraph(f"明日策略：{tc['next_day_strategy']}"))
        blocks.append(B.divider())

        # ── 大盘环境 ──
        me = adapter.notion_market_environment()
        blocks.append(B.heading_2("大盘环境"))
        blocks.append(B.callout(
            f'大盘: {me["broad_market_regime"]} | 情绪: {me["short_term_sentiment"]} | '
            f'主线环境: {me["mainline_environment"]} | '
            f'指数数据: {"就绪" if me["index_data_ready"] else "缺失"}',
            icon="📈"
        ))
        blocks.append(B.divider())

        # ── 主线状态 ──
        mainlines = adapter.notion_mainline_states()
        if mainlines:
            blocks.append(B.heading_2("主线状态"))
            headers = ["主线", "生命周期", "可交易", "强股池", "D1", "focus", "操作建议"]
            rows = []
            for m in mainlines:
                rows.append([
                    m.get("mainline_name", ""),
                    m.get("lifecycle_state", "unknown"),
                    "✓" if m.get("mainline_trade_alive") else "✗",
                    str(m.get("strong_pool_count", 0)),
                    str(m.get("d1_count", 0)),
                    str(m.get("focus_count", 0)),
                    m.get("action_advice", ""),
                ])
            blocks.extend(B.table(headers, rows))
            blocks.append(B.divider())

        # ── D1 / 次日观察 ──
        d1_info = adapter.notion_d1_watch()
        blocks.append(B.heading_2("次日观察 (D1)"))
        blocks.append(B.callout(
            f'D1 总数: {d1_info["d1_total"]} | '
            f'formal: {d1_info["d1_formal"]} | '
            f'observe: {d1_info["d1_observe"]} | '
            f'focus: {d1_info["focus_count"]}',
            icon="📋"
        ))
        if not allow:
            blocks.append(B.paragraph("⚠️ 当前不交易，所有 D1 仅观察，不生成正式买点"))
        blocks.append(B.divider())

        return blocks

    def _build_theme_name_map(cls, old_report: dict[str, Any] | None, recap_doc: dict[str, Any]) -> dict[str, str]:
        """构建 subject_key → theme_name 映射。
        来源1：旧链 report 文本（格式「题材名：subject_key 123；...」）
        来源2：recap_doc 中带 subject_name 的条目（top_candidates, observe_candidates）
        """
        name_map: dict[str, str] = {}

        # 来源1：旧链 report 文本
        if old_report:
            sections = old_report.get("sections") or []
            if isinstance(sections, list):
                for sec in sections:
                    items = sec.get("items", []) if isinstance(sec, dict) else []
                    for item in items:
                        text = str(item)
                        if "：" not in text:
                            continue
                        theme_name, _, body = text.partition("：")
                        theme_name = theme_name.strip()
                        if not theme_name or theme_name.isdigit():
                            continue
                        for part in body.split("；"):
                            part = part.strip()
                            if part.startswith("subject_key "):
                                sk = part.replace("subject_key ", "").strip()
                                if sk and sk not in name_map:
                                    name_map[sk] = theme_name
                                break

        # 来源2：recap_doc 自身数据（top_candidates, observe_candidates）
        for source_key in ("top_candidates", "observe_candidates", "candidate_diagnostics"):
            entries = recap_doc.get(source_key) or []
            if not isinstance(entries, list):
                continue
            for entry in entries:
                sk = str(entry.get("subject_key") or "").strip()
                sn = str(entry.get("subject_name") or "").strip()
                if sk and sn and not sn.isdigit() and sn != sk:
                    if sk not in name_map:
                        name_map[sk] = sn

        return name_map

    @classmethod
    def _resolve_theme_name(cls, subject_key: str, subject_name: str | None, name_map: dict[str, str]) -> str:
        """解析题材显示名：优先 subject_name（非数字），其次 name_map，最后兜底。"""
        resolved = (subject_name or "").strip()
        if resolved and not resolved.isdigit():
            return resolved
        if subject_key in name_map:
            return name_map[subject_key]
        return f"{subject_key}"

    def _build_pre_market_engine_bridge_blocks(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        B = NotionBlockBuilder
        bridge = payload.get("engine_bridge") or {}
        if not isinstance(bridge, dict) or not bridge:
            return []

        blocks: list[dict[str, Any]] = []
        blocks.append(B.heading_2("0、引擎桥接"))
        blocks.append(
            B.callout(
                f'状态: {"就绪" if bridge.get("ready") else "未就绪"} | '
                f'交易模式: {bridge.get("trade_mode") or "no_trade"} | '
                f'允许交易: {"是" if bridge.get("allow_trade") else "否"} | '
                f'阻断: {bridge.get("no_trade_blocking_rule") or "无"}',
                icon="🧭",
            )
        )
        if bridge.get("next_day_strategy"):
            blocks.append(B.paragraph(f"次日策略：{bridge.get('next_day_strategy')}"))

        observations = bridge.get("observation_list") or []
        if observations:
            blocks.append(B.paragraph("观察清单："))
            for item in observations[:5]:
                blocks.append(B.bullet(str(item)))

        pending = bridge.get("d2_pending_list") or []
        if pending:
            blocks.append(B.paragraph("D2 待确认："))
            for item in pending[:5]:
                blocks.append(B.bullet(str(item)))

        risk_notes = bridge.get("risk_notes") or []
        if risk_notes:
            blocks.append(B.paragraph("风险提示："))
            for item in risk_notes[:5]:
                blocks.append(B.bullet(str(item)))

        exec_rows = bridge.get("execution_plan_rows") or []
        if exec_rows:
            headers = ["题材", "行动", "股票", "信号", "原因"]
            rows: list[list[str]] = []
            for row in exec_rows[:10]:
                rows.append([
                    str(row.get("theme_name") or row.get("subject_key") or "--"),
                    str(row.get("action_today") or "--"),
                    str(row.get("auction_focus_stock_name") or row.get("leader_stock_name") or "--"),
                    str(row.get("auction_signal_level") or row.get("auction_signal_type") or "--"),
                    str(row.get("watch_reason") or row.get("auction_hard_reject_reason") or "--"),
                ])
            blocks.extend(B.table(headers, rows))
        blocks.append(B.divider())
        return blocks

    def _build_pre_market_blocks(self, payload: dict[str, Any], trade_date: str) -> list[dict[str, Any]]:
        B = NotionBlockBuilder
        sections = payload.get("sections") or {}
        diagnostics = payload.get("diagnostics") or {}
        blocks: list[dict[str, Any]] = []

        blocks.extend(self._build_pre_market_engine_bridge_blocks(payload))

        blocks.append(B.heading_2("一、今日重大事件"))
        major = sections.get("major_events") or []
        if major:
            for e in major[:10]:
                title = str(e.get("title") or "?")
                summary = str(e.get("summary") or "")
                theme = str(e.get("theme_name") or "")
                source = str(e.get("source_channel") or "")
                blocks.append(B.callout(f"**{title}**\n{summary}\n🏷 {theme} | {source}", icon="📰"))
        else:
            blocks.append(B.empty_paragraph("暂无重大事件"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("二、重点题材"))
        themes = sections.get("matched_themes") or []
        if themes:
            for t in themes[:10]:
                name = str(t.get("theme_name") or "?")
                count = int(t.get("event_count") or 0)
                blocks.append(B.bullet(f"**{name}** — {count} 条事件"))
        else:
            blocks.append(B.empty_paragraph("暂无匹配题材"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("三、事件驱动机会"))
        opps = sections.get("event_driven_opportunities") or []
        if opps:
            for o in opps[:5]:
                theme = str(o.get("theme_name") or "?")
                stocks = o.get("stocks") or []
                for s in stocks[:3]:
                    name = str(s.get("stock_name") or s.get("stock_id") or "?")
                    level = str(s.get("level") or "?")
                    score = str(s.get("score") or "?")
                    blocks.append(B.bullet(f"{theme} → {name} [{level}档, {score}分]"))
        else:
            blocks.append(B.empty_paragraph("暂无事件驱动机会"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("四、风险预警"))
        risks = sections.get("risk_alerts") or []
        if risks:
            for r in risks[:5]:
                reason = str(r.get("reason") or "?")
                level = str(r.get("alert_level") or "?")
                stock = str(r.get("stock_name") or "")
                blocks.append(B.callout(f"**[{level.upper()}] {stock}** — {reason}", icon="⚠️"))
        else:
            blocks.append(B.empty_paragraph("暂无风险预警"))
        blocks.append(B.divider())

        blocks.append(B.heading_2("五、公告机会"))
        opp_alerts = sections.get("opportunity_alerts") or []
        if opp_alerts:
            for a in opp_alerts[:5]:
                reason = str(a.get("reason") or "?")
                stock = str(a.get("stock_name") or "")
                amount = str(a.get("amount") or "")
                extra = f" 💰{amount}" if amount else ""
                blocks.append(B.bullet(f"**{stock}** — {reason}{extra}"))
        else:
            blocks.append(B.empty_paragraph("暂无公告机会"))
        blocks.append(B.divider())

        sb = diagnostics.get("source_breakdown") or {}
        blocks.append(B.callout(
            f"📊 数据诊断\nmatched: {sb.get('matched_by_source',{})}\n"
            f"intel_raw: {sb.get('intel_raw_announcements',0)} matched: {sb.get('intel_matched_announcements',0)}\n"
            f"window: {diagnostics.get('pre_market_window',{}).get('start_at','?')} ~ {diagnostics.get('pre_market_window',{}).get('end_at','?')}",
            icon="📊"
        ))
        return blocks

    @classmethod
    def build_blocks(cls, payload: dict[str, Any], trade_date: str) -> list[dict[str, Any]]:
        """从 normalized payload 构造 Notion blocks。"""
        B = NotionBlockBuilder
        blocks: list[dict[str, Any]] = []

        recap_doc = cls._extract_recap_doc(payload)
        old_report = cls._extract_old_report(payload)
        name_map = cls._build_theme_name_map(old_report, recap_doc)

        # ── 标题 ──────────────────────────────────────────────
        blocks.append(B.heading_1(f"{trade_date} 盘后复盘"))

        # ── PR-14D: Engine Report (preferred when available) ───
        try:
            from stock_processing_service.application.services.engine_report_adapter import (
                EngineReportAdapter,
            )
            adapter = EngineReportAdapter(recap_doc if isinstance(recap_doc, dict) else {})
            if adapter.has_engine_data:
                blocks.extend(cls._build_engine_sections(adapter, B))
        except Exception:
            pass

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
                    cls._resolve_theme_name(cls._safe_str(c.get("subject_key", "")), c.get("subject_name"), name_map),
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
                    cls._resolve_theme_name(cls._safe_str(c.get("subject_key", "")), c.get("subject_name"), name_map),
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
                    cls._resolve_theme_name(cls._safe_str(c.get("subject_key", "")), c.get("subject_name"), name_map),
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
                    cls._resolve_theme_name(cls._safe_str(h.get("subject_key", "")), h.get("subject_name"), name_map),
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
                    cls._resolve_theme_name(cls._safe_str(d.get("subject_key", "")), d.get("subject_name"), name_map),
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
            old_summary = old_report.get("summary") or ""
            if old_summary:
                blocks.append(B.paragraph(old_summary))
            old_sections = old_report.get("sections") or []
            if isinstance(old_sections, list):
                for sec in old_sections[:8]:
                    heading = sec.get("heading", "") if isinstance(sec, dict) else str(sec)
                    items = sec.get("items", []) if isinstance(sec, dict) else []
                    sec_blocks: list[dict[str, Any]] = [
                        B.paragraph(str(item)) for item in items[:5]
                    ]
                    if sec_blocks:
                        blocks.append(B.toggle(str(heading)[:120], sec_blocks))
                    elif heading:
                        blocks.append(B.bullet(str(heading)[:120]))
            if not old_summary and not old_sections:
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
        report_type: str = "post_market_recap",
    ) -> NotionPublishResult:
        trade_date = str(row.get("trade_date") or "")
        snapshot_version = str(row.get("snapshot_version") or "unknown")
        report_id = self._make_report_id(trade_date) if report_type == "post_market_recap" else f"pre_market_brief:{trade_date}"

        existing = self._query_existing_page(report_id)

        # dry_run 必须在任何写操作前判断，避免误 archive
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

        title = f"{trade_date} 盘后复盘" if report_type == "post_market_recap" else f"{trade_date} 盘前必读"
        summary = self._build_summary(payload)

        page = self._create_page(
            trade_date=trade_date,
            title=title,
            report_id=report_id,
            snapshot_version=snapshot_version,
            summary=summary,
            report_type=report_type,
        )

        if report_type == "pre_market_brief":
            blocks = self._build_pre_market_blocks(payload, trade_date)
        else:
            blocks = self.build_blocks(payload, trade_date)
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
            return "--"
        candidate_count = recap_doc.get("candidate_count", 0)
        formal_count = recap_doc.get("candidate_count_formal", 0)
        watch_input = recap_doc.get("strong_watch_input_count", 0)
        return f"候选 {candidate_count} | 正式 {formal_count} | 强势池输入 {watch_input}"
