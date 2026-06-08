"""Tushare Join Producer — stock_daily_snapshot + subject_stock_map → subject_stock_daily_snapshot.

不直接调用外部 API，依赖:
  - stock_daily_snapshot: 已由 tushare.daily_bar 任务写入
  - subject_stock_map:    本地 JYHF 静态映射（无 trade_date 维度）
"""
from __future__ import annotations

import json
import logging
from datetime import date

from stock_processing_service.application.jobs.subject_stock_snapshot.base import (
    SubjectStockDailySnapshotProducer,
    SubjectStockSnapshotBuildRequest,
    SubjectStockSnapshotBuildResult,
)

logger = logging.getLogger(__name__)

# 全量缺失的 3 只退市/ST 股票 — 不视为质量问题
KNOWN_MISSING_STOCKS = frozenset({"002231", "300391", "603056"})


class TushareJoinSubjectStockDailySnapshotProducer(SubjectStockDailySnapshotProducer):
    """Tushare 日K + subject_stock_map → subject_stock_daily_snapshot.

    stock_id 格式: Tushare 带后缀 (000001.SZ) → JYHF 无后缀 (000001)
    匹配方式: SPLIT_PART(sds.stock_id, '.', 1) = ssm.stock_id
    """

    provider = "tushare_join"

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    async def build(
        self,
        request: SubjectStockSnapshotBuildRequest,
    ) -> SubjectStockSnapshotBuildResult:
        td = request.trade_date
        trade_date_str = td.isoformat()
        batch_id = request.batch_id or f"tushare_join_subject_stock_daily_{td:%Y%m%d}"
        resolved_on_existing = request.resolved_on_existing()

        async with self._db_pool.acquire() as conn:
            # ── 前置检查 1: stock_daily_snapshot 是否就绪 ──
            daily_count = await conn.fetchval(
                "SELECT COUNT(*) FROM stock_daily_snapshot WHERE trade_date = $1", td,
            )
            if not daily_count:
                return SubjectStockSnapshotBuildResult(
                    provider="tushare_join",
                    trade_date=trade_date_str,
                    status="failed",
                    warnings=["stock_daily_snapshot is empty — run tushare_kline first"],
                    metrics={"stock_daily_count": 0},
                )

            # ── 前置检查 2: subject_stock_map 是否有数据 ──
            map_count = await conn.fetchval(
                "SELECT COUNT(*) FROM subject_stock_map WHERE stock_id IS NOT NULL AND stock_id <> ''",
            )
            if not map_count:
                return SubjectStockSnapshotBuildResult(
                    provider="tushare_join",
                    trade_date=trade_date_str,
                    status="failed",
                    warnings=["subject_stock_map is empty — run jyhf.load_staging first"],
                    metrics={"stock_daily_count": int(daily_count), "mapped_stock_count": 0},
                )

            # ── on_existing 处理 ──
            if resolved_on_existing == "skip":
                existing = await conn.fetchval(
                    "SELECT COUNT(*) FROM subject_stock_daily_snapshot WHERE trade_date = $1", td,
                )
                if existing:
                    return SubjectStockSnapshotBuildResult(
                        provider="tushare_join",
                        trade_date=trade_date_str,
                        status="ok_existing",
                        affected_rows=int(existing),
                        warnings=[f"snapshot already exists for {trade_date_str}"],
                        metrics={"stock_daily_count": int(daily_count)},
                    )
            elif resolved_on_existing == "replace":
                await conn.execute(
                    "DELETE FROM subject_stock_daily_snapshot WHERE trade_date = $1", td,
                )
            # upsert: ON CONFLICT 自动处理

            # ── 质量检查: 匹配率 ──
            quality = await self._check_quality(conn, td, int(daily_count), int(map_count))

            # ── 执行 JOIN INSERT ──
            affected = await conn.execute(
                _BUILD_SQL, td, batch_id,
            )
            # asyncpg 返回 "INSERT 0 N" 格式字符串
            affected_rows = self._parse_affected(affected)

            # ── 缺失股票 — 排除已知退市/ST ──
            real_missing = [
                s for s in quality["missing_stocks"]
                if s["stock_id"] not in KNOWN_MISSING_STOCKS
            ]

            return SubjectStockSnapshotBuildResult(
                provider="tushare_join",
                trade_date=trade_date_str,
                status="ok" if affected_rows > 0 else "ok_no_data",
                affected_rows=affected_rows,
                warnings=(
                    [f"{len(real_missing)} stocks not in tushare daily (excl. known delisted)"]
                    if real_missing else []
                ),
                metrics={
                    "source": "tushare_daily_join_subject_stock_map",
                    "batch_id": batch_id,
                    "stock_daily_count": quality["stock_daily_count"],
                    "mapped_stock_count": quality["mapped_stock_count"],
                    "mapped_distinct_stocks": quality["mapped_distinct_stocks"],
                    "matched_stock_count": quality["matched_stock_count"],
                    "missing_stock_count": quality["missing_stock_count"],
                    "real_missing_count": len(real_missing),
                    "real_missing_stocks": [s["stock_id"] for s in real_missing[:20]],
                    "match_rate": quality["match_rate"],
                    "subject_count": quality.get("subject_count"),
                    "covered_subject_count": quality.get("covered_subject_count"),
                    "coverage_pct": quality.get("coverage_pct"),
                    "on_existing": resolved_on_existing,
                    "force": request.force,
                },
            )

    # ── quality check ──

    async def _check_quality(
        self, conn, td: date, daily_count: int, map_count: int,
    ) -> dict:
        # 匹配数 (distinct stocks)
        matched = await conn.fetchval(
            """SELECT COUNT(DISTINCT ssm.stock_id)
               FROM subject_stock_map ssm
               JOIN stock_daily_snapshot sds
                 ON sds.trade_date = $1 AND SPLIT_PART(sds.stock_id, '.', 1) = ssm.stock_id
               WHERE ssm.stock_id IS NOT NULL AND ssm.stock_id <> ''""",
            td,
        ) or 0

        # 去重股票数（分母应为 distinct stock_id）
        distinct_mapped = await conn.fetchval(
            "SELECT COUNT(DISTINCT stock_id) FROM subject_stock_map WHERE stock_id IS NOT NULL AND stock_id <> ''",
        ) or 1

        # 缺失清单
        missing_rows = await conn.fetch(
            """SELECT ssm.stock_id, ssm.name,
                      COUNT(DISTINCT ssm.subject_key) AS subject_count
               FROM subject_stock_map ssm
               LEFT JOIN stock_daily_snapshot sds
                 ON sds.trade_date = $1 AND SPLIT_PART(sds.stock_id, '.', 1) = ssm.stock_id
               WHERE ssm.stock_id IS NOT NULL AND ssm.stock_id <> ''
                 AND sds.stock_id IS NULL
               GROUP BY ssm.stock_id, ssm.name
               ORDER BY subject_count DESC, ssm.stock_id""",
            td,
        )

        match_rate = (int(matched) / distinct_mapped) if distinct_mapped > 0 else 0.0

        return {
            "stock_daily_count": daily_count,
            "mapped_stock_count": map_count,
            "mapped_distinct_stocks": distinct_mapped,
            "matched_stock_count": int(matched),
            "missing_stock_count": len(missing_rows),
            "missing_stocks": [
                {"stock_id": r["stock_id"], "name": r["name"], "subjects": int(r["subject_count"])}
                for r in missing_rows
            ],
            "match_rate": round(match_rate, 4),
        }

    @staticmethod
    def _parse_affected(result: str | None) -> int:
        if not result:
            return 0
        try:
            return int(str(result).split()[-1])
        except (ValueError, IndexError):
            return 0


