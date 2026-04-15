#!/usr/bin/env python3
"""
基于真实新闻的全链路测试脚本
使用 akshare 获取实时财经新闻，通过 ThemeMatchEngine 进行题材匹配
基于 run_full_chain_100_to_decision_with_progress.py 优化
"""

import asyncio
import json
import os
import re
import sys
import time
import uuid
import argparse
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta
import logging

import akshare as ak
import asyncpg
import redis.asyncio as redis

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway
from database_service.managers.redis_stream_bus import UnifiedRedisStreamBus
from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.news_stream_handler import NewsStreamHandler
from database_service.streams.handlers.news_stream_processor import NewsStreamProcessor
from database_service.streams.handlers.theme_processor import ThemeProcessor
from database_service.streams.utils.consumer_group_manager import ConsumerGroupManager, cleanup_test_consumer_groups

# NewsCrawlerService 导入
try:
    from news_crawler_service.services.news_crawler_service import get_news_crawler_service
    HAS_NEWS_CRAWLER_SERVICE = True
except ImportError as e:
    logger = logging.getLogger("real_news_test")
    logger.warning(f"无法导入 NewsCrawlerService: {e}")
    HAS_NEWS_CRAWLER_SERVICE = False

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(PROJECT_ROOT / "tmp/real_news_test.log")
    ]
)
logger = logging.getLogger("real_news_test")

# 输出文件路径
OUT_PATH = PROJECT_ROOT / "tmp/p2_phase0_real_news_to_decision.report.json"
TEST_NEWS_PREFIX = "p2_real_news%"

# 主题键映射（用于后续分析参考）
THEME_KEY_MAP = {
    "AI/AR眼镜": "9030409",
    "SpaceX": "9064166",
    "可控核聚变": "9017950",
    "对日制裁": "9059919",
    "稀土永磁": "9010367",
    "海洋经济": "9043698",
    "深海经济": "9043698",
    "光刻胶": "9018411",
    "卫星互联": "9019807",
    "卫星互联网": "9019807",
    "液冷数据中心": "9024880",
    "AI智能体Manus": "9043089",
}


def _pg_kwargs() -> Dict[str, Any]:
    """PostgreSQL连接参数"""
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


