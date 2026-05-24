"""Re-export from database_service.streams.services.news_prefilter_adapter.

迁移说明 (Phase 4E, 2026-05-24):
  NewsPreFilterAdapter 的主代码已迁移至:
    database_service.streams.services.news_prefilter_adapter

  本文件保留为 re-export wrapper，避免修改所有现有 import。
  新引用请直接使用 database_service 版本:
    from database_service.streams.services.news_prefilter_adapter import (
        NewsPreFilterAdapter,
        NewsTriageResult,
    )
"""
from __future__ import annotations

from database_service.streams.services.news_prefilter_adapter import (  # noqa: F401
    NewsPreFilterAdapter,
    NewsTriageResult,
    _resolve_qwen_model,
)
