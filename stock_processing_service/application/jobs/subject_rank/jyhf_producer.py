"""JYHF Producer — 从本地 history JSONL 中提取 rank 行写入 subject_rank_daily.

不重新调用 JYHF API；依赖 sync_jyhf_to_local 已把 history JSONL 落地。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Sequence

from stock_processing_service.application.jobs.subject_rank.base import (
    SubjectRankBuildRequest,
    SubjectRankBuildResult,
    SubjectRankProducer,
)

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
HISTORY_DIR = PROJECT_ROOT / "theme_data_complete" / "history"


def _to_int(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_date(value: object):
    from datetime import date as _date
    if value is None:
        return None
    raw = str(value)[:10]
    try:
        return _date.fromisoformat(raw)
    except ValueError:
        return None


def _first_value(row: dict, *keys: str):
    for k in keys:
        v = row.get(k)
        if v is not None:
            return v
    return None


def _iter_history_files(subject_keys: Sequence[str]) -> list[Path]:
    """返回与给定 subject_keys 匹配的 history JSONL 文件."""
    if not HISTORY_DIR.exists():
        return []
    key_set = set(subject_keys)
    files = sorted(HISTORY_DIR.glob("*_history.jsonl"))
    if not key_set:
        return files
    return [f for f in files if f.stem.replace("_history", "") in key_set]


def _extract_rank_rows(path: Path, batch_id: str) -> list[tuple]:
    """从单个 history JSONL 文件中提取 subject_rank_daily 行."""
    rows: list[tuple] = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                item_rows = record.get("rows") if isinstance(record, dict) else record
                if isinstance(item_rows, dict):
                    item_rows = [item_rows]
                if not isinstance(item_rows, list):
                    continue
                for row in item_rows:
                    if not isinstance(row, dict):
                        continue
                    subject_key = str(
                        _first_value(row, "subjectId", "subject_key", "subjectKey") or ""
                    ).strip()
                    rank_date = _to_date(_first_value(row, "rankDate", "rank_date"))
                    if not subject_key or rank_date is None:
                        continue
                    heat = _to_int(_first_value(row, "heat", "appearance_count", "appearanceCount"))
                    heat_name = _first_value(row, "heatName", "heat_name")
                    pct_chg = _to_float(_first_value(row, "pctChg", "pct_chg"))
                    his_pct_chg = _to_float(_first_value(row, "hisPctChg", "his_pct_chg"))
                    red = bool(_first_value(row, "red") or False)
                    description = _first_value(row, "description", "desc")
                    source_system = str(_first_value(row, "source_system", "sourceSystem") or "jyhf")
                    rows.append((
                        subject_key,
                        rank_date,
                        heat,
                        str(heat_name or ""),
                        pct_chg,
                        his_pct_chg,
                        red,
                        str(description or ""),
                        source_system,
                    ))
    except Exception:
        logger.exception("Failed to read history file: %s", path)
    return rows


_RANK_SQL = """
INSERT INTO subject_rank_daily (
    subject_key, rank_date, heat, heat_name, pct_chg, his_pct_chg,
    red, description, source_system, created_at, updated_at
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), NOW())
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


class JyhfSubjectRankProducer(SubjectRankProducer):
    """JYHF 题材热度排名 Producer（默认）.

    从本地 theme_data_complete/history/*_history.jsonl 提取 rank 行，
    写入 subject_rank_daily。不调用外部 API。
    """

    provider = "jyhf"

    def __init__(self, db_pool=None):
        self._db_pool = db_pool

    async def build(
        self,
        request: SubjectRankBuildRequest,
    ) -> SubjectRankBuildResult:
        trade_date_str = request.trade_date.isoformat()
        batch_id = request.batch_id or f"jyhf_subject_rank_{request.trade_date:%Y%m%d}"
        resolved_on_existing = request.resolved_on_existing()

        if not HISTORY_DIR.exists():
            return SubjectRankBuildResult(
                provider="jyhf",
                trade_date=trade_date_str,
                status="failed",
                warnings=["history dir not found: run jyhf_history sync first"],
            )

        # 收集所有 history 文件的 rank 行
        files = sorted(HISTORY_DIR.glob("*_history.jsonl"))
        all_rank_rows: list[tuple] = []
        subject_keys: set[str] = set()
        for path in files:
            rank_rows = _extract_rank_rows(path, batch_id)
            for row in rank_rows:
                all_rank_rows.append(row)
                subject_keys.add(str(row[0]))

        # 只保留目标日期的行
        rank_rows_for_date = [
            r for r in all_rank_rows
            if r[1].isoformat() == trade_date_str
        ]

        if not rank_rows_for_date:
            return SubjectRankBuildResult(
                provider="jyhf",
                trade_date=trade_date_str,
                status="ok_no_data",
                affected_rows=0,
                warnings=[f"no rank data for {trade_date_str} in {len(files)} history files"],
                metrics={"history_files": len(files)},
            )

        async with self._db_pool.acquire() as conn:
            # ── on_existing 处理 ──
            if resolved_on_existing == "skip":
                existing = await conn.fetchval(
                    "SELECT COUNT(*) FROM subject_rank_daily WHERE rank_date = $1",
                    request.trade_date,
                )
                if existing:
                    return SubjectRankBuildResult(
                        provider="jyhf",
                        trade_date=trade_date_str,
                        status="ok_existing",
                        affected_rows=int(existing),
                        warnings=[
                            f"subject_rank_daily already exists for {trade_date_str}",
                            "如需切换数据源重建，请选择\"删除后重建 (replace)\"模式",
                        ],
                        metrics={"existing_rows": int(existing)},
                    )
            elif resolved_on_existing == "replace":
                await conn.execute(
                    "DELETE FROM subject_rank_daily WHERE rank_date = $1",
                    request.trade_date,
                )

            # ── 写入 ──
            async with conn.transaction():
                await conn.executemany(_RANK_SQL, rank_rows_for_date)

        return SubjectRankBuildResult(
            provider="jyhf",
            trade_date=trade_date_str,
            status="ok",
            affected_rows=len(rank_rows_for_date),
            metrics={
                "source": "jyhf_history_jsonl",
                "batch_id": batch_id,
                "history_files": len(files),
                "total_rank_rows": len(all_rank_rows),
                "date_rank_rows": len(rank_rows_for_date),
                "subject_count": len({r[0] for r in rank_rows_for_date}),
            },
        )
