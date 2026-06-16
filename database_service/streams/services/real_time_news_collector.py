"""
实时新闻采集服务 (RealTimeNewsCollector) — Phase 4E 升级版。

唯一正式新闻采集入口。主流程：
  fetch (crawler only, 不做过滤/去重)
  → normalize (NewsPayloadNormalizer)
  → prefilter (NewsPreFilterAdapter, 统一规则)
  → semantic dedup batch (SemanticEventDeduper)
  → semantic dedup recent (SemanticEventDeduper)
  → publish stream:news:raw
  → add to recent cache

Phase 4E (2026-05-24):
  - 接入 SemanticEventDeduper（batch + recent + Qwen + 预算保护 + 硬保护）
  - 接入 NewsPayloadNormalizer（标准化 + collector_name 标记）
  - 统一 prefilter 为 NewsPreFilterAdapter
  - Qwen 启动时异步预热
  - 统计增强
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Phase 4E: 统一 prefilter — NewsPreFilterAdapter（替换 LocalQwenNewsTriageService）
try:
    from database_service.streams.services.news_prefilter_adapter import NewsPreFilterAdapter
    HAS_NEWS_PREFILTER = True
except Exception:
    NewsPreFilterAdapter = None  # type: ignore
    HAS_NEWS_PREFILTER = False

# Phase 4E: 语义去重器
try:
    from database_service.streams.services.semantic_event_deduper import SemanticEventDeduper
    HAS_SEMANTIC_DEDUPER = True
except Exception:
    SemanticEventDeduper = None  # type: ignore
    HAS_SEMANTIC_DEDUPER = False

# Phase 4E: Payload 标准化器
try:
    from database_service.streams.services.news_payload_normalizer import normalize_news_payload
except Exception:
    normalize_news_payload = None  # type: ignore


class CollectionMode(Enum):
    REAL = "real"
    AUTO = "auto"


class RealTimeNewsCollector:
    """实时新闻采集服务 — 唯一正式入口。"""

    def __init__(
        self,
        stream_manager,
        crawler_service_client=None,
        news_producer=None,
        config: Optional[Dict] = None
    ):
        self.stream_manager = stream_manager
        self.crawler_client = crawler_service_client
        self.news_producer = news_producer
        self.config = config or {}

        # 配置参数
        self.collection_interval = self.config.get("collection_interval", 300)
        self.max_retries = self.config.get("max_retries", 3)
        self.retry_delay = self.config.get("retry_delay", 10)
        default_mode_value = str(self.config.get("default_mode", "auto")).lower()
        if default_mode_value == "mock":
            logger.warning("检测到 default_mode=mock，核心链路已禁用mock，自动改为auto")
            default_mode_value = "auto"
        self.default_mode = CollectionMode(default_mode_value)

        # Backpressure: avoid publishing more raw news when the storage consumer is
        # falling behind the bounded Redis Stream retention window.
        self.redis_url = str(self.config.get("redis_url") or os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0"))
        self.raw_stream_key = str(self.config.get("raw_stream_key", "stream:news:raw"))
        self.raw_consumer_group = str(self.config.get("raw_consumer_group", "news_storage_realtime"))
        self.enable_raw_backpressure = bool(self.config.get("enable_raw_backpressure", True))
        self.raw_backpressure_lag_ratio = float(self.config.get("raw_backpressure_lag_ratio", 0.70))
        self.raw_backpressure_delivery_lag_s = float(self.config.get("raw_backpressure_delivery_lag_s", 300))
        self.raw_backpressure_pending = int(self.config.get("raw_backpressure_pending", 1000))

        # prefilter
        self.enable_collector_prefilter = bool(self.config.get("enable_collector_prefilter", True))
        self.collector_drop_on_skip = bool(self.config.get("collector_drop_on_skip", True))

        # CLS 采集: 时间窗口 + 安全上限，替代固定条数截断
        self.cls_max_age_minutes = int(self.config.get("cls_max_age_minutes", 10))
        self.cls_max_items = int(self.config.get("cls_max_items", 60))

        # news_id 短窗口去重（保留作为快速第一层）
        self.dedup_window_seconds = int(self.config.get("collector_dedup_window_seconds", 1800))
        self._recent_news_ids: Dict[str, float] = {}

        # 永久去重（同 _seen set）：SHA1，同进程生命周期内不重发
        self._seen_dedupe_keys: set[str] = set()

        # prefilter 被过滤的 key（定期清空，允许 prefilter 变更后重评）
        self._filtered_keys: set[str] = set()
        self._filtered_cycles = 0

        # prefilter skip log（调试用）
        prefilter_skip_log = self.config.get("prefilter_skip_log_path", "")
        self._prefilter_skip_log = Path(prefilter_skip_log) if prefilter_skip_log else None
        if self._prefilter_skip_log:
            try:
                self._prefilter_skip_log.parent.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass

        # Phase 4E: 统一 prefilter — NewsPreFilterAdapter
        self._prefilter: Optional[NewsPreFilterAdapter] = None
        if self.enable_collector_prefilter and HAS_NEWS_PREFILTER:
            model_path = str(self.config.get("semantic_dedup_model_path", ""))
            self._prefilter = NewsPreFilterAdapter(
                enabled=True,
                mode="rule_prompt",  # Phase 4E: 灰区 Qwen 判定，减少噪音入 stream
                model_path=model_path,
                fail_open=True,
            )
            logger.info("新闻采集前预筛选已启用: NewsPreFilterAdapter mode=rule_prompt")
        elif self.enable_collector_prefilter:
            logger.warning("新闻采集前预筛选启用失败: NewsPreFilterAdapter 不可用")

        # Phase 4E: 语义去重器
        self._deduper: Optional[SemanticEventDeduper] = None
        self.enable_semantic_dedup = bool(self.config.get("enable_semantic_dedup", True))
        if self.enable_semantic_dedup and HAS_SEMANTIC_DEDUPER and self._prefilter:
            model_path = str(self.config.get("semantic_dedup_model_path", ""))
            self._deduper = SemanticEventDeduper(
                prefilter=NewsPreFilterAdapter(
                    enabled=True,
                    mode=str(self.config.get("semantic_dedup_mode", "rule_prompt")),
                    model_path=model_path,
                    fail_open=True,
                ),
                recent_max_size=int(self.config.get("semantic_dedup_recent_max_size", 500)),
                recent_max_age_hours=int(self.config.get("semantic_dedup_recent_max_age_hours", 6)),
                qwen_max_per_round=int(self.config.get("qwen_max_per_round", 20)),
                qwen_max_candidates_per_news=int(self.config.get("qwen_max_candidates_per_news", 5)),
                qwen_max_recent_comparisons=int(self.config.get("qwen_max_recent_comparisons", 50)),
                audit_dir=self.config.get("semantic_dedup_audit_dir",
                    "tmp/product_runtime_phase4e_semantic_dedupe"),
            )
            logger.info(
                "语义去重已启用: mode=%s budget=%d/%d/%d",
                self.config.get("semantic_dedup_mode", "rule_prompt"),
                int(self.config.get("qwen_max_per_round", 20)),
                int(self.config.get("qwen_max_candidates_per_news", 5)),
                int(self.config.get("qwen_max_recent_comparisons", 50)),
            )
        elif self.enable_semantic_dedup:
            logger.warning("语义去重启用失败: SemanticEventDeduper 或 prefilter 不可用")

        # Phase 4E: Qwen warmup 标记
        self._qwen_warmup = bool(self.config.get("qwen_dedup_warmup", True))

        # 运行状态
        self.is_running = False
        self.collection_task: Optional[asyncio.Task] = None
        self.stats: Dict[str, Any] = {
            "started_at": None,
            "total_collections": 0,
            "successful_collections": 0,
            "failed_collections": 0,
            "last_collection_time": None,
            "last_collection_result": None,
            "mode_history": [],
            "news_published": 0,
            "news_prefilter_skipped": 0,
            "news_dedup_skipped": 0,
            "active_collector": "RealTimeNewsCollector",
            "collector_version": "phase4e",
            "errors": [],
        }

        logger.info("RealTimeNewsCollector 初始化完成 (Phase 4E)")
        logger.info("  采集间隔: %ss", self.collection_interval)
        logger.info("  默认模式: %s", self.default_mode.value)
        logger.info("  语义去重: %s", "enabled" if self._deduper else "disabled")
        logger.info("  Qwen warmup: %s", self._qwen_warmup)

    async def warmup_semantic_dedup(self) -> None:
        """启动时异步预热 Qwen，不阻塞采集循环。"""
        if not self._deduper or not self._qwen_warmup:
            return
        logger.info("Qwen dedup warmup started (background task)")
        await self._deduper.warmup()

    async def start_collection_loop(self) -> None:
        if self.is_running:
            logger.warning("采集循环已经在运行中")
            return

        self.is_running = True
        self.stats["started_at"] = datetime.now().isoformat()

        # Phase 4E: 启动前异步预热 Qwen
        if self._deduper and self._qwen_warmup:
            asyncio.create_task(self._deduper.warmup())

        self.collection_task = asyncio.create_task(self._collection_loop())
        logger.info("新闻采集循环已启动，间隔: %ss", self.collection_interval)

    async def stop_collection_loop(self) -> None:
        if not self.is_running:
            logger.warning("采集循环未在运行")
            return

        self.is_running = False

        if self.collection_task:
            self.collection_task.cancel()
            try:
                await self.collection_task
            except asyncio.CancelledError:
                logger.info("采集循环已取消")

        logger.info("新闻采集循环已停止")

    async def _collection_loop(self):
        # 采集周期硬超时: collection_interval + 额外缓冲，防止单次采集永久阻塞
        _cycle_timeout = max(self.collection_interval + 60, 180)
        while self.is_running:
            try:
                result = await asyncio.wait_for(
                    self.collect_and_publish(),
                    timeout=_cycle_timeout,
                )

                self.stats["total_collections"] += 1
                if result.get("success"):
                    self.stats["successful_collections"] += 1
                    self.stats["news_published"] += result.get("news_published", 0)
                else:
                    self.stats["failed_collections"] += 1

                self.stats["last_collection_time"] = datetime.now().isoformat()
                self.stats["last_collection_result"] = result

                logger.info(
                    "新闻采集完成: 成功=%s, 发布=%s条, "
                    "dedup_batch=%s, dedup_recent=%s, qwen_calls=%s",
                    result.get("success"),
                    result.get("news_published", 0),
                    result.get("semantic_dedup_batch_count", 0),
                    result.get("semantic_dedup_recent_count", 0),
                    result.get("qwen_dedup_call_count", 0),
                )

            except asyncio.CancelledError:
                break
            except asyncio.TimeoutError:
                logger.error("采集循环超时 (%.0fs)，本轮跳过，下轮重试", _cycle_timeout)
                self.stats["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": f"collection_cycle_timeout_{_cycle_timeout}s",
                })
            except Exception as e:
                logger.error("采集循环发生错误: %s", e)
                self.stats["errors"].append({
                    "time": datetime.now().isoformat(),
                    "error": str(e)
                })

            try:
                await asyncio.sleep(self.collection_interval)
            except asyncio.CancelledError:
                break

    async def collect_and_publish(self, mode: str = "auto") -> Dict:
        start_time = time.time()
        result: Dict[str, Any] = {
            "success": False,
            "mode": mode,
            "news_collected": 0,
            "news_published": 0,
            "news_prefilter_skipped": 0,
            "news_dedup_skipped": 0,
            "semantic_dedup_batch_count": 0,
            "semantic_dedup_recent_count": 0,
            "qwen_dedup_call_count": 0,
            "error": None,
            "duration": 0,
            "timestamp": datetime.now().isoformat()
        }

        try:
            actual_mode = self._determine_collection_mode(mode)
            result["mode"] = actual_mode.value
            self.stats["mode_history"].append({
                "time": datetime.now().isoformat(),
                "mode": actual_mode.value
            })

            # Phase 4E: 重置 deduper 每轮预算
            if self._deduper:
                self._deduper.new_round()

            backpressure = await self._raw_stream_backpressure()
            if backpressure.get("active"):
                result["success"] = True
                result["backpressure"] = backpressure
                result["duration"] = time.time() - start_time
                logger.warning(
                    "raw stream backpressure active, skip collection: lag=%s xlen=%s ratio=%.3f "
                    "pending=%s delivery_lag_s=%s",
                    backpressure.get("lag"),
                    backpressure.get("xlen"),
                    float(backpressure.get("lag_ratio") or 0),
                    backpressure.get("pending"),
                    backpressure.get("delivery_lag_s"),
                )
                return result

            # 1. 采集新闻 (crawler only, 不做过滤/去重)
            news_items = await self._collect_news(actual_mode)
            result["news_collected"] = len(news_items)

            if not news_items:
                logger.info("采集模式 %s: 未采集到新闻", actual_mode.value)
                result["success"] = True
                result["duration"] = time.time() - start_time
                return result

            # 2. 标准化 (Normalizer)
            news_items = self._normalize_news_batch(news_items)

            # 3. 低质量预筛选 (统一 NewsPreFilterAdapter)
            news_items, prefilter_skipped = self._prefilter_news(news_items)
            result["news_prefilter_skipped"] = prefilter_skipped
            self.stats["news_prefilter_skipped"] += prefilter_skipped

            if not news_items:
                logger.info("预筛选后无可发布新闻")
                result["success"] = True
                result["duration"] = time.time() - start_time
                return result

            # 4. 永久去重（SHA1 dedupe key） + news_id 短窗口去重
            news_items, perm_dup_skipped = self._dedupe_permanent(news_items)
            result["news_dedup_skipped_permanent"] = perm_dup_skipped
            news_items, dedup_skipped = self._dedup_news_items(news_items)
            result["news_dedup_skipped"] = dedup_skipped + perm_dup_skipped
            self.stats["news_dedup_skipped"] += result["news_dedup_skipped"]

            # 每 10 个周期清空 _filtered，允许 prefilter 重评
            self._filtered_cycles += 1
            if self._filtered_cycles >= 10:
                self._filtered_keys.clear()
                self._filtered_cycles = 0

            if not news_items:
                logger.info("去重后无可发布新闻")
                result["success"] = True
                result["duration"] = time.time() - start_time
                return result

            # 5. batch 内语义去重 (SemanticEventDeduper)
            if self._deduper:
                before = len(news_items)
                news_items = await self._deduper.dedup_batch(news_items)
                result["semantic_dedup_batch_count"] = before - len(news_items)

            if not news_items:
                logger.info("语义去重后无可发布新闻")
                result["success"] = True
                result["duration"] = time.time() - start_time
                return result

            # 6. 跨周期去重 (SemanticEventDeduper)
            if self._deduper:
                before = len(news_items)
                news_items = await self._deduper.dedup_against_recent(news_items)
                result["semantic_dedup_recent_count"] = before - len(news_items)

            if not news_items:
                logger.info("跨周期去重后无可发布新闻")
                result["success"] = True
                result["duration"] = time.time() - start_time
                return result

            # 7. 发布到 stream:news:raw
            published_count = await self._publish_news_to_stream(news_items)
            result["news_published"] = published_count
            result["success"] = published_count > 0

            # 8. 写入永久去重集 + recent cache（仅成功发布的）
            for item in news_items[:published_count]:
                key = _make_dedupe_key(item)
                self._seen_dedupe_keys.add(key)
                if self._deduper:
                    self._deduper.add_to_recent(item)

            # 9. 附加 deduper stats
            if self._deduper:
                ds = self._deduper.get_stats()
                result["qwen_dedup_call_count"] = ds.get("qwen_dedup_call_count", 0)
                result["qwen_dedup_ready"] = ds.get("qwen_dedup_ready", False)
                result["qwen_dedup_budget_exhausted"] = ds.get("qwen_dedup_budget_exhausted", 0)
                result["hard_protect_count"] = ds.get("hard_protect_count", 0)

            logger.info(
                "采集模式 %s: 采集%d条 → 发布%d条到stream:news:raw "
                "(预筛跳%d, dedup跳%d, batch_dedup=%d, recent_dedup=%d)",
                actual_mode.value,
                result["news_collected"],
                published_count,
                prefilter_skipped,
                dedup_skipped,
                result.get("semantic_dedup_batch_count", 0),
                result.get("semantic_dedup_recent_count", 0),
            )

        except Exception as e:
            logger.error("新闻采集发布失败: %s", e)
            result["error"] = str(e)
            result["success"] = False

        result["duration"] = time.time() - start_time
        return result

    async def _raw_stream_backpressure(self) -> Dict[str, Any]:
        """Return active=True when raw consumer lag risks trim loss."""
        if not self.enable_raw_backpressure:
            return {"active": False, "disabled": True}

        try:
            import redis.asyncio as aioredis

            redis_client = aioredis.from_url(self.redis_url, decode_responses=True)
            try:
                xlen = int(await redis_client.xlen(self.raw_stream_key))
                latest_items = await redis_client.xrevrange(self.raw_stream_key, count=1)
                groups = await redis_client.xinfo_groups(self.raw_stream_key)
            finally:
                await redis_client.aclose()

            group_info = None
            for group in groups:
                if str(group.get("name")) == self.raw_consumer_group:
                    group_info = group
                    break
            if not group_info:
                return {"active": False, "reason": "consumer_group_missing", "xlen": xlen}

            lag = int(group_info.get("lag") or 0)
            pending = int(group_info.get("pending") or 0)
            last_delivered = str(group_info.get("last-delivered-id") or "")
            lag_ratio = (lag / xlen) if xlen > 0 else 0.0
            delivery_lag_s = 0.0
            latest_id = str(latest_items[0][0]) if latest_items else ""
            if latest_id and last_delivered and "-" in latest_id and "-" in last_delivered:
                try:
                    latest_ts = int(latest_id.split("-")[0]) / 1000.0
                    delivered_ts = int(last_delivered.split("-")[0]) / 1000.0
                    delivery_lag_s = max(0.0, latest_ts - delivered_ts)
                except Exception:
                    delivery_lag_s = 0.0

            active = (
                lag_ratio > self.raw_backpressure_lag_ratio
                or delivery_lag_s > self.raw_backpressure_delivery_lag_s
                or pending > self.raw_backpressure_pending
            )
            return {
                "active": active,
                "stream": self.raw_stream_key,
                "group": self.raw_consumer_group,
                "xlen": xlen,
                "latest_id": latest_id,
                "last_delivered_id": last_delivered,
                "lag": lag,
                "lag_ratio": round(lag_ratio, 4),
                "pending": pending,
                "delivery_lag_s": round(delivery_lag_s, 1),
                "threshold_lag_ratio": self.raw_backpressure_lag_ratio,
                "threshold_delivery_lag_s": self.raw_backpressure_delivery_lag_s,
                "threshold_pending": self.raw_backpressure_pending,
            }
        except Exception as exc:
            logger.warning("raw stream backpressure check skipped: %s", exc)
            return {"active": False, "error": str(exc)}

    def _normalize_news_batch(self, news_items: List[Dict]) -> List[Dict]:
        """使用 NewsPayloadNormalizer 标准化整批新闻。"""
        if normalize_news_payload is None:
            return news_items

        normalized = []
        run_id = os.getenv("RUN_ID", "")
        for item in news_items:
            try:
                payload = normalize_news_payload(
                    item,
                    run_id=run_id,
                    default_source="db_collector",
                    collector_name="RealTimeNewsCollector",
                    collector_version="phase4e",
                )
                normalized.append(payload)
            except Exception:
                logger.exception("标准化新闻失败，保留原始条目")
                normalized.append(item)
        return normalized

    def _prefilter_news(self, news_items: List[Dict]) -> (List[Dict], int):
        """统一 prefilter — NewsPreFilterAdapter。"""
        if not self.enable_collector_prefilter or not self._prefilter:
            return news_items, 0

        kept: List[Dict] = []
        skipped = 0

        for news in news_items:
            try:
                triage = self._prefilter.evaluate(news)
                decision = str(triage.decision).upper()
                news_id = str(news.get("news_id", "unknown"))
                dedupe_key = _make_dedupe_key(news)

                # 已在 _filtered_keys 中 → 跳过（除非 prefilter 变更允许重评）
                if dedupe_key in self._filtered_keys:
                    skipped += 1
                    continue

                if decision == "SKIP" and self.collector_drop_on_skip:
                    skipped += 1
                    self._filtered_keys.add(dedupe_key)
                    self._write_prefilter_skip_log(news, triage)
                    logger.debug("prefilter SKIP: %s reason=%s", news_id, triage.reason)
                    continue

                # 记录 prefilter 元数据
                news.update(self._prefilter.to_payload_fields(triage))
            except Exception as e:
                logger.warning("prefilter 异常，保留该新闻: %s", e)

            kept.append(news)

        return kept, skipped

    def _dedupe_permanent(self, news_items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
        """SHA1 永久去重：同进程生命周期内不重发同一 dedupe_key。"""
        if not news_items:
            return news_items, 0

        filtered: List[Dict[str, Any]] = []
        skipped = 0
        for item in news_items:
            key = _make_dedupe_key(item)
            if key in self._seen_dedupe_keys:
                skipped += 1
                continue
            filtered.append(item)
        return filtered, skipped

    def _dedup_news_items(self, news_items: List[Dict[str, Any]]) -> tuple[List[Dict[str, Any]], int]:
        """基于 news_id 短窗口去重（快速第一层）。"""
        if not news_items:
            return news_items, 0

        now_ts = time.time()
        expired = [
            nid for nid, ts in self._recent_news_ids.items()
            if now_ts - ts > self.dedup_window_seconds
        ]
        for nid in expired:
            self._recent_news_ids.pop(nid, None)

        filtered: List[Dict[str, Any]] = []
        skipped = 0
        for item in news_items:
            news_id = str(item.get("news_id") or "").strip()
            if not news_id:
                filtered.append(item)
                continue

            if news_id in self._recent_news_ids:
                skipped += 1
                logger.debug("news_id 去重: %s", news_id)
                continue

            self._recent_news_ids[news_id] = now_ts
            filtered.append(item)

        return filtered, skipped

    def _write_prefilter_skip_log(self, payload: Dict, triage_result) -> None:
        """记录 prefilter skip 事件到 JSONL（调试用）。"""
        if not self._prefilter_skip_log:
            return
        try:
            import json as _json
            from datetime import datetime as _dt
            entry = {
                "time": _dt.now().isoformat(),
                "title": str(payload.get("title", ""))[:200],
                "reason": str(triage_result.reason)[:200],
                "mode": str(triage_result.mode),
                "source": str(payload.get("source", "")),
            }
            with open(self._prefilter_skip_log, "a", encoding="utf-8") as f:
                f.write(_json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def _determine_collection_mode(self, requested_mode: str) -> CollectionMode:
        if requested_mode == "auto":
            if self._is_real_mode_available():
                return CollectionMode.REAL
            else:
                logger.warning("auto模式下CLS和akshare采集均不可用，本轮可能无法产出新闻")
                return CollectionMode.REAL
        else:
            try:
                return CollectionMode(requested_mode)
            except ValueError:
                logger.warning("无效的采集模式: %s，使用默认模式", requested_mode)
                return self.default_mode

    def _is_real_mode_available(self) -> bool:
        """检查真实采集路径是否可用（与 _collect_real_news 实际路径一致）。"""
        # CLS: 通过 news_crawler_service 单例（直接 import，不依赖 crawler_client）
        try:
            from news_crawler_service.services.news_crawler_service import get_news_crawler_service
            if get_news_crawler_service().collector is not None:
                return True
        except Exception:
            pass
        # Fallback: akshare 多源也足够
        try:
            import akshare  # noqa: F401
            return True
        except ImportError:
            pass
        return False

    async def _collect_news(self, mode: CollectionMode) -> List[Dict]:
        if mode == CollectionMode.REAL:
            return await self._collect_real_news()
        else:
            raise ValueError(f"不支持的采集模式: {mode}")

    async def _collect_real_news(self) -> List[Dict]:
        """多源并行采集：CLS + 东方财富快讯 (CDP 并行) + akshare。"""
        results: List[Dict] = []

        # ── CDP 双源并行采集 (共用 Chrome :9224，各自独立标签页) ──
        async def _fetch_cls_cdp() -> List[Dict]:
            items: List[Dict] = []
            try:
                from news_crawler_service.services.news_crawler_service import get_news_crawler_service
                crawler_service = get_news_crawler_service()
                raw = await asyncio.wait_for(
                    crawler_service.crawl_news_auto(
                        count=self.cls_max_items, prefer_real=True,
                        max_age_minutes=self.cls_max_age_minutes,
                    ),
                    timeout=45,
                )
                if raw.get("status") == "success":
                    for item in raw.get("response", {}).get("news_list", []):
                        item["source_channel"] = "cls"
                        items.append(item)
                    logger.debug("CLS fetch: %d items", len(items))
                elif raw.get("error"):
                    logger.warning("CLS fetch failed: %s", raw.get("error", "unknown"))
            except asyncio.TimeoutError:
                logger.warning("CLS fetch timeout after 45s")
            except ImportError:
                logger.debug("news_crawler_service not available, skipping CLS")
            except Exception as exc:
                logger.warning("CLS fetch exception: %s", exc)
            return items

        async def _fetch_eastmoney_cdp() -> List[Dict]:
            items: List[Dict] = []
            try:
                from news_crawler_service.collectors.cls_cdp import (
                    ClsCdpCollector, KUXUN_URL, KUXUN_EXTRACTION_JS,
                )
                em_collector = ClsCdpCollector(
                    cdp_port=9224,
                    url=KUXUN_URL,
                    extraction_js=KUXUN_EXTRACTION_JS,
                    source_name="eastmoney_kuaixun",
                    cache_max_age=60,
                    content_min_length=200,
                )
                em_df = await asyncio.wait_for(
                    asyncio.to_thread(em_collector.fetch_df, limit=30),
                    timeout=35,
                )
                if em_df is not None and not em_df.empty:
                    for _, row in em_df.iterrows():
                        items.append({
                            "title": str(row.get("标题", "")),
                            "content": str(row.get("内容", "")),
                            "source": "eastmoney_kuaixun",
                            "source_channel": "eastmoney_kuaixun",
                            "publish_date": str(row.get("发布日期", "")),
                            "publish_time": str(row.get("发布时间", "")),
                            "url": str(row.get("URL", "")),
                            "keywords": [],
                        })
                    logger.debug("Eastmoney kuaixun fetch: %d items", len(em_df))
            except asyncio.TimeoutError:
                logger.warning("Eastmoney kuaixun CDP fetch timeout after 35s")
            except ImportError:
                logger.debug("Eastmoney kuaixun module not available")
            except Exception as exc:
                logger.warning("Eastmoney kuaixun fetch exception: %s", exc)
            return items

        # CLS 和东方财富快讯 CDP 并行
        cdp_tasks = [
            asyncio.create_task(_fetch_cls_cdp()),
            asyncio.create_task(_fetch_eastmoney_cdp()),
        ]
        cdp_results = await asyncio.gather(*cdp_tasks, return_exceptions=True)
        for r in cdp_results:
            if isinstance(r, list):
                results.extend(r)

        # ── Sources 3-6: akshare native sources ──
        try:
            akshare_rows = await self._fetch_akshare_multi_source()
            results.extend(akshare_rows)
        except Exception as exc:
            logger.warning("akshare multi-source fetch failed: %s", exc)

        # Fallback: direct akshare if all sources failed
        if not results:
            logger.warning("All sources empty, trying fallback akshare direct")
            try:
                import akshare as ak
                df = await asyncio.wait_for(asyncio.to_thread(ak.stock_news_em), timeout=45)
                if df is not None and not df.empty:
                    for _, row in df.head(20).iterrows():
                        r = row.to_dict()
                        r["source_channel"] = "akshare_em"
                        results.append(r)
                    logger.info("Fallback akshare_em: %d items", len(results))
            except asyncio.TimeoutError:
                logger.warning("Fallback akshare_em fetch timeout")
            except Exception as exc:
                logger.warning("Fallback akshare also failed: %s", exc)

        if not results:
            logger.warning("All collection sources returned empty")
            return []

        # Standardize
        standardized = []
        now = datetime.now()
        for n in results:
            standardized.append({
                "news_id": str(n.get("news_id", "")),
                "title": str(n.get("title", "")),
                "content": str(n.get("content") or n.get("内容") or n.get("title", "")),
                "source": str(n.get("source", "unknown")),
                "source_channel": str(n.get("source_channel") or "unknown"),
                "publish_date": str(n.get("publish_date", now.strftime("%Y-%m-%d"))),
                "publish_time": str(n.get("publish_time", now.strftime("%H:%M:%S"))),
                "url": str(n.get("url", "")),
                "keywords": n.get("keywords", []),
                "collected_at": now.isoformat(),
            })

        logger.info("多源采集完成: %d 条 (CLS+akshare)", len(standardized))
        return standardized

    async def _fetch_akshare_multi_source(self) -> List[Dict]:
        """Parallel fetch from 东方财富/新浪/同花顺/富途/CCTV via akshare。"""
        import akshare as ak

        sources: list[tuple[str, Any, str]] = [
            ("sina",  ak.stock_info_global_sina, "sina"),
            ("ths",   ak.stock_info_global_ths,  "ths"),
            ("futu",  ak.stock_info_global_futu, "futu"),
            ("cctv",  ak.news_cctv,              "cctv"),
        ]
        _LIMITS = {"sina": 20, "ths": 20, "futu": 50, "cctv": 12}

        async def _fetch_one(label: str, func, channel: str) -> List[Dict]:
            try:
                df = await asyncio.wait_for(asyncio.to_thread(func), timeout=45)
                if df is None or getattr(df, "empty", True):
                    return []
                limit = _LIMITS.get(channel, 50)
                records = df.head(limit).to_dict("records")
                for r in records:
                    r["source_channel"] = f"akshare_{channel}"
                    if channel == "sina":
                        content_text = str(r.get("内容", ""))
                        r["title"] = content_text[:40]
                        r["content"] = content_text
                        r["publish_time"] = str(r.get("时间", ""))
                        r["publish_date"] = datetime.now().strftime("%Y-%m-%d")
                return [dict(row) for row in records]
            except asyncio.TimeoutError:
                logger.warning("akshare %s fetch timeout", label)
                return []
            except Exception as exc:
                logger.warning("akshare %s fetch failed: %s", label, exc)
                return []

        tasks = [asyncio.create_task(_fetch_one(label, func, ch)) for label, func, ch in sources]
        gathered = await asyncio.gather(*tasks, return_exceptions=True)

        all_rows: List[Dict] = []
        for i, rows in enumerate(gathered):
            if isinstance(rows, Exception):
                logger.warning("akshare source %s crashed: %s", sources[i][0], rows)
            else:
                if rows:
                    logger.info("akshare %s: %d items", sources[i][0], len(rows))
                all_rows.extend(rows)

        return all_rows

    async def _publish_news_to_stream(self, news_items: List[Dict]) -> int:
        if not news_items:
            return 0

        published_count = 0
        try:
            if self.news_producer:
                message_ids = await self.news_producer.publish_batch(news_items, "raw")
                published_count = sum(1 for mid in message_ids if mid is not None)
            else:
                for news in news_items:
                    try:
                        message_data = {
                            "news_id": news.get("news_id"),
                            "title": news.get("title"),
                            "content": news.get("content"),
                            "source": news.get("source"),
                            "source_channel": news.get("source_channel", ""),
                            "publish_date": news.get("publish_date"),
                            "publish_time": news.get("publish_time"),
                            "collected_at": news.get("collected_at"),
                            "run_id": news.get("run_id", ""),
                            "type": "raw_news",
                            "collector_name": news.get("collector_name", "RealTimeNewsCollector"),
                            "collector_version": news.get("collector_version", "phase4e"),
                        }
                        message_id = await self.stream_manager.publish("stream:news:raw", message_data)
                        if message_id:
                            published_count += 1
                            logger.debug("新闻发布成功: %s -> %s", news.get("news_id"), message_id)
                    except Exception as e:
                        logger.error("发布单条新闻失败 %s: %s", news.get("news_id"), e)

        except Exception as e:
            logger.error("批量发布新闻失败: %s", e)

        return published_count

    async def get_collection_stats(self) -> Dict:
        stats = dict(self.stats)

        total = stats["total_collections"]
        successful = stats["successful_collections"]
        stats["success_rate"] = (successful / total * 100) if total > 0 else 0

        stats["is_running"] = self.is_running
        stats["collection_interval"] = self.collection_interval

        if stats["errors"]:
            stats["recent_errors"] = stats["errors"][-10:]
        else:
            stats["recent_errors"] = []

        # Phase 4E: deduper stats
        if self._deduper:
            ds = self._deduper.get_stats()
            stats.update({
                "semantic_dedup_batch_count": ds.get("semantic_dedup_batch_count", 0),
                "semantic_dedup_recent_count": ds.get("semantic_dedup_recent_count", 0),
                "qwen_dedup_call_count": ds.get("qwen_dedup_call_count", 0),
                "qwen_dedup_ready": ds.get("qwen_dedup_ready", False),
                "qwen_dedup_unavailable_count": ds.get("qwen_dedup_unavailable_count", 0),
                "qwen_dedup_budget_exhausted": ds.get("qwen_dedup_budget_exhausted", 0),
                "hard_protect_count": ds.get("hard_protect_count", 0),
                "recent_cache_size": ds.get("recent_cache_size", 0),
            })

        return stats

    def get_config(self) -> Dict:
        return {
            "collection_interval": self.collection_interval,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "default_mode": self.default_mode.value,
            "is_real_mode_available": self._is_real_mode_available(),
            "enable_semantic_dedup": self._deduper is not None,
            "active_collector": "RealTimeNewsCollector",
            "collector_version": "phase4e",
        }


def _make_dedupe_key(payload: Dict[str, Any]) -> str:
    """SHA1 dedupe key，与旧 AkShare collector 兼容。"""
    value = str(payload.get("external_id") or payload.get("news_id") or "")
    if not value:
        value = f"{payload.get('title', '')}|{payload.get('content', '')}"
    return hashlib.sha1(str(value).encode()).hexdigest()
