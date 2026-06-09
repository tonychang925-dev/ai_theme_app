"""JYHF Producer — 包装已有 jyhf.import_stock_daily 逻辑.

保持现有 JYHF 采集行为完全不变，只做协议适配。
"""
from __future__ import annotations

import json
import logging

from stock_processing_service.application.jobs.subject_stock_snapshot.base import (
    SubjectStockDailySnapshotProducer,
    SubjectStockSnapshotBuildRequest,
    SubjectStockSnapshotBuildResult,
)

logger = logging.getLogger(__name__)


class JyhfSubjectStockDailySnapshotProducer(SubjectStockDailySnapshotProducer):
    """JYHF API 股票日快照 Producer（默认）.

    包装已有 import_jyhf_stock_daily_incremental 逻辑：
    遍历 subject_key → 调用 JYHF stock/realtime-by-subject/v2 → 写入 subject_stock_daily_snapshot.
    """

    provider = "jyhf"

    def __init__(self, db_pool=None, jyhf_token: str = ""):
        self._db_pool = db_pool
        self._jyhf_token = jyhf_token

    async def build(
        self,
        request: SubjectStockSnapshotBuildRequest,
    ) -> SubjectStockSnapshotBuildResult:
        from database_service.managers.postgres_manager import PostgresDatabaseManager
        from database_service.scripts.import_jyhf_stock_daily_incremental import (
            build_rows_from_subject_records,
            ensure_tables,
            get_postgres_config,
            load_rows,
            refresh_current_mapping,
        )
        from sync_jyhf_to_local import resolve_token
        from theme_collector import APIClient

        trade_date_str = request.trade_date.isoformat()
        batch_id = request.batch_id or f"jyhf_subject_stock_daily_{request.trade_date:%Y%m%d}"
        resolved_on_existing = request.resolved_on_existing()

        # ── Token ──
        token = resolve_token(self._jyhf_token or None)
        if not token:
            return SubjectStockSnapshotBuildResult(
                provider="jyhf",
                trade_date=trade_date_str,
                status="failed",
                warnings=["missing JYHF token"],
            )

        manager = PostgresDatabaseManager(get_postgres_config())
        await manager.connect()
        try:
            await ensure_tables(manager)

            # ── 加载 subject_keys ──
            subject_keys = await self._load_subject_keys(manager)
            if not subject_keys:
                return SubjectStockSnapshotBuildResult(
                    provider="jyhf",
                    trade_date=trade_date_str,
                    status="failed",
                    warnings=["no jyhf subjects found in DB"],
                )

            # ── on_existing 处理 ──
            if resolved_on_existing == "skip":
                collect_subjects = await self._filter_missing_subjects(
                    manager, subject_keys, trade_date_str,
                )
                if not collect_subjects:
                    existing_count = await self._count_existing(manager, trade_date_str)
                    return SubjectStockSnapshotBuildResult(
                        provider="jyhf",
                        trade_date=trade_date_str,
                        status="ok_existing",
                        affected_rows=existing_count,
                        warnings=[
                            f"snapshot already exists for {trade_date_str}",
                            "如需切换数据源重建，请选择"删除后重建 (replace)"模式",
                        ],
                        metrics={"subjects_total": len(subject_keys)},
                    )
            elif resolved_on_existing == "replace":
                await self._delete_existing(manager, trade_date_str)
                collect_subjects = subject_keys
            else:  # upsert — 全量采集，ON CONFLICT 自动更新
                collect_subjects = subject_keys

            # ── API 采集 ──
            client = APIClient(token)
            subject_records = await self._collect_subject_records(
                client, collect_subjects, trade_date_str,
            )
            rows, touched_subjects = build_rows_from_subject_records(
                subject_records, trade_date_str, batch_id,
            )
            count = await load_rows(manager, rows)
            map_count, staging_count, serving_count = await refresh_current_mapping(
                manager, touched_subjects, trade_date_str, batch_id,
            )

            return SubjectStockSnapshotBuildResult(
                provider="jyhf",
                trade_date=trade_date_str,
                status="ok" if count > 0 else "ok_no_data",
                affected_rows=count,
                metrics={
                    "source": "jyhf_api",
                    "batch_id": batch_id,
                    "subjects_total": len(subject_keys),
                    "subjects_collected": len(collect_subjects),
                    "subjects_touched": len(touched_subjects),
                    "current_map": map_count,
                    "staging": staging_count,
                    "serving": serving_count,
                    "api_stats": dict(client.stats),
                },
            )
        except Exception as exc:
            logger.exception("JYHF producer build failed")
            return SubjectStockSnapshotBuildResult(
                provider="jyhf",
                trade_date=trade_date_str,
                status="failed",
                warnings=[f"{type(exc).__name__}: {exc}"],
            )
        finally:
            await manager.disconnect()

    # ── private helpers ──

    async def _load_subject_keys(self, manager) -> list[str]:
        async with manager.pool.acquire() as conn:
            has_node = await conn.fetchval(
                "SELECT to_regclass('public.subject_node_staging') IS NOT NULL",
            )
            if has_node:
                rows = await conn.fetch(
                    """SELECT DISTINCT subject_key FROM subject_node_staging
                       WHERE subject_key IS NOT NULL ORDER BY subject_key""",
                )
            else:
                rows = await conn.fetch(
                    """SELECT DISTINCT source_id AS subject_key
                       FROM theme_master
                       WHERE source_system = 'jyhf' AND source_id IS NOT NULL
                       ORDER BY source_id""",
                )
        return [str(r["subject_key"]) for r in rows]

    async def _filter_missing_subjects(
        self, manager, subject_keys: list[str], trade_date: str,
    ) -> list[str]:
        from datetime import date as _date
        async with manager.pool.acquire() as conn:
            existing = await conn.fetch(
                """SELECT DISTINCT subject_key FROM subject_stock_daily_snapshot
                   WHERE trade_date = $1::date AND subject_key = ANY($2::varchar[])""",
                _date.fromisoformat(trade_date),
                subject_keys,
            )
        existing_keys = {str(r["subject_key"]) for r in existing}
        return [k for k in subject_keys if k not in existing_keys]

    async def _count_existing(self, manager, trade_date: str) -> int:
        from datetime import date as _date
        async with manager.pool.acquire() as conn:
            return int(await conn.fetchval(
                "SELECT COUNT(*) FROM subject_stock_daily_snapshot WHERE trade_date = $1",
                _date.fromisoformat(trade_date),
            ) or 0)

    async def _delete_existing(self, manager, trade_date: str) -> None:
        from datetime import date as _date
        async with manager.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM subject_stock_daily_snapshot WHERE trade_date = $1",
                _date.fromisoformat(trade_date),
            )

    async def _collect_subject_records(
        self, client, subject_keys: list[str], trade_date: str,
    ) -> list:
        import asyncio
        from theme_collector import DataCollector

        out: list = []
        completed = 0
        failed = 0
        total = len(subject_keys)
        sem = asyncio.Semaphore(20)
        lock = asyncio.Lock()

        def _fetch(subject_key: str):
            try:
                data = client.request(
                    "stock/realtime-by-subject/v2",
                    {
                        "sort": "pctChg", "sortType": "desc",
                        "date": trade_date,
                        "subjectId": subject_key,
                        "start": 0, "end": 1200,
                    },
                    f"stock_daily_{trade_date}",
                )
                rows = DataCollector.extract_items(data)
                valid = [row for row in rows if isinstance(row, list)]
                return (subject_key, valid, None)
            except Exception as e:
                return (subject_key, None, str(e))

        async def _fetch_with_sem(subject_key: str):
            nonlocal completed, failed
            async with sem:
                subj, rows, err = await asyncio.to_thread(_fetch, subject_key)
            async with lock:
                completed += 1
                if err:
                    failed += 1
                elif rows:
                    out.append((subj, rows))
                if completed % 50 == 0 or completed == total:
                    logger.info(
                        "JYHF stock daily: %s/%s success=%s fail=%s",
                        completed, total, completed - failed, failed,
                    )

        await asyncio.gather(*[_fetch_with_sem(k) for k in subject_keys])
        return out