async def fetch_real_news(source: str = "stock_news_em", limit: int = 10) -> List[Dict[str, Any]]:
    """
    获取真实新闻数据 - 优先使用 NewsCrawlerService，失败时回退到直接调用 akshare

    Args:
        source: 新闻源，可选值:
            - "stock_news_em": 东方财富股票新闻 (通过 NewsCrawlerService 或直接 akshare)
            - "news_cctv": 央视新闻 (直接 akshare)
            - "news": 百度新闻 (直接 akshare)
            - "futures_news_shmet": 上海有色网期货新闻 (直接 akshare)
        limit: 获取的新闻数量

    Returns:
        新闻数据列表，每条新闻包含: title, content, publish_date, source, raw_text
    """
    logger = logging.getLogger("real_news_test")
    news_items = []

    # 1. 优先尝试使用 NewsCrawlerService（如果可用且source为stock_news_em）
    if HAS_NEWS_CRAWLER_SERVICE and source == "stock_news_em":
        try:
            logger.info(f"使用 NewsCrawlerService 获取新闻 (limit={limit})")
            service = get_news_crawler_service()

            # 检查服务状态
            status = await service.get_service_status()
            if not status.get("initialized", False):
                logger.warning("NewsCrawlerService 未初始化，回退到直接调用")
            else:
                # 尝试抓取真实新闻
                result = await service.crawl_real_news(limit=limit)

                if result.get("status") == "success":
                    response = result.get("response", {})
                    news_list = response.get("news_list", [])
                    logger.info(f"NewsCrawlerService 成功获取 {len(news_list)} 条新闻")

                    for news_data in news_list:
                        # 转换 NewsCrawlerService 数据格式到统一格式
                        title = news_data.get("title", "")
                        content = news_data.get("content", "")
                        publish_date = news_data.get("publish_date", "")
                        publish_time = news_data.get("publish_time", "")
                        news_source = news_data.get("source", "akshare_cls")
                        market = news_data.get("market", "A股")

                        # 构建 raw_text（标题+内容）
                        raw_text = f"{title} {content}" if title and content else title or content or ""

                        if raw_text:  # 至少要有内容
                            news_items.append({
                                "title": title,
                                "content": content,
                                "publish_date": publish_date,
                                "publish_time": publish_time,
                                "source": news_source,
                                "market": market,
                                "raw_text": raw_text
                            })

                    # 如果成功获取到新闻，直接返回
                    if news_items:
                        logger.info(f"成功通过 NewsCrawlerService 获取 {len(news_items)} 条新闻")
                        return news_items[:limit]
                    else:
                        logger.warning("NewsCrawlerService 返回空新闻列表，回退到直接调用")

                else:
                    error_msg = result.get("error", "未知错误")
                    logger.warning(f"NewsCrawlerService 抓取失败: {error_msg}")

        except Exception as e:
            logger.warning(f"NewsCrawlerService 调用异常: {e}")
            # 继续尝试直接调用 akshare

    # 2. 回退到直接调用 akshare（原有逻辑）
    logger.info(f"使用直接 akshare 调用获取新闻: {source}")
    try:
        if source == "stock_news_em":
            # 东方财富股票新闻
            df = ak.stock_news_em()
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    title = str(row.get("新闻标题", "")).strip()
                    content = str(row.get("新闻内容", "")).strip()
                    publish_time = str(row.get("发布时间", "")).strip()
                    news_url = str(row.get("新闻链接", "")).strip()

                    if title and content:
                        news_items.append({
                            "title": title,
                            "content": f"{title}\n{content}",
                            "publish_date": publish_time.split()[0] if " " in publish_time else publish_time,
                            "publish_time": publish_time,
                            "source": "东方财富",
                            "url": news_url,
                            "raw_text": f"{title} {content}"
                        })

        elif source == "news_cctv":
            # 央视新闻
            df = ak.news_cctv()
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    title = str(row.get("title", "")).strip()
                    content = str(row.get("content", "")).strip()
                    publish_time = str(row.get("date", "")).strip()

                    if title and content:
                        news_items.append({
                            "title": title,
                            "content": content,
                            "publish_date": publish_time,
                            "source": "央视新闻",
                            "raw_text": f"{title} {content}"
                        })

        elif source == "futures_news_shmet":
            # 上海有色网期货新闻
            df = ak.futures_news_shmet()
            if df is not None and not df.empty:
                for _, row in df.head(limit).iterrows():
                    title = str(row.get("标题", "")).strip()
                    content = str(row.get("内容", "")).strip()
                    publish_time = str(row.get("日期", "")).strip()

                    if title:
                        news_items.append({
                            "title": title,
                            "content": content if content else title,
                            "publish_date": publish_time,
                            "source": "上海有色网",
                            "raw_text": f"{title} {content}"
                        })

        else:
            # 默认使用百度新闻
            try:
                df = ak.news()
                if df is not None and not df.empty:
                    for _, row in df.head(limit).iterrows():
                        title = str(row.get("title", "")).strip()
                        content = str(row.get("content", "")).strip()
                        publish_time = str(row.get("date", "")).strip()

                        if title:
                            news_items.append({
                                "title": title,
                                "content": content if content else title,
                                "publish_date": publish_time,
                                "source": "百度新闻",
                                "raw_text": f"{title} {content}"
                            })
            except:
                # 如果百度新闻失败，回退到股票新闻
                logger.warning("百度新闻获取失败，回退到股票新闻")
                return await fetch_real_news("stock_news_em", limit)

    except Exception as e:
        logger.error(f"直接 akshare 调用失败 ({source}): {e}")
        # 返回空列表，后续会使用模拟数据作为fallback

    # 3. 如果获取不到新闻，使用模拟数据作为fallback
    if not news_items:
        logger.warning(f"从 {source} 获取不到新闻数据，使用模拟数据")
        mock_news = [
            ("AI眼镜厂商发布新品，预计将推动AR产业链发展", "AI/AR眼镜"),
            ("液冷数据中心需求激增，相关公司订单饱满", "液冷数据中心"),
            ("SpaceX成功发射新卫星，卫星互联网建设加速", "卫星互联网"),
            ("深海勘探技术突破，海洋经济前景广阔", "深海经济"),
            ("光刻胶国产替代加速，相关公司业绩增长", "光刻胶"),
        ]

        for i, (content, theme) in enumerate(mock_news[:limit]):
            news_items.append({
                "title": content[:50] + "...",
                "content": content,
                "publish_date": datetime.now().strftime("%Y-%m-%d"),
                "source": "模拟数据",
                "raw_text": content,
                "theme_name": theme,
                "expected_subject_key": THEME_KEY_MAP.get(theme, "")
            })

    logger.info(f"成功获取 {len(news_items)} 条新闻（来源: {source}）")
    return news_items[:limit]


