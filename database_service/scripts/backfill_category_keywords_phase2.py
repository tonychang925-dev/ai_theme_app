"""
P1.phase2 T06: 回填 financial_categories.keywords

规则:
- L2 keywords <- theme_master(tags.keywords by category2_code)
- L1 keywords <- aggregated child L2 keywords
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
service_dir = os.path.dirname(current_dir)
project_root = os.path.dirname(service_dir)
sys.path.insert(0, project_root)
sys.path.insert(0, service_dir)

from database_service.gateway import DatabaseGateway
from database_service.streams.gateway_integration import get_gateway
from theme_service.services.category_keyword_backfill import build_category_keyword_backfill


async def main(dry_run: bool = True) -> int:
    # 复用现有集成测试链路：StreamEnhancedGateway -> base_gateway
    gateway = await get_gateway(enable_retry=True, retry_config={"max_retries": 1})
    base_gateway = getattr(gateway, "base_gateway", None)
    if base_gateway is None:
        # 降级：沿用统一网关入口，避免stream初始化失败导致脚本不可用
        base_gateway = await DatabaseGateway.get_instance()

    categories = await base_gateway.load_all_categories()
    themes = await base_gateway.get_all_active_themes(limit=50000)
    result = build_category_keyword_backfill(categories, themes)

    print("=" * 80)
    print("P1.phase2 T06 分类关键词回填")
    print(f"时间: {datetime.now().isoformat(timespec='seconds')}")
    print(f"分类数: {len(categories)}  题材数: {len(themes)}")
    print(f"拟更新分类数: {len(result.updates)}")
    print("覆盖率指标:")
    print(json.dumps(result.metrics, ensure_ascii=False, indent=2))
    print("=" * 80)

    if dry_run:
        print("dry-run 模式：未写入数据库")
        return 0

    if not result.updates:
        print("无更新，结束")
        return 0

    if not hasattr(base_gateway, "_client") or not hasattr(base_gateway._client, "pool"):
        raise RuntimeError("当前数据库客户端不支持直接连接池写入")

    async with base_gateway._client.pool.acquire() as conn:
        async with conn.transaction():
            for code, keywords in result.updates.items():
                await conn.execute(
                    """
                    UPDATE financial_categories
                    SET keywords = $1::text[], updated_at = NOW()
                    WHERE category_code = $2
                    """,
                    keywords,
                    code,
                )

    print("写入完成")
    return 0


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    raise SystemExit(asyncio.run(main(dry_run=dry_run)))
