"""P1: 盘后复盘数据 readiness 检查服务。

独立于 BuildPostMarketRecapJob，用于 API 查询和任务流门禁。
检查 5 张核心表是否有当日数据，返回 ready / failed_precondition。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

# 核心表检查配置: (table_name, category, required)
CORE_TABLE_CHECKS: list[tuple[str, str, bool]] = [
    ("subject_stock_daily_snapshot", "base", True),
    ("theme_cycle_judgement_v2", "derived", True),
    ("money_flow_enhanced", "derived", True),
    ("strong_stock_watch_history", "derived", True),
    ("dragon_tiger_object", "derived", False),  # 无榜日可为空
]


@dataclass
class ReadinessResult:
    trade_date: str
    status: str  # ready | failed_precondition
    base_tables: dict[str, int] = field(default_factory=dict)
    derived_tables: dict[str, int] = field(default_factory=dict)
    missing_tables: list[str] = field(default_factory=list)
    skipped_tables: list[dict] = field(default_factory=list)
    error_code: str = ""
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "trade_date": self.trade_date,
            "status": self.status,
            "base_tables": self.base_tables,
            "derived_tables": self.derived_tables,
            "missing_tables": self.missing_tables,
            "skipped_tables": self.skipped_tables,
            "error_code": self.error_code,
            "diagnostics": self.diagnostics,
        }


class PostMarketReadinessService:
    """盘后复盘数据 readiness 检查服务。

    用法:
        service = PostMarketReadinessService(pool=asyncpg_pool)
        result = await service.check(trade_date)
        if result.status == "ready":
            ...
    """

    def __init__(self, pool=None):
        self._pool = pool

    async def check(self, trade_date: date) -> ReadinessResult:
        """检查 5 张核心表，返回 ReadinessResult。"""
        if self._pool is None:
            return ReadinessResult(
                trade_date=trade_date.isoformat(),
                status="failed_precondition",
                error_code="POST_MARKET_READINESS_CHECK_UNAVAILABLE",
                missing_tables=["readiness_checker_db_pool"],
                diagnostics={"reason": "no_db_pool"},
            )

        result = ReadinessResult(
            trade_date=trade_date.isoformat(),
            status="ready",
        )

        async with self._pool.acquire() as conn:
            for table_name, category, required in CORE_TABLE_CHECKS:
                cnt = 0
                try:
                    row = await conn.fetchrow(
                        f"SELECT COUNT(*) AS cnt FROM {table_name} WHERE trade_date = $1::date",
                        trade_date,
                    )
                    cnt = int(row["cnt"]) if row else 0
                except Exception as exc:
                    logger.warning("readiness check failed for table %s: %s", table_name, exc)
                    result.missing_tables.append(table_name)
                    continue

                if category == "base":
                    result.base_tables[table_name] = cnt
                else:
                    result.derived_tables[table_name] = cnt

                if cnt == 0:
                    if required:
                        result.missing_tables.append(table_name)
                    else:
                        reason = "no_dragon_tiger_day"
                        if table_name == "dragon_tiger_object":
                            job_row = await conn.fetchrow(
                                """
                                SELECT error_code, error_message, diagnostics
                                FROM post_market_job_status
                                WHERE trade_date = $1::date
                                  AND job_key = 'dragon_tiger_object_build'
                                """,
                                trade_date,
                            )
                            if job_row and job_row["error_code"]:
                                reason = str(job_row["error_code"])
                        result.skipped_tables.append({
                            "table": table_name,
                            "reason": reason,
                        })

        if result.missing_tables:
            result.status = "failed_precondition"
            result.error_code = "POST_MARKET_DERIVED_DATA_NOT_READY"

        return result
