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
        promoted_count = self._int(recap_doc.get("strong_watch_promoted_count"))
        d1_pass = self._int(recap_doc.get("d1_pass"))

        formal_candidates = list(recap_doc.get("formal_top_candidates") or [])
        observe_candidates = list(recap_doc.get("observe_candidates") or [])
        top_candidates = list(recap_doc.get("top_candidates") or [])
        promoted_pool = list(recap_doc.get("promoted_pool_preview") or [])

        dependency_status = self._dependency_status(recap_doc)
        missing_dependencies = [name for name, ok in dependency_status.items() if not ok]

        highlights = [
            f"强势观察池更新 {pool_written} 条，历史跟踪 {strong_watch_count} 条",
            f"弱转强候选通过 {d1_pass} 条，正式 {formal_count} 条，观察 {observe_count} 条",
            f"最终候选合计 {candidate_count} 条，晋级输入 {promoted_count} 条",
        ]
        if missing_dependencies:
            highlights.append(f"新链依赖未完全命中：{','.join(missing_dependencies)}")

        sections = [
            {
                "heading": "正式候选",
                "items": self._candidate_lines(formal_candidates or top_candidates, limit=12),
            },
            {
                "heading": "观察候选",
                "items": self._candidate_lines(observe_candidates, limit=10),
            },
            {
                "heading": "强势池输入",
                "items": self._pool_lines(promoted_pool, limit=12),
            },
            {
                "heading": "链路状态",
                "items": self._dependency_lines(dependency_status),
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
                    "strong_watch_promoted_count": promoted_count,
                    "d1_pass": d1_pass,
                },
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
    def _candidate_lines(rows: list[Any], *, limit: int) -> list[str]:
        lines: list[str] = []
        for row in rows[:limit]:
            item = dict(row or {})
            stock_name = str(item.get("stock_name") or item.get("stock_id") or "").strip()
            subject_name = str(item.get("subject_name") or item.get("subject_key") or "").strip()
            score = str(item.get("candidate_score") or item.get("watch_score") or "").strip()
            support_type = str(item.get("support_type") or "").strip()
            parts = [
                part
                for part in (stock_name, subject_name, f"score={score}" if score else "", support_type)
                if part
            ]
            if parts:
                lines.append(" / ".join(parts))
        return lines or ["暂无候选"]

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
    def _dependency_lines(status: dict[str, bool]) -> list[str]:
        return [f"{name}: {'ok' if ok else 'missing'}" for name, ok in status.items()]

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0
