"""新闻 payload 标准化器。

从 AkShareRealtimeNewsCollector._normalize_payload() 迁移，
归一化不同来源的新闻字段，保证下游兼容。

Phase 4E (2026-05-24):
  新增 collector_name / collector_version 标记，每个 payload 携带身份信息。
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))


def _pick(row: dict[str, Any], *keys: str) -> Any:
    """从行中按顺序尝试提取第一个非空字段值。"""
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip() != "":
            return value
    return None


def normalize_news_payload(
    row: dict[str, Any],
    *,
    run_id: str = "",
    default_source: str = "db_collector",
    collector_name: str = "RealTimeNewsCollector",
    collector_version: str = "phase4e",
) -> dict[str, str]:
    """标准化新闻 payload，与现有 stream:news:raw 消费者兼容。

    包含:
      - publish_date 7 天 stale 校验
      - source_channel 保留原始值
      - external_id 生成
      - collector_name / collector_version 身份标记

    Args:
        row: 原始新闻行（来自 crawler 或其他源）
        run_id: 运行 ID
        default_source: 默认来源标识
        collector_name: 采集器名称
        collector_version: 采集器版本

    Returns:
        标准格式 dict，包含 news_id, external_id, title, content, source,
        source_channel, publish_date, publish_time, collected_at, url, run_id,
        type, collector_name, collector_version
    """
    title = _pick(row, "title", "新闻标题", "标题") or ""
    content = _pick(row, "content", "新闻内容", "内容", "摘要") or title
    source = _pick(row, "source", "新闻来源", "来源") or default_source
    source_channel = _pick(row, "source_channel") or source
    url = _pick(row, "url", "链接", "新闻链接") or ""
    publish_date = _pick(row, "publish_date", "date", "日期")
    publish_time = _pick(row, "publish_time", "time", "发布时间", "时间")
    keywords = _pick(row, "keywords") or []

    now = datetime.now(TZ_CN)

    # publish_date 7 天 stale 校验
    if publish_date:
        try:
            pd = date.fromisoformat(str(publish_date)[:10])
            if pd < (now.date() - timedelta(days=7)):
                logger.debug("Rejecting stale publish_date=%s, using today", pd)
                publish_date = None
        except (ValueError, TypeError):
            publish_date = None
    if not publish_date:
        publish_date = now.date().isoformat()

    publish_time_text = str(publish_time or now.strftime("%H:%M:%S"))
    external_id = _pick(row, "external_id", "news_id", "id")

    if not external_id:
        raw = f"{title}|{content}|{publish_date}|{publish_time_text}"
        external_id = f"{source_channel}:" + hashlib.sha1(raw.encode()).hexdigest()[:24]

    payload: dict[str, str] = {
        "news_id": str(external_id),
        "external_id": str(external_id),
        "title": str(title),
        "content": str(content),
        "source": str(source),
        "source_channel": str(source_channel),
        "publish_date": str(publish_date)[:10],
        "publish_time": str(publish_time_text),
        "collected_at": now.isoformat(),
        "url": str(url),
        "run_id": run_id,
        "type": "raw_news",
        "collector_name": collector_name,
        "collector_version": collector_version,
    }

    # keywords 只在非空时加入
    if keywords:
        payload["keywords"] = ",".join(keywords) if isinstance(keywords, list) else str(keywords)

    return {k: v for k, v in payload.items() if v is not None}
