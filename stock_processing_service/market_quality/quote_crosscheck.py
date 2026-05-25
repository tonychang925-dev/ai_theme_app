"""P1-D 核心：JYHF × TDX 双源行情交叉校验服务."""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone, timedelta

from stock_processing_service.market_quality.crosscheck_rules import evaluate
from stock_processing_service.market_quality.crosscheck_repository import CrosscheckRepository
from stock_processing_service.market_quality.crosscheck_publisher import CrosscheckPublisher

logger = logging.getLogger("sps.crosscheck.quote_crosscheck")
TZ_CN = timezone(timedelta(hours=8))


class QuoteCrosscheckService:
    """双源行情校验服务.

    职责：
      1. 从 JYHF 和 TDX 表读取最新行情
      2. 计算价差、涨跌幅差、延迟
      3. 写入 market_quote_crosscheck
      4. 异常推送到 Redis

    不做策略信号，只做数据质量。
    """

    def __init__(self, repository: CrosscheckRepository, publisher: CrosscheckPublisher):
        self._repo = repository
        self._pub = publisher
        self.stats = {
            "last_run_at": None,
            "total_checks": 0,
            "ok": 0, "warn": 0, "critical": 0,
            "missing_source": 0, "stale_source": 0,
            "alg_writes": 0, "alg_published": 0,
            "last_error": None,
            "jyhf_stock_count": 0,
            "tdx_stock_count": 0,
            "matched_stock_count": 0,
        }

    def status(self) -> dict:
        return dict(self.stats)

    async def run_once(self, max_age_seconds: float = 30.0) -> dict:
        """执行一轮双源校验."""
        now = datetime.now(TZ_CN)
        today_str = str(date.today())
        ts_str = now.isoformat()

        summary = {
            "ts": ts_str,
            "trade_date": today_str,
            "max_age_seconds": max_age_seconds,
            "total": 0, "ok": 0, "warn": 0, "critical": 0,
            "missing_source": 0, "stale_source": 0,
            "written": 0, "published": 0,
        }

        # 1. 获取两边最新行情
        jyhf_quotes = await self._repo.fetch_latest_jyhf_quotes(max_age_seconds)
        tdx_quotes = await self._repo.fetch_latest_tdx_quotes(max_age_seconds)

        self.stats["jyhf_stock_count"] = len(jyhf_quotes)
        self.stats["tdx_stock_count"] = len(tdx_quotes)

        # 2. 取并集
        all_stock_ids = set(jyhf_quotes.keys()) | set(tdx_quotes.keys())
        self.stats["matched_stock_count"] = len(all_stock_ids)
        summary["total"] = len(all_stock_ids)

        if not all_stock_ids:
            logger.debug("no quotes in window (max_age=%ss)", max_age_seconds)
            self.stats["last_run_at"] = ts_str
            return summary

        # 3. 逐股票校验
        for stock_id in sorted(all_stock_ids):
            result = evaluate(
                stock_id=stock_id,
                jyhf=jyhf_quotes.get(stock_id),
                tdx=tdx_quotes.get(stock_id),
                now=now,
            )
            result["trade_date"] = today_str
            result["ts"] = ts_str

            # 统计
            status = result["crosscheck_status"]
            if status == "OK":
                summary["ok"] += 1
                self.stats["ok"] += 1
            elif status == "WARN":
                summary["warn"] += 1
                self.stats["warn"] += 1
            elif status == "CRITICAL":
                summary["critical"] += 1
                self.stats["critical"] += 1
            elif status == "MISSING_SOURCE":
                summary["missing_source"] += 1
                self.stats["missing_source"] += 1
            elif status == "STALE_SOURCE":
                summary["stale_source"] += 1
                self.stats["stale_source"] += 1

            # 写入 DB
            try:
                row_id = await self._repo.insert_crosscheck(result)
                if row_id:
                    summary["written"] += 1
                    self.stats["alg_writes"] += 1
            except Exception as exc:
                logger.warning("insert crosscheck %s failed: %s", stock_id, exc)

            # 异常推送 Redis
            if status != "OK":
                try:
                    await self._pub.publish(result)
                    summary["published"] += 1
                    self.stats["alg_published"] += 1
                except Exception as exc:
                    logger.warning("publish crosscheck %s failed: %s", stock_id, exc)

        self.stats["total_checks"] += summary["total"]
        self.stats["last_run_at"] = ts_str
        self.stats["last_error"] = None

        return summary

    async def get_db_summary(self, max_age_seconds: float = 120.0) -> dict:
        """从 DB 读取最近的校验汇总."""
        return await self._repo.get_status_summary(max_age_seconds)
