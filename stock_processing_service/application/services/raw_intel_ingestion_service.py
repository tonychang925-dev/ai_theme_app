# ai_theme_app/stock_processing_service/application/services/raw_intel_ingestion_service.py
"""
Phase 6A: 原始公告入库服务

从 AnnouncementCollector 接收标准化 doc list，负责：
  - 补充 checksum / dedupe_key（collector 已预计算，此处做兜底）
  - 逐条调用 DatabaseGateway.upsert_raw_intel_document() 幂等写入
  - 返回 upsert 统计 {inserted, updated, failed, total}

不负责：
  - LLM 结构化
  - PDF 下载/解析
  - stream 投递
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

TZ_CN = timezone(timedelta(hours=8))


class RawIntelIngestionService:
    """一手信息文档入库服务。

    用法：
        from database_service.gateway import DatabaseGateway
        gw = await DatabaseGateway.get_instance()
        svc = RawIntelIngestionService(gw)
        stats = await svc.ingest(docs)
        # stats = {"inserted": 45, "updated": 5, "failed": 0, "total": 50}
    """

    def __init__(self, gateway: Any) -> None:
        """Args:
            gateway: DatabaseGateway 实例（写操作使用 _client）。
        """
        self._gateway = gateway

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    async def ingest(self, docs: List[Dict[str, Any]]) -> Dict[str, int]:
        """逐条幂等写入 raw_intel_document，返回统计。

        Args:
            docs: AnnouncementCollector.collect() 产出的 dict list。

        Returns:
            {"inserted": N, "updated": N, "failed": N, "total": N}
        """
        if not docs:
            return {"inserted": 0, "updated": 0, "failed": 0, "total": 0}

        inserted = 0
        updated = 0
        failed = 0

        for doc in docs:
            try:
                # 兜底：确保 checksum 和 dedupe_key 存在
                self._ensure_identity_fields(doc)

                # 幂等写入
                row = await self._gateway.upsert_raw_intel_document(doc)

                # 判断插入还是更新
                # created_at == updated_at → 新插入
                # updated_at > created_at → 更新已有行
                created = row.get("created_at")
                updated_at = row.get("updated_at")
                if created and updated_at and created != updated_at:
                    updated += 1
                else:
                    inserted += 1

            except Exception:
                logger.exception("raw_intel_document upsert 失败: source_system=%s source_id=%s",
                                 doc.get("source_system"), doc.get("source_id"))
                failed += 1

        stats = {"inserted": inserted, "updated": updated, "failed": failed, "total": len(docs)}
        logger.info("RawIntelIngestionService.ingest 完成: %s", stats)
        return stats

    async def ingest_one(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        """单条幂等写入，返回完整行。"""
        self._ensure_identity_fields(doc)
        return await self._gateway.upsert_raw_intel_document(doc)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_identity_fields(doc: Dict[str, Any]) -> None:
        """兜底：若 collector 未预计算，则在此补全 checksum 和 dedupe_key。"""
        if not doc.get("checksum"):
            doc["checksum"] = _compute_checksum(
                doc.get("title", ""),
                doc.get("stock_code", ""),
                doc.get("publish_time", ""),
            )
        if not doc.get("dedupe_key"):
            doc["dedupe_key"] = _build_dedupe_key(
                doc.get("source_system", ""),
                doc.get("source_type", ""),
                doc.get("source_id", ""),
            )

    # ------------------------------------------------------------------
    # 可选：直接结合 Collector 的便捷方法
    # ------------------------------------------------------------------

    async def collect_and_ingest(
        self,
        collector: Any,
        days_back: int = 1,
    ) -> Dict[str, int]:
        """一键：采集 + 入库。

        Args:
            collector: AnnouncementCollector 实例。
            days_back: 往前抓取天数。

        Returns:
            ingest 统计 dict。
        """
        docs = await collector.collect(days_back=days_back)
        return await self.ingest(docs)


# ------------------------------------------------------------------
# 模块级工具函数（与 AnnouncementCollector 保持一致）
# ------------------------------------------------------------------

def _compute_checksum(title: str, stock_code: str, publish_time: Any) -> str:
    raw = f"{title or ''}|{stock_code or ''}|{str(publish_time or '')}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _build_dedupe_key(source_system: str, source_type: str, source_id: str) -> str:
    return f"{source_system}:{source_type}:{source_id}"
