"""P0-E: Intel Collection Pipeline Runtime (Stages 1-3).

Periodically executes the intel announcement upstream pipeline:

  Stage 1: AnnouncementCollector → fetch from CNINFO HTTP API
  Stage 2: RawIntelIngestionService → upsert into raw_intel_document
  Stage 3: IntelEventExtractor → LLM extract into structured_intel_event

Stage 4 (IntelStreamProducer → news_event + stream) is handled separately
by run_intel_stream_producer.py, which polls structured_intel_event for
stream_status='pending' rows.

Design:
  - Collection uses synchronous HTTP (cninfo), run in thread executor.
  - Ingestion is idempotent (dedupe_key + checksum upsert).
  - LLM extraction is the bottleneck; limit to N docs per cycle.
  - Once extracted, Stage 4 picks up the structured rows automatically.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from news_crawler_service.collectors.announcement_collector import AnnouncementCollector
from stock_processing_service.application.services.raw_intel_ingestion_service import (
    RawIntelIngestionService,
)
from stock_processing_service.domain.services.intel_event_extractor import (
    IntelEventExtractor,
)

CN_TZ = ZoneInfo("Asia/Shanghai")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run Intel collection pipeline (Stages 1-3) periodic loop."
    )
    parser.add_argument("--poll-interval-seconds", type=int, default=600,
                        help="Seconds between collection cycles (default 600 = 10 min)")
    parser.add_argument("--days-back", type=int, default=1,
                        help="Days back to collect announcements")
    parser.add_argument("--max-pages", type=int, default=5,
                        help="Max cninfo pages per cycle")
    parser.add_argument("--extraction-limit", type=int, default=20,
                        help="Max LLM extractions per cycle")
    parser.add_argument("--extraction-timeout", type=int, default=60,
                        help="LLM extraction timeout per doc")
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--once", action="store_true",
                        help="Run one cycle and exit")
    parser.add_argument("--status-path", default=None)
    parser.add_argument("--parent-pid", type=int, default=None)
    # Active-window mode: only run during 15:00-08:00 CN time
    parser.add_argument("--active-window-only", action="store_true", default=True,
                        help="Only run during 15:00-08:00 CN time window")
    return parser


class PipelineStats:
    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        self.cycles = 0
        self.collected_total = 0
        self.ingested_total = 0
        self.ingested_failed = 0
        self.extracted_total = 0
        self.extraction_failed = 0
        self.last_collect_at: str | None = None
        self.last_ingest_at: str | None = None
        self.last_extract_at: str | None = None
        self.last_error: str | None = None
        self.running = True

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "run_id": self.run_id,
            "cycles": self.cycles,
            "collected_total": self.collected_total,
            "ingested_total": self.ingested_total,
            "ingested_failed": self.ingested_failed,
            "extracted_total": self.extracted_total,
            "extraction_failed": self.extraction_failed,
            "last_collect_at": self.last_collect_at,
            "last_ingest_at": self.last_ingest_at,
            "last_extract_at": self.last_extract_at,
            "last_error": self.last_error,
        }


async def async_main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db_name = args.db_name or os.environ.get("PG_DATABASE", "stock_data_test")
    os.environ.setdefault("PG_DATABASE", db_name)
    os.environ.setdefault("DB_NAME", db_name)
    os.environ.setdefault("DB_TYPE", "postgresql")

    from database_service.gateway import DatabaseGateway
    from database_service.config import DatabaseConfig, DatabaseType

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=db_name)
    gateway = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)

    if args.parent_pid:
        asyncio.create_task(_watch_parent(args.parent_pid))

    run_id = args.run_id or os.environ.get("RUN_ID",
        f"intel_collection_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")

    stats = PipelineStats(run_id)
    status_path = Path(args.status_path) if args.status_path else None
    collector = AnnouncementCollector(max_pages=args.max_pages)
    ingestion_svc = RawIntelIngestionService(gateway)
    extractor = IntelEventExtractor(timeout=args.extraction_timeout)

    def _write_stats() -> None:
        if status_path:
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text(
                json.dumps(stats.to_dict(), ensure_ascii=False, indent=2)
            )

    def _in_active_window() -> bool:
        """Check if we're in the collection window (15:00-08:00 CN time)."""
        if not args.active_window_only:
            return True
        now = datetime.now(CN_TZ).time()
        # Active: 15:00-23:59 OR 00:00-08:00
        return now >= time(15, 0) or now < time(8, 0)

    try:
        while True:
            stats.cycles += 1

            if not _in_active_window():
                logging.info(
                    "Outside active window (15:00-08:00 CN), sleeping %s s",
                    args.poll_interval_seconds,
                )
                _write_stats()
                if args.once:
                    break
                await asyncio.sleep(args.poll_interval_seconds)
                continue

            try:
                # ── Stage 1: Collect ──────────────────────────────
                logging.info("[Stage 1] Collecting announcements (days_back=%s, max_pages=%s)",
                             args.days_back, args.max_pages)
                docs = await collector.collect(days_back=args.days_back)
                stats.collected_total += len(docs)
                stats.last_collect_at = datetime.now(timezone.utc).isoformat()
                logging.info("[Stage 1] Collected %s docs", len(docs))

                # ── Stage 2: Ingest ───────────────────────────────
                if docs:
                    logging.info("[Stage 2] Ingesting %s docs", len(docs))
                    ingest_stats = await ingestion_svc.ingest(docs)
                    stats.ingested_total += ingest_stats.get("inserted", 0) + ingest_stats.get("updated", 0)
                    stats.ingested_failed += ingest_stats.get("failed", 0)
                    stats.last_ingest_at = datetime.now(timezone.utc).isoformat()
                    logging.info(
                        "[Stage 2] Ingest done: inserted=%s updated=%s failed=%s",
                        ingest_stats.get("inserted"), ingest_stats.get("updated"), ingest_stats.get("failed"),
                    )

                # ── Stage 3: Extract ──────────────────────────────
                pending = await gateway.get_raw_intel_documents_by_status(
                    "pending", limit=args.extraction_limit
                )
                if pending:
                    # 预过滤：跳过例行公告（无投资价值）
                    skipped_routine = 0
                    filtered_pending = []
                    for doc in pending:
                        title = str(doc.get("title") or "").strip()
                        if _is_routine_announcement(title):
                            skipped_routine += 1
                            await gateway.update_raw_intel_llm_status(doc["id"], "skipped_routine")
                            continue
                        filtered_pending.append(doc)

                    if skipped_routine:
                        logging.info("[Stage 3] Skipped %s routine announcements", skipped_routine)

                    logging.info("[Stage 3] Extracting %s pending docs (filtered from %s)",
                                 len(filtered_pending), len(pending))
                    extracted = 0
                    for doc in filtered_pending:
                        try:
                            result = await extractor.extract_announcement(doc)
                            await gateway.insert_structured_intel_event(result)
                            await gateway.update_raw_intel_llm_status(doc["id"], "done")
                            extracted += 1
                            logging.info(
                                "[Stage 3] Extracted doc_id=%s stock=%s title=%s",
                                doc["id"], doc.get("stock_code", ""),
                                str(doc.get("title", ""))[:60],
                            )
                        except Exception:
                            logging.exception(
                                "[Stage 3] Extraction failed doc_id=%s stock=%s",
                                doc["id"], doc.get("stock_code", ""),
                            )
                            try:
                                await gateway.update_raw_intel_llm_status(doc["id"], "failed")
                            except Exception:
                                pass
                    stats.extracted_total += extracted
                    stats.extraction_failed += len(pending) - extracted
                    stats.last_extract_at = datetime.now(timezone.utc).isoformat()
                    logging.info("[Stage 3] Extracted %s/%s docs", extracted, len(pending))
                else:
                    logging.info("[Stage 3] No pending docs to extract")

                stats.last_error = None
            except Exception as exc:
                stats.last_error = str(exc)
                logging.exception("Intel collection pipeline cycle failed")

            _write_stats()

            if args.once:
                break
            await asyncio.sleep(args.poll_interval_seconds)

    finally:
        stats.running = False
        _write_stats()
        await extractor.close()
        close_fn = getattr(gateway, "close", None)
        if callable(close_fn):
            await close_fn()


