"""NewChainIntelFeedAdapter — 新链数据 → 情报台统一适配层。

职责：
1. 通过 DatabaseGateway 读取新链各业务表
2. 把不同表的数据统一转换为 IntelFeedItem dict
3. 支持 feed_date / session / item_type / limit 过滤
4. 输出给现有 /api/v1/intel_feed 和 /api/v1/intel_feed/defaults

架构规则：不直接 SQL，读写均通过 DatabaseGateway 完成。
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database_service.gateway import DatabaseGateway

logger = logging.getLogger(__name__)

# ── Item type → sort priority (higher = shown first) ──────────────────────
ITEM_TYPE_PRIORITY: Dict[str, int] = {
    "recap": 100,
    "weak_to_strong": 90,
    "theme_cycle": 85,
    "theme_identity": 80,
    "stock_signal": 70,
    "event": 60,
    "theme_history": 50,
    # 旧链保留类型 (fallback)
    "new_theme": 40,
    "event_review": 35,
    "theme_move": 30,
    "stock_move": 25,
}

# strong_stock_watch_pool 默认展示上限
DEFAULT_STRONG_STOCK_LIMIT = 20


class NewChainIntelFeedAdapter:
    """新链情报台统一适配器。"""

    __slots__ = ("_gw", "_strong_stock_limit")

    def __init__(self, gateway: DatabaseGateway, strong_stock_limit: int = DEFAULT_STRONG_STOCK_LIMIT) -> None:
        self._gw = gateway
        self._strong_stock_limit = strong_stock_limit

    # ── Per-source loaders ───────────────────────────────────────────────

    async def load_recap_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """post_market_recap_snapshot → recap 类情报项。"""
        rows = await self._gw.get_new_chain_intel_recap(feed_date)
        items: List[Dict[str, Any]] = []
        for row in rows:
            raw = row.get("payload") or {}
            if isinstance(raw, str):
                try:
                    import json as _json
                    raw = _json.loads(raw)
                except Exception:
                    raw = {}
            payload: dict = raw if isinstance(raw, dict) else {}
            recap_doc = payload.get("recap_doc", payload)
            report = payload.get("report", {})
            # 摘要信息
            candidate_count = recap_doc.get("candidate_count", recap_doc.get("formal_candidates", 0))
            strong_watch_count = recap_doc.get("strong_watch_promoted_count",
                                                recap_doc.get("strong_watch_input_count", 0))
            top_themes = report.get("highlights", [])[:5] if report else []

            summary_parts = [f"主线题材 {len(top_themes)} 个" if top_themes else "",
                             f"强势股观察 {strong_watch_count} 只" if strong_watch_count else "",
                             f"弱转强候选 {candidate_count} 只" if candidate_count else ""]
            summary = "；".join(p for p in summary_parts if p) or "盘后复盘已生成"

            items.append({
                "item_id": f"recap:{feed_date.isoformat()}",
                "item_type": "recap",
                "occurred_at": f"{feed_date.isoformat()}T15:30:00",
                "title": f"{feed_date.isoformat()} 盘后复盘已生成",
                "summary": summary,
                "theme_subject_keys": [],
                "theme_names": [],
                "stock_ids": [],
                "stock_names": [],
                "confidence": None,
                "impact_score": 90,
                "source_type": "post_market_recap_snapshot",
                "source_channel": "new_chain",
            })
        return items

    async def load_theme_identity_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """theme_mainline_identity_registry → theme_identity 类情报项。"""
        rows = await self._gw.get_new_chain_intel_identity(feed_date)
        items: List[Dict[str, Any]] = []
        for row in rows:
            subject_key = str(row.get("subject_key", ""))
            theme_name = str(row.get("theme_name") or subject_key)
            identity_status = str(row.get("identity_status") or "")
            composite = round(float(row.get("composite_score") or 0), 1)

            title = f"{theme_name} 确认为主线题材"
            summary = f"综合评分: {composite}；逻辑: {round(float(row.get('logic_score') or 0), 1)}；市场: {round(float(row.get('market_score') or 0), 1)}"

            items.append({
                "item_id": f"theme_identity:{subject_key}:{feed_date.isoformat()}",
                "item_type": "theme_identity",
                "occurred_at": f"{feed_date.isoformat()}T15:30:00",
                "title": title,
                "summary": summary,
                "theme_subject_keys": [subject_key],
                "theme_names": [theme_name],
                "stock_ids": [],
                "stock_names": [],
                "confidence": float(row.get("llm_confidence") or 0) if row.get("llm_confidence") else None,
                "impact_score": composite,
                "source_type": "theme_mainline_identity_registry",
                "source_channel": "new_chain",
            })
        return items

    async def load_theme_cycle_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """theme_cycle_judgement_v2 → theme_cycle 类情报项。"""
        rows = await self._gw.get_new_chain_intel_cycle(feed_date)
        items: List[Dict[str, Any]] = []
        for row in rows:
            subject_key = str(row.get("subject_key", ""))
            theme_name = str(row.get("theme_name") or subject_key)
            final_cycle = str(row.get("final_cycle_state") or "unknown")
            final_alive = bool(row.get("final_mainline_alive"))
            fade_watch = bool(row.get("fade_watch"))
            fade_confirmed = bool(row.get("fade_confirmed"))
            mainline_strength = round(float(row.get("mainline_strength_score") or 0), 1)
            prev_cycle = str(row.get("previous_cycle_state") or "")
            transition = str(row.get("state_transition_reason") or "")

            # 构建标题 & 摘要
            cycle_map = {
                "start": "启动", "maintain": "维持", "divergence": "分歧",
                "fade": "退潮", "fade_watch": "退潮预警", "fade_confirmed": "退潮确认",
            }
            cycle_label = cycle_map.get(final_cycle, final_cycle)

            if fade_confirmed:
                title = f"{theme_name} 周期退潮确认"
                summary = "退潮已确认；后续移出主线追踪"
            elif fade_watch:
                title = f"{theme_name} 周期退潮预警"
                summary = f"退潮预警；强度: {mainline_strength}" + (f"；原因: {transition}" if transition else "")
            elif final_alive:
                if prev_cycle and prev_cycle != final_cycle:
                    title = f"{theme_name} 周期状态变更: {cycle_label}"
                else:
                    title = f"{theme_name} 周期维持: {cycle_label}"
                summary = f"仍为主线；强度: {mainline_strength}" + (f"；原因: {transition}" if transition else "")
            else:
                title = f"{theme_name} 周期状态: {cycle_label}"
                summary = f"主线信号减弱；强度: {mainline_strength}" + (f"；原因: {transition}" if transition else "")

            items.append({
                "item_id": f"theme_cycle:{subject_key}:{feed_date.isoformat()}",
                "item_type": "theme_cycle",
                "occurred_at": f"{feed_date.isoformat()}T15:30:00",
                "title": title,
                "summary": summary,
                "theme_subject_keys": [subject_key],
                "theme_names": [theme_name],
                "stock_ids": [],
                "stock_names": [],
                "confidence": round(float(row.get("confidence_score") or 0), 3) if row.get("confidence_score") else None,
                "impact_score": mainline_strength,
                "source_type": "theme_cycle_judgement_v2",
                "source_channel": "new_chain",
            })
        return items

    async def load_strong_stock_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """strong_stock_watch_pool → stock_signal 类情报项（top N）。"""
        rows = await self._gw.get_new_chain_intel_strong_watch(
            feed_date, limit_per_source=self._strong_stock_limit
        )
        items: List[Dict[str, Any]] = []
        for row in rows:
            stock_id = str(row.get("stock_id", ""))
            stock_name = str(row.get("stock_name", ""))
            subject_key = str(row.get("subject_key", ""))
            theme_name = str(row.get("theme_name") or subject_key)
            pool_type = str(row.get("pool_entry_type") or "")
            watch_score = round(float(row.get("watch_score") or 0), 1)
            watch_status = str(row.get("watch_status") or "")
            support_type = str(row.get("support_type") or "")
            candidate_promoted = bool(row.get("candidate_promoted"))

            pool_label = "进入强势追踪池" if pool_type == "formal" else "进入强势观察池"
            if candidate_promoted:
                pool_label += " (已晋升候选)"

            summary_parts = [
                f"关联题材: {theme_name}",
                f"强势评分: {watch_score}",
                f"状态: {watch_status}" if watch_status else "",
                f"支撑: {support_type}" if support_type else "",
            ]
            summary = "；".join(p for p in summary_parts if p)

            items.append({
                "item_id": f"stock_signal:strong_watch:{stock_id}:{feed_date.isoformat()}",
                "item_type": "stock_signal",
                "occurred_at": f"{feed_date.isoformat()}T15:30:00",
                "title": f"{stock_name}({stock_id}) {pool_label}",
                "summary": summary,
                "theme_subject_keys": [subject_key] if subject_key else [],
                "theme_names": [theme_name] if theme_name else [],
                "stock_ids": [stock_id] if stock_id else [],
                "stock_names": [stock_name] if stock_name else [],
                "confidence": None,
                "impact_score": watch_score,
                "source_type": "strong_stock_watch_pool",
                "source_channel": "new_chain",
            })
        return items

    async def load_weak_to_strong_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """weak_to_strong_candidate_pool → weak_to_strong 类情报项。"""
        rows = await self._gw.get_new_chain_intel_w2s(feed_date)
        items: List[Dict[str, Any]] = []
        for row in rows:
            stock_id = str(row.get("stock_id", ""))
            stock_name = str(row.get("stock_name", ""))
            subject_key = str(row.get("subject_key", ""))
            theme_name = str(row.get("theme_name") or subject_key)
            candidate_score = round(float(row.get("candidate_score") or 0), 1)
            weak_type = str(row.get("weak_type") or "")
            candidate_type = str(row.get("candidate_type") or "")
            support_type = str(row.get("support_type") or "")
            support_level = round(float(row.get("support_level") or 0), 1)
            is_dragon_head = bool(row.get("is_dragon_head"))

            type_map = {
                "strong_trend_repair": "弱转强修复候选",
                "weak_breakout": "弱转强突破候选",
            }
            type_label = type_map.get(candidate_type, "弱转强候选")

            summary_parts = [
                f"关联题材: {theme_name}",
                f"候选评分: {candidate_score}",
                f"弱态类型: {weak_type}" if weak_type else "",
                f"支撑: {support_type}({support_level})" if support_type else "",
                "龙头股" if is_dragon_head else "",
            ]
            summary = "；".join(p for p in summary_parts if p)

            items.append({
                "item_id": f"stock_signal:w2s:{stock_id}:{feed_date.isoformat()}",
                "item_type": "weak_to_strong",
                "occurred_at": f"{feed_date.isoformat()}T15:30:00",
                "title": f"{stock_name}({stock_id}) {type_label}",
                "summary": summary,
                "theme_subject_keys": [subject_key] if subject_key else [],
                "theme_names": [theme_name] if theme_name else [],
                "stock_ids": [stock_id] if stock_id else [],
                "stock_names": [stock_name] if stock_name else [],
                "confidence": None,
                "impact_score": candidate_score,
                "source_type": "weak_to_strong_candidate_pool",
                "source_channel": "new_chain",
            })
        return items

    # ── Main query ──────────────────────────────────────────────────────

    async def get_intel_feed(
        self,
        feed_date: date,
        session: str = "all",
        item_type: str = "all",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """从新链数据源聚合情报项，返回按优先级+评分排序的列表。"""
        all_items: List[Dict[str, Any]] = []

        # 每项 load 失败不阻断其余源
        async def _safe_load(label: str, coro):
            try:
                return await coro
            except Exception:
                logger.warning("NewChainIntelFeedAdapter: load %s failed for %s", label, feed_date, exc_info=True)
                return []

        all_items.extend(await _safe_load("recap", self.load_recap_items(feed_date)))
        all_items.extend(await _safe_load("weak_to_strong", self.load_weak_to_strong_items(feed_date)))
        all_items.extend(await _safe_load("theme_cycle", self.load_theme_cycle_items(feed_date)))
        all_items.extend(await _safe_load("theme_identity", self.load_theme_identity_items(feed_date)))
        all_items.extend(await _safe_load("strong_stock", self.load_strong_stock_items(feed_date)))

        # session 过滤（新链数据默认 post_market，只有 all/post 可见）
        if session not in ("all", "post", ""):
            all_items = []

        # item_type 过滤
        if item_type != "all":
            all_items = [it for it in all_items if it["item_type"] == item_type]

        # 排序：priority desc → impact_score desc → occurred_at desc
        def _sort_key(it: Dict[str, Any]) -> tuple[int, float, str]:
            pri = ITEM_TYPE_PRIORITY.get(str(it.get("item_type") or ""), 0)
            score = float(it.get("impact_score") or 0)
            occurred = str(it.get("occurred_at") or "")
            return (-pri, -score, occurred)

        all_items.sort(key=_sort_key)
        return all_items[:limit]

    async def get_latest_date(self) -> Optional[str]:
        """返回新链各源的最大日期，不做 fallback。"""
        best: Optional[date] = None
        for source_date in [
            await self._gw.get_latest_post_market_recap_trade_date(),
            await self._gw.get_latest_strong_watch_trade_date(),
        ]:
            if source_date:
                d = source_date if isinstance(source_date, date) else datetime.fromisoformat(str(source_date)).date()
                if best is None or d > best:
                    best = d
        # 额外：cycle_judgement_v2 和 identity_registry 在 gateway 无 latest 方法
        # 这里 fallback 到已知最新。后续如果要精确到表级，可加新 gateway 方法。
        return best.isoformat() if best else None

    async def get_source_counts(self, feed_date: date) -> Dict[str, int]:
        """返回各源当前日期行数（调试用）。"""
        counts: Dict[str, int] = {}
        for label, loader in [
            ("post_market_recap_snapshot", self.load_recap_items),
            ("theme_mainline_identity_registry", self.load_theme_identity_items),
            ("theme_cycle_judgement_v2", self.load_theme_cycle_items),
            ("weak_to_strong_candidate_pool", self.load_weak_to_strong_items),
        ]:
            try:
                items = await loader(feed_date)
                counts[label] = len(items)
            except Exception:
                counts[label] = -1

        try:
            raw = await self._gw.get_new_chain_intel_strong_watch(feed_date, limit_per_source=9999)
            counts["strong_stock_watch_pool"] = len(raw)
        except Exception:
            counts["strong_stock_watch_pool"] = -1
        return counts
