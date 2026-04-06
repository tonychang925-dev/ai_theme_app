import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import asyncpg

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway, get_gateway
from theme_service.services.theme_service import ThemeService


EXPECTED_SUBJECT_KEY = "9030409"
RAW_PATH = Path("/Users/admin/Desktop/ai_theme_app/evaluate_service/data/raw/test_cases.txt")
OUT_PATH = Path("/Users/admin/Desktop/ai_theme_app/tmp/p2_phase0_theme_match_engine_30_from_test_cases.preview.json")


def _pg_kwargs():
    return {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "postgres"),
        "password": os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
        "database": os.getenv("POSTGRES_DATABASE", "stock_data_test"),
    }


def _load_first_30_ai_ar_raws():
    text = RAW_PATH.read_text(encoding="utf-8")
    match = re.search(r"测试集1:题材名称:AI/AR眼镜\n(.*?)(?:\n测试集2:题材名称:|\Z)", text, re.S)
    assert match, "未找到 AI/AR眼镜 测试段"
    block = match.group(1)
    rows = []
    for line in block.splitlines():
        value = line.strip()
        if not value.startswith("- "):
            continue
        value = value[2:].strip()
        if value:
            rows.append(value)
    assert len(rows) >= 30, f"AI/AR眼镜 原始样本不足 30 条，当前 {len(rows)}"
    return rows[:30]


async def main():
    cfg = DatabaseConfig(
        db_type=DatabaseType.POSTGRESQL,
        postgres_host=os.getenv("POSTGRES_HOST", "localhost"),
        postgres_port=int(os.getenv("POSTGRES_PORT", "5432")),
        postgres_database=os.getenv("POSTGRES_DATABASE", "stock_data_test"),
        postgres_username=os.getenv("POSTGRES_USER", "postgres"),
        postgres_password=os.getenv("POSTGRES_PASSWORD", "zxbzj~925"),
    )
    cfg.redis.enabled = False
    init_config(cfg)
    DatabaseGateway._instance = None

    gateway = await get_gateway()
    service = ThemeService()
    service.set_database_gateway(gateway)

    conn = await asyncpg.connect(**_pg_kwargs())
    created_event_ids = []
    created_news_ids = []
    preview = []

    try:
        raws = _load_first_30_ai_ar_raws()
        for idx, raw in enumerate(raws, start=1):
            external_news_id = f"tc30_ai_ar_{idx}_{uuid.uuid4().hex[:8]}"
            title = "AI/AR眼镜相关新闻"
            news_data = {
                "news_id": external_news_id,
                "title": title,
                "content": raw,
                "source": "pytest_p2_phase0_theme_match_engine_30",
                "publish_date": "2026-03-01",
                "metadata": {
                    "source_case_index": idx,
                    "ground_truth_theme": "AI/AR眼镜",
                },
            }
            await gateway.create_news(news_data)
            news_row = await gateway.get_news(external_news_id)
            created_news_ids.append(int(news_row["id"]))

            summary = raw[:180]
            event_payload = {
                "news_id": int(news_row["id"]),
                "event_type": "行业新闻",
                "impact_industries": ["AI/AR眼镜"],
                "direction": "利好",
                "confidence": 0.95,
                "summary": summary,
                "theme_directive": {},
                "theme_directive_processed": False,
                "severity_score": 0.8,
                "source_weight": 1.0,
                "event_time": "2026-03-01 00:00:00",
                "entities": [],
                "causal_claim": [summary] if summary else [],
                "evidence_set": {"core_concepts": ["AI眼镜", "AR眼镜", "智能眼镜"]},
                "raw_event_json": {
                    "title": title,
                    "content": raw,
                    "source_case_index": idx,
                    "ground_truth_theme": "AI/AR眼镜",
                },
            }
            event_id = await gateway.create_news_event(event_payload)
            created_event_ids.append(int(event_id))

            event_row = await gateway.get_news_event_for_match(int(event_id))
            result = await service.match_event(event_row)
            preview.append(
                {
                    "case_index": idx,
                    "event_id": int(event_id),
                    "decision": result["decision"],
                    "matched_subject_key": result.get("matched_subject_key"),
                    "matched_theme_name": result.get("matched_theme_name"),
                    "confidence": result.get("confidence"),
                    "reason_code": result.get("reason_code"),
                    "top1_hit": str(result.get("matched_subject_key")) == EXPECTED_SUBJECT_KEY,
                    "raw_text": raw,
                }
            )

        OUT_PATH.write_text(json.dumps(preview, ensure_ascii=False, indent=2), encoding="utf-8")
        hits = sum(1 for row in preview if row["top1_hit"])
        print(
            json.dumps(
                {
                    "events": len(preview),
                    "top1_hits": hits,
                    "top1_accuracy": hits / len(preview) if preview else 0.0,
                    "preview_path": str(OUT_PATH),
                },
                ensure_ascii=False,
            )
        )
    finally:
        try:
            if created_event_ids:
                await conn.execute("DELETE FROM news_event WHERE id = ANY($1::int[])", created_event_ids)
            if created_news_ids:
                await conn.execute("DELETE FROM news_raw WHERE id = ANY($1::int[])", created_news_ids)
        finally:
            await conn.close()
            if hasattr(gateway, "close"):
                await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
