"""P1-D: PDF 正文批量解析脚本。"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from stock_processing_service.application.services.pdf_content_extractor import (
    PdfContentExtractor,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Parse raw_intel_document PDFs to content_text.")
    parser.add_argument("--db-name", default=None)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--high-value-only", action="store_true", default=True)
    parser.add_argument("--all", dest="high_value_only", action="store_false")
    parser.add_argument("--once", action="store_true", default=True)
    parser.add_argument("--max-pdf-mb", type=int, default=20)
    parser.add_argument("--pdf-cache-dir", default="data/intel_pdfs")
    parser.add_argument("--max-content-chars", type=int, default=12000)
    return parser


async def async_main() -> None:
    args = build_parser().parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db_name = args.db_name or os.environ.get("PG_DATABASE", "stock_data_test")
    os.environ.setdefault("PG_DATABASE", db_name)
    os.environ.setdefault("DB_TYPE", "postgresql")

    from database_service.gateway import DatabaseGateway
    from database_service.config import DatabaseConfig, DatabaseType

    cfg = DatabaseConfig(db_type=DatabaseType.POSTGRESQL, postgres_database=db_name)
    gateway = await DatabaseGateway.initialize(config=cfg, auto_warm_cache=False)

    extractor = PdfContentExtractor(
        cache_dir=args.pdf_cache_dir,
        max_pdf_mb=args.max_pdf_mb,
        max_content_chars=args.max_content_chars,
    )

    docs = await gateway.get_raw_intel_for_pdf_parse(
        limit=args.limit, high_value_only=args.high_value_only,
    )
    logging.info("Fetched %s docs for PDF parse (high_value_only=%s)", len(docs), args.high_value_only)

    stats = {"total": len(docs), "parsed": 0, "download_failed": 0, "parse_failed": 0, "skipped": 0}
    for doc in docs:
        result = extractor.process(doc)
        await gateway.update_raw_intel_content_text(
            doc["id"],
            content_text=result["content_text"],
            pdf_path=result.get("pdf_path"),
            parse_status=result["parse_status"],
            parse_error=result.get("parse_error"),
            parse_method=result.get("parse_method"),
        )
        status = result["parse_status"]
        stats[status] = stats.get(status, 0) + 1
        if status == "parsed":
            logging.info(
                "✅ doc_id=%s method=%s chars=%s title=%.60s",
                result["doc_id"], result.get("parse_method"), len(result["content_text"]), str(doc.get("title", ""))[:60],
            )
        else:
            logging.warning("❌ doc_id=%s status=%s error=%s", result["doc_id"], status, result.get("parse_error"))

    logging.info("Done: %s", stats)
    await gateway.close()


if __name__ == "__main__":
    asyncio.run(async_main())