# ── 公告例行性过滤 ──────────────────────────────────────────────────────

_ROUTINE_TITLE_PATTERNS = [
    # 股东会相关
    "股东会通知", "股东会决议", "年度股东会", "临时股东会", "股东大会通知",
    "股东会法律意见", "股东大会决议", "股东大会通知",
    # 董事会/监事会
    "董事会决议", "监事会决议", "董事会换届", "监事会换届",
    "董事会第", "监事会第",  # 董事会第X次会议 / 监事会第X次会议
    "独立董事", "董事候选人", "监事候选人",
    "董事会会议", "监事会会议", "董事会召开",
    # 法律/审计/会计
    "法律意见书", "律师事务所", "会计师事务所",
    "审计报告", "内控报告", "内部控制评价",
    # 章程/制度
    "章程修订", "公司章程", "修改公司章程",
    "公司制度", "管理制度",
    # 募集资金/定增例行报告
    "募集资金使用", "募集资金存放", "募集资金年度",
    # 权益分派
    "权益分派", "利润分配",
    # 投资者关系
    "投资者关系活动", "调研记录", "投资者接待",
    # 其他例行
    "薪酬委员会", "提名委员会", "审计委员会",
    "续聘", "更换会计师事务所",
    "独立董事述职",
    # 担保
    "对外担保进展", "对外担保公告", "为子公司提供担保",
    # 高管变动
    "变更财务总监", "变更董事会秘书", "变更监事",
    "聘任副总经理", "聘任财务总监", "聘任董事会秘书",
]

_MATERIAL_KEYWORDS = [
    "定增", "发行股份", "购买资产", "重大资产重组", "增发",
    "并购", "收购", "要约收购",
    "业绩预告", "业绩快报", "业绩修正",
    "中标", "合同", "订单", "投资协议",
    "退市风险", "撤销退市", "ST", "*ST",
    "立案调查", "行政处罚", "证监会",
    "减持计划", "减持结果", "增持计划", "回购",
]


def _is_routine_announcement(title: str) -> bool:
    """判断是否为无投资价值的例行公告。

    如果标题命中了例行模式且未命中重要关键词 → skip。
    """
    if not title:
        return False
    # 如果包含重要关键词 → 非例行，保留
    for kw in _MATERIAL_KEYWORDS:
        if kw in title:
            return False
    # 检查例行模式
    for pat in _ROUTINE_TITLE_PATTERNS:
        if pat in title:
            return True
    return False


async def _watch_parent(parent_pid: int, interval: float = 5.0) -> None:
    import os as _os
    while True:
        await asyncio.sleep(interval)
        try:
            _os.kill(parent_pid, 0)
        except (ProcessLookupError, PermissionError):
            logging.warning("parent pid %d died, exiting", parent_pid)
            _os._exit(0)


if __name__ == "__main__":
    asyncio.run(async_main())
