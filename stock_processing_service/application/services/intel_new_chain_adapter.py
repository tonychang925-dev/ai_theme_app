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
import re
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from database_service.gateway import DatabaseGateway

logger = logging.getLogger(__name__)

# ── Item type → sort priority (higher = shown first) ──────────────────────
ITEM_TYPE_PRIORITY: Dict[str, int] = {
    # 新闻事件（旧链核心内容）— 最高优先级，new_theme 与 event 同级
    "event": 100,
    "new_theme": 100,
    "event_review": 95,
    # 新链信号 — 略低但不被淹没
    "recap": 85,
    "weak_to_strong": 80,
    "theme_cycle": 75,
    "theme_identity": 70,
    "stock_signal": 60,
    # 旧链其他
    "theme_move": 50,
    "stock_move": 40,
    "theme_history": 30,
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
            candidate_count = int(row.get("candidate_count") or 0)
            strong_watch_count = int(row.get("strong_watch_input_count") or 0)
            highlights_raw = row.get("highlights") or []
            if isinstance(highlights_raw, str):
                try:
                    import json as _json
                    highlights_raw = _json.loads(highlights_raw)
                except Exception:
                    highlights_raw = []
            top_themes = (highlights_raw or [])[:5]

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

    async def load_news_event_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """旧链：news_event + event_theme_map + theme_master → event 情报项。"""
        try:
            rows = await self._gw.get_intel_news_events(feed_date)
        except Exception:
            return []
        items: List[Dict[str, Any]] = []
        for row in rows:
            items.append({
                "item_id": str(row.get("item_id", "")),
                "item_type": "event",
                "occurred_at": str(row.get("occurred_at") or ""),
                "title": str(row.get("title") or ""),
                "summary": str(row.get("summary") or ""),
                "theme_subject_keys": list(row.get("theme_subject_keys") or []),
                "theme_names": list(row.get("theme_names") or []),
                "stock_ids": [],
                "stock_names": [],
                "confidence": float(row.get("confidence") or 0) if row.get("confidence") else None,
                "impact_score": float(row.get("impact_score") or 0),
                "source_type": str(row.get("source_type", "event_theme_map")),
                "source_channel": str(row.get("source_channel", "realtime_news")),
            })
        return items

    async def load_review_event_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """event_review_queue → event_review 情报项。"""
        fn = getattr(self._gw, "get_pre_market_review_events", None)
        if not callable(fn):
            return []
        try:
            rows = await fn(feed_date, limit=200)
        except Exception:
            return []
        items: List[Dict[str, Any]] = []
        for row in rows or []:
            theme_name = str(row.get("theme_name") or "")
            source_channel = self._normalize_review_source_channel(row.get("source_channel"))
            items.append({
                "item_id": str(row.get("item_id") or f"review:{row.get('event_id', '')}"),
                "item_type": "event_review",
                "occurred_at": str(row.get("occurred_at") or ""),
                "title": str(row.get("title") or ""),
                "summary": str(row.get("summary") or row.get("reason") or ""),
                "theme_subject_keys": [],
                "theme_names": [theme_name] if theme_name else [],
                "stock_ids": [],
                "stock_names": [],
                "confidence": float(row.get("confidence") or 0) if row.get("confidence") else None,
                "impact_score": float(row.get("impact_score") or 0),
                "source_type": str(row.get("source_type") or "event_review_queue"),
                "source_channel": source_channel,
            })
        return items

    async def load_subject_history_items(self, feed_date: date) -> List[Dict[str, Any]]:
        """旧链：subject_history_staging JYHF CDP → event / new_theme 情报项。"""
        try:
            rows = await self._gw.get_intel_subject_history(feed_date)
        except Exception:
            return []
        # 中文题材名 → JYHF 数字 key 映射
        names = list({str(row.get("title") or "") for row in rows if row.get("title")})
        name_to_key: dict[str, str] = {}
        if names:
            try:
                name_to_key = await self._gw.resolve_subject_keys_by_names(names)
            except Exception:
                pass
        items: List[Dict[str, Any]] = []
        for row in rows:
            summary = str(row.get("summary") or "")
            title = str(row.get("title") or "")
            is_new_theme = ("新题材更新" in title or "新题材更新" in summary)
            items.append({
                "item_id": str(row.get("item_id", "")),
                "item_type": "new_theme" if is_new_theme else "event",
                "occurred_at": str(row.get("occurred_at") or ""),
                "title": title,
                "summary": summary,
                "theme_subject_keys": [name_to_key.get(title, "")] if name_to_key.get(title) else [],
                "theme_names": list(row.get("theme_names") or []),
                "stock_ids": [],
                "stock_names": [],
                "confidence": float(row.get("confidence") or 0) if row.get("confidence") else None,
                "impact_score": float(row.get("impact_score") or 0),
                "source_type": str(row.get("source_type") or "jyhf_cdp_dom"),
                "source_channel": str(row.get("source_channel") or "jyhf_cdp"),
            })
        return items

    async def get_intel_feed(
        self,
        feed_date: date,
        session: str = "all",
        item_type: str = "all",
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """聚合情报项：新链信号 + 旧链新闻事件，按优先级排序。"""
        all_items: List[Dict[str, Any]] = []

        # 新链信号 + 旧链新闻事件 — asyncio.gather 并行加载
        import asyncio as _asyncio
        loaders = [
            ("recap", self.load_recap_items(feed_date)),
            ("weak_to_strong", self.load_weak_to_strong_items(feed_date)),
            ("theme_cycle", self.load_theme_cycle_items(feed_date)),
            ("theme_identity", self.load_theme_identity_items(feed_date)),
            ("strong_stock", self.load_strong_stock_items(feed_date)),
            ("news_event", self.load_news_event_items(feed_date)),
            ("review_event", self.load_review_event_items(feed_date)),
            ("subject_history", self.load_subject_history_items(feed_date)),
        ]
        results = await _asyncio.gather(*[coro for _, coro in loaders], return_exceptions=True)
        for (label, _), result in zip(loaders, results):
            if isinstance(result, Exception):
                logger.warning("NewChainIntelFeedAdapter: load %s failed for %s: %s", label, feed_date, result)
            elif isinstance(result, list):
                all_items.extend(result)

        all_items = self._dedupe_feed_items(all_items)

        # session 过滤（仅 event 类 item 有实际时间，新链信号默认 post_market）
        if session not in ("all", ""):
            filtered: List[Dict[str, Any]] = []
            for it in all_items:
                if it["item_type"] not in ("event",):
                    if session in ("all", "post", ""):
                        filtered.append(it)
                    continue
                occurred = it.get("occurred_at", "")
                if not occurred:
                    filtered.append(it)
                    continue
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(str(occurred).replace("Z", "+00:00"))
                    hm = dt.hour * 60 + dt.minute
                    if session == "pre" and hm < 9 * 60 + 30:
                        filtered.append(it)
                    elif session == "intra" and 9 * 60 + 30 <= hm < 15 * 60:
                        filtered.append(it)
                    elif session == "post" and hm >= 15 * 60:
                        filtered.append(it)
                except Exception:
                    filtered.append(it)
            all_items = filtered

        # item_type 过滤
        if item_type != "all":
            all_items = [it for it in all_items if it["item_type"] == item_type]

        # 排序：priority desc → occurred_at desc（事件最新在上），score desc tiebreak
        def _sort_key(it: Dict[str, Any]) -> tuple[int, int, float]:
            pri = ITEM_TYPE_PRIORITY.get(str(it.get("item_type") or ""), 0)
            score = float(it.get("impact_score") or 0)
            occurred = str(it.get("occurred_at") or "")
            # 解析时间戳为 epoch 秒，失败用 0；取负实现降序
            try:
                from datetime import datetime
                ts = int(datetime.fromisoformat(occurred.replace("Z", "+00:00")).timestamp())
            except Exception:
                ts = 0
            # 事件类 -ts 实现时间降序（最新在上）
            if it.get("item_type") in ("event", "event_review", "new_theme"):
                return (-pri, -ts, -score)
            return (-pri, 0, -score)

        all_items.sort(key=_sort_key)
        return all_items[:limit]

    @staticmethod
    def _normalize_review_source_channel(value: Any) -> str:
        source = str(value or "").strip()
        if source in {"", "realtime_news", "structured_theme_match", "event_theme_matcher"}:
            return "akshare_realtime"
        return source

    @staticmethod
    def _dedupe_feed_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        best_by_key: Dict[tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]], Dict[str, Any]] = {}
        for item in items:
            key = NewChainIntelFeedAdapter._feed_item_dedupe_key(item)
            previous = best_by_key.get(key)
            if previous is None or NewChainIntelFeedAdapter._feed_item_rank(item) > NewChainIntelFeedAdapter._feed_item_rank(previous):
                best_by_key[key] = item
        return list(best_by_key.values())

    @staticmethod
    def _feed_item_dedupe_key(item: Dict[str, Any]) -> tuple[str, tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
        title = NewChainIntelFeedAdapter._normalize_feed_text(str(item.get("title") or ""))
        if not title:
            title = NewChainIntelFeedAdapter._normalize_feed_text(str(item.get("summary") or ""))
        theme_names = tuple(
            sorted(
                {
                    NewChainIntelFeedAdapter._normalize_feed_text(str(value))
                    for value in (item.get("theme_names") or [])
                    if str(value).strip()
                }
            )
        )
        theme_keys = tuple(
            sorted(
                {
                    NewChainIntelFeedAdapter._normalize_feed_text(str(value))
                    for value in (item.get("theme_subject_keys") or [])
                    if str(value).strip()
                }
            )
        )
        stock_ids = tuple(
            sorted(
                {
                    NewChainIntelFeedAdapter._normalize_feed_text(str(value))
                    for value in (item.get("stock_ids") or [])
                    if str(value).strip()
                }
            )
        )
        return (title, theme_names, theme_keys, stock_ids)

    @staticmethod
    def _feed_item_rank(item: Dict[str, Any]) -> tuple[int, int, float]:
        priority = ITEM_TYPE_PRIORITY.get(str(item.get("item_type") or ""), 0)
        occurred_at = str(item.get("occurred_at") or "")
        try:
            ts = int(datetime.fromisoformat(occurred_at.replace("Z", "+00:00")).timestamp())
        except Exception:
            ts = 0
        score = float(item.get("impact_score") or 0)
        return (priority, ts, score)

    @staticmethod
    def _normalize_feed_text(value: str) -> str:
        return re.sub(r"[\s【】\[\]（）()、,，.。:：;；\-_/]+", "", value).lower()

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
