from __future__ import annotations

from typing import Any

from .phase0_harness_types import P2Phase0RunContext, RawNewsEnvelope


def build_raw_news_envelopes(
    samples: list[dict[str, Any]], run_ctx: P2Phase0RunContext
) -> list[RawNewsEnvelope]:
    envelopes: list[RawNewsEnvelope] = []
    for idx, sample in enumerate(samples, start=1):
        raw_news_id = str(sample.get("news_id") or sample.get("id") or f"{run_ctx.run_id}-{idx}")
        trace_id = f"{run_ctx.trace_prefix}:{run_ctx.run_id}:{idx}"
        payload = {
            "news_id": raw_news_id,
            "title": sample.get("title", ""),
            "content": sample.get("content") or sample.get("summary", ""),
            "source": sample.get("source", "validation_dataset"),
            "publish_date": sample.get("publish_date") or sample.get("date"),
            "test_flag": run_ctx.test_flag,
            "run_id": run_ctx.run_id,
            "trace_id": trace_id,
            "source_tag": run_ctx.source_tag,
        }
        envelopes.append(RawNewsEnvelope(raw_news_id=raw_news_id, trace_id=trace_id, payload=payload))
    return envelopes