def _build_v2_payload(raw_text: str, news_id: str, sequence: int, batch_id: str, title: str = "") -> Dict[str, Any]:
    """构建新闻payload"""
    return {
        "_t": "news",
        "_v": 2,
        "id": news_id,
        "t": title[:200] if title else "",
        "c": raw_text,
        "s": "cls",
        "d": datetime.now().strftime("%Y-%m-%d"),
        "tm": "00:00:00",
        "_b": batch_id,
        "_s": sequence,
    }


async def _wait_for_news_raw(gateway: Any, external_news_id: str, timeout_s: float = 30.0) -> Optional[Dict[str, Any]]:
    """等待新闻数据存储"""
    started = time.time()
    while time.time() - started < timeout_s:
        row = await gateway.get_news(external_news_id)
        if row:
            return row
        await asyncio.sleep(0.2)
    return None


async def _wait_for_decisions(
    redis_client: redis.Redis,
    stream_name: str,
    expected_count: int,
    seen_ids: set[str],
    timeout_s: float = 180.0,
) -> List[Dict[str, Any]]:
    """等待决策结果"""
    started = time.time()
    decisions: List[Dict[str, Any]] = []
    while time.time() - started < timeout_s:
        messages = await redis_client.xread({stream_name: "0-0"}, count=500, block=1000)
        for _stream, message_list in messages:
            for message_id, payload in message_list:
                if message_id in seen_ids:
                    continue
                seen_ids.add(message_id)
                raw = payload.get("decision")
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                try:
                    decisions.append(json.loads(raw))
                except json.JSONDecodeError as e:
                    logger.error(f"决策 JSON 解析失败: {e}")
        if len(decisions) >= expected_count:
            break
        await asyncio.sleep(0.2)
    return decisions


def _print_progress(stage: str, current: int, total: int, extra: str = "") -> None:
    """打印进度信息"""
    suffix = f" {extra}" if extra else ""
    print(f"[{current}/{total}] {stage}{suffix}", flush=True)


async def _cleanup_previous_test_data(conn: asyncpg.Connection) -> None:
    """清理之前的测试数据"""
    await conn.execute("""
        DELETE FROM event_theme_map
        WHERE event_id IN (
            SELECT e.id
            FROM news_event e
            JOIN news_raw n ON n.id = e.news_id
            WHERE n.news_id LIKE $1
        )
    """, TEST_NEWS_PREFIX)

    await conn.execute("""
        DELETE FROM news_event
        WHERE news_id IN (
            SELECT id FROM news_raw WHERE news_id LIKE $1
        )
    """, TEST_NEWS_PREFIX)

    await conn.execute("DELETE FROM news_raw WHERE news_id LIKE $1", TEST_NEWS_PREFIX)

    logger.info("测试数据清理完成")


def _build_report(details: List[Dict[str, Any]]) -> Dict[str, Any]:
    """构建测试报告"""
    processed = len(details)
    successful = sum(1 for row in details if row.get("status") == "ok")
    failed = sum(1 for row in details if row.get("status") == "failed")

    # 统计匹配结果分布
    theme_counter = Counter()
    for row in details:
        if row.get("matched_theme_name"):
            theme_counter[row["matched_theme_name"]] += 1

    # 统计决策类型分布
    decision_counter = Counter()
    for row in details:
        if row.get("decision_type"):
            decision_counter[row["decision_type"]] += 1

    # 统计置信度分布
    confidence_stats = {
        "avg": 0.0,
        "min": 1.0,
        "max": 0.0,
        "distribution": defaultdict(int)
    }
    confidences = [row.get("confidence", 0) for row in details if row.get("confidence") is not None]
    if confidences:
        confidence_stats["avg"] = sum(confidences) / len(confidences)
        confidence_stats["min"] = min(confidences)
        confidence_stats["max"] = max(confidences)
        # 置信度分布：0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0
        for conf in confidences:
            bucket = int(conf * 5)
            bucket_key = f"{bucket*0.2:.1f}-{(bucket+1)*0.2:.1f}"
            confidence_stats["distribution"][bucket_key] += 1

    return {
        "events": len(details),
        "processed": processed,
        "successful": successful,
        "failed": failed,
        "success_rate": round(successful / processed, 4) if processed else 0.0,
        "avg_confidence": round(confidence_stats["avg"], 4),
        "min_confidence": round(confidence_stats["min"], 4),
        "max_confidence": round(confidence_stats["max"], 4),
        "theme_distribution": dict(theme_counter.most_common(20)),
        "decision_distribution": dict(decision_counter),
        "confidence_distribution": dict(confidence_stats["distribution"]),
        "details": details,
        "timestamp": datetime.now().isoformat(),
    }


