from __future__ import annotations

from typing import Any

from .phase0_harness_types import P2Phase0RunContext


PHASE0_STREAMS_AND_GROUPS = [
    ("stream:news:raw", "news_storage_handlers"),
    ("stream:events:structured", "theme_processors_v2"),
    ("stream:events:decision", "decision_executors"),
    ("stream:events:pending", "clustering_workers"),
]


async def ensure_streams_and_groups(redis_client: Any) -> None:
    for stream_name, group_name in PHASE0_STREAMS_AND_GROUPS:
        try:
            await redis_client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        except Exception as exc:  # pragma: no cover - depends on live redis
            if "BUSYGROUP" not in str(exc):
                raise


async def prepare_phase0_runtime(redis_client: Any, run_ctx: P2Phase0RunContext) -> dict[str, Any]:
    await ensure_streams_and_groups(redis_client)
    return {"run_id": run_ctx.run_id, "streams": [item[0] for item in PHASE0_STREAMS_AND_GROUPS]}


async def cleanup_phase0_run(_redis_client: Any, _run_ctx: P2Phase0RunContext) -> None:
    # Intentionally conservative: phase0 cleanup strategy will be filled
    # after handlers and persistence protocol are finalized.
    return None

