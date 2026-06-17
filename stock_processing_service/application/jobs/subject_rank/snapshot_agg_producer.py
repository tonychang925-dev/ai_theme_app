"""SnapshotAgg Producer — 从 subject_stock_daily_snapshot 聚合生成 subject_rank_daily.

不依赖 JYHF API；纯 SQL 聚合 + 横截面打分。

v1 heat 公式:
  heat_score =
      0.30 * amount_weighted_pct_score
    + 0.25 * limit_up_score
    + 0.20 * top3_pct_score
    + 0.15 * amount_score
    + 0.10 * up_ratio_score

各项通过 PERCENT_RANK() 横截面归一化到 0~100.
"""
from __future__ import annotations

import logging
from datetime import date

from stock_processing_service.application.jobs.subject_rank.base import (
    SubjectRankBuildRequest,
    SubjectRankBuildResult,
    SubjectRankProducer,
)

logger = logging.getLogger(__name__)

_MIN_STOCK_COUNT = 3


# ── v1 聚合 + 打分 SQL ──
# 分两个 CTE: heat_scored 先算 heat（数值），final_rank 再算 heat_name（依赖 heat）
_BUILD_SQL = f"""
WITH base AS (
    SELECT
        trade_date,
        subject_key,
        COUNT(*) AS stock_count,
        SUM(COALESCE(amount, 0)) AS amount_sum,
        SUM(COALESCE(volume, 0)) AS volume_sum,
        AVG(pct_chg) AS avg_pct_chg,
        SUM(COALESCE(pct_chg, 0) * COALESCE(amount, 0))
            / NULLIF(SUM(COALESCE(amount, 0)), 0) AS amount_weighted_pct_chg,
        COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) >= 9.8) AS limit_up_count,
        COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) > 0) AS up_count,
        COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) < 0) AS down_count,
        CASE WHEN COUNT(*) > 0
            THEN COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) > 0)::numeric / COUNT(*)::numeric
            ELSE 0
        END AS up_ratio,
        AVG(pct_chg) FILTER (WHERE rank_order <= 3) AS top3_avg_pct_chg,
        AVG(pct_chg) FILTER (WHERE is_leader = TRUE) AS leader_avg_pct_chg
    FROM subject_stock_daily_snapshot
    WHERE trade_date = $1::date
    GROUP BY trade_date, subject_key
    HAVING COUNT(*) >= {_MIN_STOCK_COUNT}
),
scored AS (
    SELECT
        *,
        PERCENT_RANK() OVER (ORDER BY COALESCE(amount_weighted_pct_chg, 0)) * 100
            AS amount_weighted_pct_score,
        PERCENT_RANK() OVER (ORDER BY COALESCE(limit_up_count, 0)) * 100
            AS limit_up_score,
        PERCENT_RANK() OVER (ORDER BY COALESCE(top3_avg_pct_chg, -999)) * 100
            AS top3_pct_score,
        PERCENT_RANK() OVER (ORDER BY LN(NULLIF(COALESCE(amount_sum, 0), 0) + 1)) * 100
            AS amount_score,
        COALESCE(up_ratio, 0) * 100 AS up_ratio_score
    FROM base
),
heat_scored AS (
    SELECT
        *,
        ROUND(
            0.30 * COALESCE(amount_weighted_pct_score, 0)
          + 0.25 * COALESCE(limit_up_score, 0)
          + 0.20 * COALESCE(top3_pct_score, 0)
          + 0.15 * COALESCE(amount_score, 0)
          + 0.10 * COALESCE(up_ratio_score, 0)
        )::integer AS heat
    FROM scored
),
final_rank AS (
    SELECT
        *,
        CASE
            WHEN heat >= 85 THEN '极热'
            WHEN heat >= 70 THEN '热'
            WHEN heat >= 55 THEN '活跃'
            WHEN heat >= 40 THEN '温和'
            ELSE '冷'
        END AS heat_name,
        ROW_NUMBER() OVER (ORDER BY heat DESC) AS hot_rank,
        COUNT(*) OVER () AS total_subjects
    FROM heat_scored
)
INSERT INTO subject_rank_daily (
    subject_key, rank_date, heat, heat_name, pct_chg, his_pct_chg,
    red, description, source_system, created_at, updated_at
)
SELECT
    fr.subject_key,
    fr.trade_date,
    fr.heat,
    fr.heat_name,
    ROUND(fr.avg_pct_chg::numeric, 4),
    NULL::numeric,
    COALESCE(fr.avg_pct_chg, 0) > 0,
    CONCAT(
        '板块热度', fr.heat, '（', fr.heat_name, '），排名', fr.hot_rank, '/', fr.total_subjects,
        '，成分股', fr.stock_count, '只，上涨', COALESCE(fr.up_count, 0), '只（',
        ROUND(COALESCE(fr.up_ratio, 0) * 100, 1), '%），涨停', COALESCE(fr.limit_up_count, 0), '家',
        '，均价涨幅', ROUND(fr.avg_pct_chg::numeric, 2), '%',
        '，成交额',
        CASE
            WHEN fr.amount_sum >= 100000000 THEN CONCAT(ROUND(fr.amount_sum / 100000000, 2), '亿')
            WHEN fr.amount_sum >= 10000 THEN CONCAT(ROUND(fr.amount_sum / 10000, 2), '万')
            ELSE ROUND(fr.amount_sum::numeric, 2)::text
        END
    ),
    'snapshot_agg',
    NOW(),
    NOW()
FROM final_rank fr
ON CONFLICT (subject_key, rank_date)
DO UPDATE SET
    heat = EXCLUDED.heat,
    heat_name = EXCLUDED.heat_name,
    pct_chg = EXCLUDED.pct_chg,
    his_pct_chg = EXCLUDED.his_pct_chg,
    red = EXCLUDED.red,
    description = EXCLUDED.description,
    source_system = EXCLUDED.source_system,
    updated_at = NOW()
"""