class _RedisStructuredEventBus:
    """Redis 结构化事件总线 (适配器)"""
    def __init__(self, redis_client: redis.Redis, structured_stream: str):
        self.redis_client = redis_client
        self.structured_stream = structured_stream

    async def publish_to_stream(self, stream_key: str, data: Dict[str, Any]):
        target = self.structured_stream if stream_key == "stream:events:structured" else stream_key
        payload = {"payload": json.dumps(data, ensure_ascii=False)}
        return await self.redis_client.xadd(target, payload, maxlen=10000)


async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="基于真实新闻的全链路测试")
    parser.add_argument("--sample-size", type=int, default=10, help="测试样本数量")
    parser.add_argument("--news-source", type=str, default="stock_news_em",
                       choices=["stock_news_em", "news_cctv", "news", "futures_news_shmet"],
                       help="新闻数据源")
    parser.add_argument("--no-cleanup", action="store_true", help="不清理之前的测试数据")
    parser.add_argument("--output", type=str, default=None, help="输出报告文件路径")

    args = parser.parse_args()

    if not os.getenv("DEEPSEEK_API_KEY"):
        raise RuntimeError("DEEPSEEK_API_KEY 未设置")

    # 设置输出路径
    output_path = Path(args.output) if args.output else OUT_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 生成运行ID
    run_id = uuid.uuid4().hex[:8]
    batch_id = f"p2_real_news_{run_id}"

    # Stream名称
    raw_stream = "stream:news:raw"
    structured_stream = "stream:events:structured"
    decision_stream = "stream:events:decision"
    dead_letter_stream = "stream:dead:letter"
    # 使用固定消费者组名，避免Redis中消费者组积累
    # 原动态生成: consumer_group = f"theme_processors_real_{run_id}"
    consumer_group = "theme_processors_v1"  # 与ThemeProcessor默认组名保持一致
    consumer_name = f"tp_fixed_{run_id}"  # 消费者名称仍可动态生成以支持并发

    # 初始化数据库配置
    cfg = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
    )
    cfg.redis.enabled = True
    init_config(cfg)
    DatabaseGateway._instance = None

    # 获取gateway
    stream_gateway = await get_gateway(enable_retry=True, retry_config={"max_retries": 2})
    base_gateway = stream_gateway.base_gateway

    # 初始化Redis
    redis_client = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        decode_responses=True,
    )
    await redis_client.ping()
    stream_bus = UnifiedRedisStreamBus(redis_client, cfg)

    # 清理旧的测试消费者组（解决消费者组积累问题）
    logger.info("🧹 清理旧的测试消费者组...")
    try:
        cgm = ConsumerGroupManager(redis_client)
        cleanup_result = await cgm.cleanup_old_groups(
            pattern="theme_processors_real_*",
            max_age_hours=24
        )
        logger.info(f"清理结果: 找到 {cleanup_result.get('total_groups_found', 0)} 个组, "
                   f"清理 {cleanup_result.get('groups_cleaned', 0)} 个")
    except Exception as e:
        logger.warning(f"清理测试消费者组失败（可忽略）: {e}")

    # 准备Streams
    await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")
    for stream_name in (raw_stream, structured_stream, decision_stream, dead_letter_stream):
        await redis_client.delete(stream_name)
    await stream_bus.ensure_consumer_group("news_raw", "news_storage_handlers")

    # 获取真实新闻数据
    logger.info(f"从 {args.news_source} 获取 {args.sample_size} 条新闻...")
    news_items = await fetch_real_news(args.news_source, args.sample_size)

    if not news_items:
        raise RuntimeError("无法获取新闻数据，测试终止")

    # 初始化处理组件
    news_handler = NewsStreamHandler(
        stream_bus=stream_bus,
        database_gateway=base_gateway,
        config={
            "consumer_group": "news_storage_handlers",
            "stream_name": "news_raw",
            "batch_size": 5,
            "block_time": 500,
        },
    )

    theme_processor = ThemeProcessor(
        redis_host=os.getenv("REDIS_HOST", "localhost"),
        redis_port=int(os.getenv("REDIS_PORT", "6379")),
        enable_classification_first=False,  # 使用 ThemeMatchEngine
        consumer_name=consumer_name,
        config={
            "stream_structured": structured_stream,
            "stream_decision": decision_stream,
            "stream_dead_letter": dead_letter_stream,
            "consumer_group": consumer_group,
            "structured_batch_size": 10,
            "structured_block_time": 500,
        },
    )

    news_processor = NewsStreamProcessor(
        event_bus=_RedisStructuredEventBus(redis_client, structured_stream),
        config={"database_gateway": base_gateway},
    )

    # 状态跟踪
    created_news_raw_ids: List[int] = []
    created_news_event_ids: List[int] = []
    seen_decision_ids: set[str] = set()
    details: List[Dict[str, Any]] = []
    conn = await asyncpg.connect(**_pg_kwargs())

    try:
        logger.info(f"开始真实新闻全链路测试，样本数={len(news_items)}")

        # 清理之前的测试数据
        if not args.no_cleanup:
            await _cleanup_previous_test_data(conn)

        # 启动处理服务
        await news_handler.start_storage_service()

        logger.info("正在初始化 ThemeProcessor...")
        ok = await theme_processor.initialize()
        if not ok:
            raise RuntimeError("theme_processor 初始化失败")

        logger.info("正在启动 ThemeProcessor...")
        await theme_processor.start()
        logger.info("ThemeProcessor 启动完成")

        # 处理每条新闻
        for idx, news_item in enumerate(news_items, start=1):
            external_news_id = f"{batch_id}_{idx:03d}_{uuid.uuid4().hex[:6]}"

            # 构建payload
            payload = _build_v2_payload(
                raw_text=news_item["raw_text"],
                news_id=external_news_id,
                sequence=idx,
                batch_id=batch_id,
                title=news_item.get("title", "")
            )

            # 发送到raw stream
            await stream_bus.publish_to_stream("news_raw", {"payload": payload})
            _print_progress("news_raw injected", idx, len(news_items), external_news_id)

            # 等待新闻存储
            stored_news = await _wait_for_news_raw(base_gateway, external_news_id, timeout_s=60.0)
            if not stored_news:
                logger.error(f"news_raw 未落库: {external_news_id}")
                details.append({
                    "index": idx,
                    "status": "failed",
                    "stage": "news_storage",
                    "news_id": external_news_id,
                    "news_title": news_item.get("title", "")[:100],
                    "news_source": news_item.get("source", ""),
                    "error": "news_raw_not_stored",
                })
                continue

            created_news_raw_ids.append(int(stored_news["id"]))
            _print_progress("news_raw persisted", idx, len(news_items), f"id={stored_news['id']}")

            # 构建结构化消息
            stored_message = {
                "payload": {
                    "news_data": {
                        "id": int(stored_news["id"]),
                        "news_row_id": int(stored_news["id"]),
                        "news_id": external_news_id,
                        "title": stored_news.get("title") or news_item.get("title", ""),
                        "content": stored_news.get("content") or news_item["raw_text"],
                        "source": stored_news.get("source") or news_item.get("source", "akshare"),
                        "publish_date": str(stored_news.get("publish_date") or news_item.get("publish_date", datetime.now().strftime("%Y-%m-%d"))),
                    }
                }
            }

            # 处理结构化
            processor_result = await news_processor.process_stream_message(
                message_id=f"stored_{uuid.uuid4().hex[:8]}",
                message_data=stored_message,
            )

            if not processor_result.get("success"):
                details.append({
                    "index": idx,
                    "status": "failed",
                    "stage": "news_stream_processor",
                    "news_id": external_news_id,
                    "news_title": news_item.get("title", "")[:100],
                    "news_source": news_item.get("source", ""),
                    "error": processor_result.get("error") or "news_stream_processor_failed",
                })
                _print_progress("structuring failed", idx, len(news_items),
                              str(processor_result.get("error") or "unknown_error"))
                continue

            news_event_id = processor_result.get("news_event_id")
            if not news_event_id:
                details.append({
                    "index": idx,
                    "status": "failed",
                    "stage": "news_event_persistence",
                    "news_id": external_news_id,
                    "news_title": news_item.get("title", "")[:100],
                    "error": "news_event_not_created",
                })
                _print_progress("news_event missing", idx, len(news_items))
                continue

            created_news_event_ids.append(int(news_event_id))
            _print_progress("news_event persisted", idx, len(news_items), f"event_id={news_event_id}")

            if not processor_result.get("structured_stream_published"):
                details.append({
                    "index": idx,
                    "status": "failed",
                    "stage": "structured_stream",
                    "news_id": external_news_id,
                    "news_event_id": news_event_id,
                    "news_title": news_item.get("title", "")[:100],
                    "error": "structured_stream_not_published",
                })
                _print_progress("structured stream missing", idx, len(news_items), f"event_id={news_event_id}")
                continue

            _print_progress("structured event published", idx, len(news_items))

            # 等待决策
            new_decisions = await _wait_for_decisions(
                redis_client,
                decision_stream,
                expected_count=1,
                seen_ids=seen_decision_ids,
                timeout_s=180.0,
            )

            if not new_decisions:
                details.append({
                    "index": idx,
                    "status": "failed",
                    "stage": "decision_stream",
                    "news_id": external_news_id,
                    "news_event_id": news_event_id,
                    "news_title": news_item.get("title", "")[:100],
                    "error": "decision_not_received",
                })
                _print_progress("decision missing", idx, len(news_items), f"event_id={news_event_id}")
                continue

            # 处理决策结果
            decision = new_decisions[0]
            match_result = decision.get("match_result", {}) or {}

            # 提取匹配信息
            matched_subject_key = str(match_result.get("matched_subject_key") or "")
            matched_theme_name = match_result.get("matched_theme_name")
            confidence = match_result.get("confidence", 0.0)
            decision_type = decision.get("decision_type", "")
            action = decision.get("action", "")

            # 记录成功结果
            details.append({
                "index": idx,
                "status": "ok",
                "stage": "decision_stream",
                "news_id": external_news_id,
                "news_event_id": news_event_id,
                "news_title": news_item.get("title", "")[:100],
                "news_source": news_item.get("source", ""),
                "publish_date": news_item.get("publish_date", ""),
                "matched_subject_key": matched_subject_key,
                "matched_theme_name": matched_theme_name,
                "confidence": confidence,
                "decision_type": decision_type,
                "action": action,
                "reason_code": match_result.get("reason_code", ""),
                "raw_news": news_item.get("raw_text", "")[:500],  # 保留原始新闻文本供分析
            })

            current_ok = sum(1 for row in details if row.get("status") == "ok")
            current_failed = sum(1 for row in details if row.get("status") == "failed")

            _print_progress(
                "decision received",
                idx,
                len(news_items),
                f"{action} -> {matched_theme_name or '无匹配'} | conf={confidence:.2f} | ok={current_ok}/{current_ok+current_failed}"
            )

        # 生成报告
        report = _build_report(details)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        logger.info(f"测试完成！报告已保存: {output_path}")
        logger.info(f"处理统计: {report['processed']} 条新闻，成功 {report['successful']} 条，失败 {report['failed']} 条")
        logger.info(f"成功率: {report['success_rate']:.2%}，平均置信度: {report['avg_confidence']:.2f}")

        # 打印匹配最多的主题
        if report["theme_distribution"]:
            logger.info("匹配最多的主题:")
            for theme, count in list(report["theme_distribution"].items())[:5]:
                logger.info(f"  {theme}: {count} 次")

        # 打印摘要
        print(json.dumps({
            "events": report["events"],
            "processed": report["processed"],
            "successful": report["successful"],
            "failed": report["failed"],
            "success_rate": report["success_rate"],
            "avg_confidence": report["avg_confidence"],
            "report_path": str(output_path),
        }, ensure_ascii=False))

    finally:
        # 清理资源
        try:
            await news_handler.stop_storage_service()
        except Exception as e:
            logger.error(f"停止news_handler失败: {e}")

        try:
            await theme_processor.stop()
        except Exception as e:
            logger.error(f"停止theme_processor失败: {e}")

        await conn.close()

        # 清理streams
        try:
            await redis_client.delete(raw_stream, structured_stream, decision_stream, dead_letter_stream)
        except Exception as e:
            logger.error(f"清理streams失败: {e}")

        if hasattr(base_gateway, "close"):
            await base_gateway.close()


if __name__ == "__main__":
    asyncio.run(main())