# ── 核心 JOIN SQL ──

_BUILD_SQL = """
INSERT INTO subject_stock_daily_snapshot (
    trade_date,
    subject_key,
    stock_id,
    stock_name,
    open_price,
    high_price,
    low_price,
    close_price,
    pre_close,
    pct_chg,
    volume,
    amount,
    rank_order,
    is_leader,
    limit_up,
    raw_json,
    ingest_batch_id
)
SELECT
    sds.trade_date,
    ssm.subject_key,
    ssm.stock_id,
    COALESCE(NULLIF(ssm.name, ''), sds.stock_name) AS stock_name,
    sds.open_price,
    sds.high_price,
    sds.low_price,
    sds.close_price,
    sds.pre_close,
    sds.pct_chg,
    sds.volume,
    sds.amount,

    ROW_NUMBER() OVER (
        PARTITION BY ssm.subject_key
        ORDER BY COALESCE(sds.pct_chg, -999) DESC,
                 COALESCE(sds.amount, 0) DESC
    ) AS rank_order,

    COALESCE(ssm.top, FALSE) AS is_leader,

    CASE
        WHEN COALESCE(sds.pct_chg, 0) >= 9.8 THEN TRUE
        ELSE FALSE
    END AS limit_up,

    jsonb_build_object(
        'snapshot_provider', 'tushare_join',
        'source', 'stock_daily_snapshot + subject_stock_map',
        'subject_stock_map_source_type', ssm.source_type,
        'map_evidence', ssm.evidence_json,
        'tushare_stock_id', sds.stock_id,
        'local_stock_id', ssm.stock_id
    ) AS raw_json,

    $2::varchar AS ingest_batch_id

FROM subject_stock_map ssm
JOIN stock_daily_snapshot sds
  ON sds.trade_date = $1::date
 AND SPLIT_PART(sds.stock_id, '.', 1) = ssm.stock_id

WHERE ssm.stock_id IS NOT NULL
  AND ssm.stock_id <> ''

ON CONFLICT (trade_date, subject_key, stock_id)
DO UPDATE SET
    stock_name = EXCLUDED.stock_name,
    open_price = EXCLUDED.open_price,
    high_price = EXCLUDED.high_price,
    low_price = EXCLUDED.low_price,
    close_price = EXCLUDED.close_price,
    pre_close = EXCLUDED.pre_close,
    pct_chg = EXCLUDED.pct_chg,
    volume = EXCLUDED.volume,
    amount = EXCLUDED.amount,
    rank_order = EXCLUDED.rank_order,
    is_leader = EXCLUDED.is_leader,
    limit_up = EXCLUDED.limit_up,
    raw_json = EXCLUDED.raw_json,
    ingest_batch_id = EXCLUDED.ingest_batch_id,
    updated_at = NOW()
"""