class SnapshotAggSubjectRankProducer(SubjectRankProducer):
    """从 subject_stock_daily_snapshot 聚合生成 subject_rank_daily.

    不依赖 JYHF API；依赖 subject_stock_daily_snapshot (可由 JYHF 或 TushareJoin 提供).

    v1 heat 公式: 成交额加权涨幅 + 涨停数 + top3涨幅 + 成交额 + 上涨占比.
    """

    provider = "snapshot_agg"

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    async def build(
        self,
        request: SubjectRankBuildRequest,
    ) -> SubjectRankBuildResult:
        td = request.trade_date
        trade_date_str = td.isoformat()
        batch_id = request.batch_id or f"snapshot_agg_subject_rank_{td:%Y%m%d}"
        resolved_on_existing = request.resolved_on_existing()

        async with self._db_pool.acquire() as conn:
            # ── 前置检查 1: subject_stock_daily_snapshot 是否就绪 ──
            snapshot_count = await conn.fetchval(
                "SELECT COUNT(*) FROM subject_stock_daily_snapshot WHERE trade_date = $1", td,
            )
            if not snapshot_count:
                return SubjectRankBuildResult(
                    provider="snapshot_agg",
                    trade_date=trade_date_str,
                    status="failed",
                    warnings=["subject_stock_daily_snapshot is empty — run stock_snapshot.build first"],
                    metrics={"snapshot_rows": 0},
                )

            # ── 前置检查 2: 质量检查（在任何修改之前）──
            quality = await self._check_quality(conn, td)

            # ── on_existing 处理 ──
            if resolved_on_existing == "skip":
                existing = await conn.fetchval(
                    "SELECT COUNT(*) FROM subject_rank_daily WHERE rank_date = $1",
                    td,
                )
                if existing:
                    return SubjectRankBuildResult(
                        provider="snapshot_agg",
                        trade_date=trade_date_str,
                        status="ok_existing",
                        affected_rows=int(existing),
                        warnings=[
                            f"subject_rank_daily already exists for {trade_date_str}",
                            "如需切换数据源重建，请选择\"删除后重建 (replace)\"模式",
                        ],
                        metrics={"snapshot_rows": int(snapshot_count), "existing_rows": int(existing)},
                    )

            affected_rows = 0
            if resolved_on_existing == "replace":
                # 事务包裹：DELETE + INSERT 原子执行
                async with conn.transaction():
                    await conn.execute(
                        "DELETE FROM subject_rank_daily WHERE rank_date = $1",
                        td,
                    )
                    affected = await conn.execute(_BUILD_SQL, td)
                affected_rows = self._parse_affected(affected)
            else:
                affected = await conn.execute(_BUILD_SQL, td)
                affected_rows = self._parse_affected(affected)

            # ── 写入后质量检查：从 subject_rank_daily 读取真实值 ──
            if affected_rows > 0:
                written = await self._check_written_quality(conn, td)
            else:
                written = {}

        return SubjectRankBuildResult(
            provider="snapshot_agg",
            trade_date=trade_date_str,
            status="ok" if affected_rows > 0 else "ok_no_data",
            affected_rows=affected_rows,
            warnings=(
                [f"only {affected_rows} subjects with >= {_MIN_STOCK_COUNT} stocks"]
                if affected_rows < 20 and affected_rows > 0 else []
            ),
            metrics={
                "source": "subject_stock_daily_snapshot_aggregation",
                "batch_id": batch_id,
                "heat_formula": "v1",
                "snapshot_rows": int(snapshot_count),
                "snapshot_subject_count": quality["snapshot_subject_count"],
                "ranked_subject_count": written.get("ranked_subject_count", quality["ranked_subject_count"]),
                "top100_count": written.get("top100_count", 0),
                "missing_name_count": quality.get("missing_name_count", 0),
                "avg_heat": written.get("avg_heat", quality["avg_heat"]),
                "max_heat": written.get("max_heat", 0),
                "min_heat": written.get("min_heat", 0),
                "on_existing": resolved_on_existing,
                "force": request.force,
            },
        )

    async def _check_quality(self, conn, td: date) -> dict:
        """质量预检：统计聚合前的数据分布."""
        row = await conn.fetchrow(
            """
            WITH agg AS (
                SELECT
                    subject_key,
                    COUNT(*) AS stock_count,
                    AVG(pct_chg) AS avg_pct_chg,
                    SUM(COALESCE(pct_chg, 0) * COALESCE(amount, 0))
                        / NULLIF(SUM(COALESCE(amount, 0)), 0) AS amount_weighted_pct_chg,
                    COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) >= 9.8) AS limit_up_count,
                    COUNT(*) FILTER (WHERE COALESCE(pct_chg, 0) > 0)::numeric
                        / NULLIF(COUNT(*), 0) AS up_ratio,
                    AVG(pct_chg) FILTER (WHERE rank_order <= 3) AS top3_avg_pct_chg,
                    SUM(COALESCE(amount, 0)) AS amount_sum
                FROM subject_stock_daily_snapshot
                WHERE trade_date = $1::date
                GROUP BY subject_key
            )
            SELECT
                COUNT(*) AS snapshot_subject_count,
                COUNT(*) FILTER (WHERE stock_count >= $2) AS ranked_subject_count,
                ROUND(AVG(avg_pct_chg) FILTER (WHERE stock_count >= $2)::numeric, 4) AS avg_heat
            FROM agg
            """,
            td,
            _MIN_STOCK_COUNT,
        )
        return {
            "snapshot_subject_count": int((row or {}).get("snapshot_subject_count") or 0),
            "ranked_subject_count": int((row or {}).get("ranked_subject_count") or 0),
            "top100_count": 0,
            "missing_name_count": 0,
            "avg_heat": float((row or {}).get("avg_heat") or 0),
            "max_heat": 0,
            "min_heat": 0,
        }

    async def _check_written_quality(self, conn, td: date) -> dict:
        """写入后质量检查：从 subject_rank_daily 读取真实值."""
        row = await conn.fetchrow(
            """
            WITH ranked AS (
                SELECT
                    subject_key,
                    heat,
                    ROW_NUMBER() OVER (ORDER BY heat DESC) AS hot_rank
                FROM subject_rank_daily
                WHERE rank_date = $1
            )
            SELECT
                COUNT(*) AS ranked_subject_count,
                COUNT(*) FILTER (WHERE hot_rank <= 100) AS top100_count,
                ROUND(AVG(heat)::numeric, 2) AS avg_heat,
                MAX(heat) AS max_heat,
                MIN(heat) AS min_heat
            FROM ranked
            """,
            td,
        )
        if row is None:
            return {}
        return {
            "ranked_subject_count": int(row["ranked_subject_count"] or 0),
            "top100_count": int(row["top100_count"] or 0),
            "avg_heat": float(row["avg_heat"] or 0),
            "max_heat": int(row["max_heat"] or 0),
            "min_heat": int(row["min_heat"] or 0),
        }

    @staticmethod
    def _parse_affected(result: str | None) -> int:
        if not result:
            return 0
        try:
            return int(str(result).split()[-1])
        except (ValueError, IndexError):
            return 0
