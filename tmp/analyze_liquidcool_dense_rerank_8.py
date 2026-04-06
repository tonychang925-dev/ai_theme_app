from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway, get_gateway
from theme_service.services.theme_service import ThemeService
from theme_service.services.theme_match_engine import (
    _build_feature_recall_rows,
    _compute_dynamic_topk,
    _inject_direct_hit_candidates,
    _collect_direct_hit_subject_keys,
    _merge_recall_rows,
    _rrf_merge_rows,
)


DATASET_PATH = PROJECT_ROOT / "structured_events_with_gt.jsonl"
GT_SUBJECT_KEY = os.getenv("GT_SUBJECT_KEY", "9024880")
DETAIL_OUT = PROJECT_ROOT / f"tmp/liquidcool_dense_rerank_{GT_SUBJECT_KEY}.detail.json"
METRICS_OUT = PROJECT_ROOT / f"tmp/liquidcool_dense_rerank_{GT_SUBJECT_KEY}.metrics.json"


def _load_dataset() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in DATASET_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if str(obj.get("gt_subject_key") or "") == GT_SUBJECT_KEY:
            rows.append(obj)
    return rows


def _build_event_row(obj: Dict[str, Any], idx: int) -> Dict[str, Any]:
    return {
        "event_id": idx,
        "news_id": idx,
        "title": "",
        "content": obj.get("raw_text") or "",
        "summary": obj.get("summary") or "",
        "event_type": obj.get("event_type") or "",
        "entities": obj.get("entities") or [],
        "causal_claim": obj.get("causal_claim") or [],
        "evidence_set": obj.get("evidence_set") or {},
        "raw_event_json": obj,
        "trace_id": obj.get("event_id") or f"evt_{idx}",
    }


def _summarize_rank(values: List[int]) -> Dict[str, int]:
    return {str(k): values.count(k) for k in sorted(set(values))}


async def main() -> None:
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
    engine = service.theme_match_engine
    rows = _load_dataset()
    profiles = await engine.profile_repository.load_active_profiles()
    profile_map = {p.subject_key: p for p in profiles}

    details: List[Dict[str, Any]] = []
    dense_in = 0
    dense_top1 = 0
    dense_ranks: List[int] = []
    sparse_in = 0
    sparse_top1 = 0
    sparse_ranks: List[int] = []
    merged_in = 0
    merged_top1 = 0
    merged_ranks: List[int] = []
    rerank_in = 0
    rerank_top1 = 0
    rerank_ranks: List[int] = []
    reserve_in = 0
    reserve_top1 = 0
    reserve_ranks: List[int] = []
    llm_in = 0
    llm_top1 = 0
    llm_ranks: List[int] = []
    llm_match = 0
    llm_review = 0
    llm_unknown = 0

    try:
        total = len(rows)
        for idx, obj in enumerate(rows, start=1):
            request = service.build_theme_match_request(_build_event_row(obj, idx))
            dense_rows = await engine._dense_recall(request)
            dense_keys = [str(r.get("subject_key") or "") for r in dense_rows]
            sparse_rows = await engine._sparse_recall(request)
            sparse_keys = [str(r.get("subject_key") or "") for r in sparse_rows]
            hybrid_rows = _rrf_merge_rows(dense_rows, sparse_rows)
            feature_rows = _build_feature_recall_rows(request, profile_map)
            merged_rows = _merge_recall_rows(hybrid_rows, feature_rows)
            merged_keys = [str(r.get("subject_key") or "") for r in merged_rows]
            reranked_rows = engine._rerank(request, merged_rows, profile_map)
            rerank_keys = [str(r.get("subject_key") or "") for r in reranked_rows]
            dynamic_topk = _compute_dynamic_topk(reranked_rows)
            direct_hit_keys = _collect_direct_hit_subject_keys(request, profile_map)
            final_rows = _inject_direct_hit_candidates(
                reranked_rows,
                direct_hit_keys,
                profile_map,
                final_topk=dynamic_topk,
                max_inject=2,
            )
            final_keys = [str(r.get("subject_key") or "") for r in final_rows]
            candidates = engine._materialize_candidates(final_rows, profile_map)
            llm_result = None
            llm_envelope = None
            llm_rank = None
            if candidates and engine._judge.enabled():
                llm_result = engine._judge.judge(request, candidates, profile_map)
                llm_envelope = engine._final_decide_with_llm(request, candidates, profile_map, llm_result)
                matched_key = str(llm_envelope.matched_subject_key or "")
                if matched_key == GT_SUBJECT_KEY:
                    llm_rank = 1

            dense_rank = dense_keys.index(GT_SUBJECT_KEY) + 1 if GT_SUBJECT_KEY in dense_keys else None
            sparse_rank = sparse_keys.index(GT_SUBJECT_KEY) + 1 if GT_SUBJECT_KEY in sparse_keys else None
            merged_rank = merged_keys.index(GT_SUBJECT_KEY) + 1 if GT_SUBJECT_KEY in merged_keys else None
            rerank_rank = rerank_keys.index(GT_SUBJECT_KEY) + 1 if GT_SUBJECT_KEY in rerank_keys else None
            final_rank = final_keys.index(GT_SUBJECT_KEY) + 1 if GT_SUBJECT_KEY in final_keys else None

            if dense_rank is not None:
                dense_in += 1
                dense_ranks.append(dense_rank)
                if dense_rank == 1:
                    dense_top1 += 1

            if sparse_rank is not None:
                sparse_in += 1
                sparse_ranks.append(sparse_rank)
                if sparse_rank == 1:
                    sparse_top1 += 1

            if merged_rank is not None:
                merged_in += 1
                merged_ranks.append(merged_rank)
                if merged_rank == 1:
                    merged_top1 += 1

            if rerank_rank is not None:
                rerank_in += 1
                rerank_ranks.append(rerank_rank)
                if rerank_rank == 1:
                    rerank_top1 += 1

            if final_rank is not None:
                reserve_in += 1
                reserve_ranks.append(final_rank)
                if final_rank == 1:
                    reserve_top1 += 1

            if llm_result is not None:
                if llm_rank is not None:
                    llm_in += 1
                    llm_ranks.append(llm_rank)
                    llm_top1 += 1
                if llm_envelope and llm_envelope.decision == "MATCH":
                    llm_match += 1
                elif llm_envelope and llm_envelope.decision == "HUMAN_REVIEW":
                    llm_review += 1
                elif llm_envelope and llm_envelope.decision == "UNKNOWN":
                    llm_unknown += 1

            details.append(
                {
                    "index": idx,
                    "event_id": obj.get("event_id"),
                    "gt_subject_key": GT_SUBJECT_KEY,
                    "dense_rank": dense_rank,
                    "sparse_rank": sparse_rank,
                    "merged_rank": merged_rank,
                    "rerank_rank": rerank_rank,
                    "final_rank": final_rank,
                    "dynamic_topk": dynamic_topk,
                    "direct_hit_keys": direct_hit_keys,
                    "llm_verdict": llm_result.get("verdict") if llm_result else None,
                    "llm_best_theme_key": llm_result.get("best_theme_key") if llm_result else None,
                    "llm_confidence": llm_result.get("confidence") if llm_result else None,
                    "llm_decision": llm_envelope.decision if llm_envelope else None,
                    "dense_top5": dense_keys[:5],
                    "sparse_top5": sparse_keys[:5],
                    "merged_top5": merged_keys[:5],
                    "rerank_top5": rerank_keys[:5],
                    "final_top5": final_keys[:5],
                }
            )
            print(
                f"[{idx}/{total}] event_id={obj.get('event_id')} "
                f"dense_rank={dense_rank or 'MISS'} sparse_rank={sparse_rank or 'MISS'} "
                f"merged_rank={merged_rank or 'MISS'} "
                f"rerank_rank={rerank_rank or 'MISS'} reserve_rank={final_rank or 'MISS'} "
                f"dynamic_topk={dynamic_topk} "
                f"llm={llm_envelope.matched_subject_key if llm_envelope else '--'}",
                flush=True,
            )

        metrics = {
            "gt_subject_key": GT_SUBJECT_KEY,
            "events": total,
            "dense": {
                "in_candidates": dense_in,
                "candidate_recall": round(dense_in / total, 4) if total else 0.0,
                "top1_hits": dense_top1,
                "top1_recall": round(dense_top1 / total, 4) if total else 0.0,
                "rank_hist": _summarize_rank(dense_ranks),
            },
            "sparse": {
                "in_candidates": sparse_in,
                "candidate_recall": round(sparse_in / total, 4) if total else 0.0,
                "top1_hits": sparse_top1,
                "top1_recall": round(sparse_top1 / total, 4) if total else 0.0,
                "rank_hist": _summarize_rank(sparse_ranks),
            },
            "merged": {
                "in_candidates": merged_in,
                "candidate_recall": round(merged_in / total, 4) if total else 0.0,
                "top1_hits": merged_top1,
                "top1_recall": round(merged_top1 / total, 4) if total else 0.0,
                "rank_hist": _summarize_rank(merged_ranks),
            },
            "rerank": {
                "in_candidates": rerank_in,
                "candidate_recall": round(rerank_in / total, 4) if total else 0.0,
                "top1_hits": rerank_top1,
                "top1_recall": round(rerank_top1 / total, 4) if total else 0.0,
                "rank_hist": _summarize_rank(rerank_ranks),
            },
            "reserve": {
                "in_candidates": reserve_in,
                "candidate_recall": round(reserve_in / total, 4) if total else 0.0,
                "top1_hits": reserve_top1,
                "top1_recall": round(reserve_top1 / total, 4) if total else 0.0,
                "rank_hist": _summarize_rank(reserve_ranks),
            },
            "llm": {
                "top1_hits": llm_top1,
                "top1_recall": round(llm_top1 / total, 4) if total else 0.0,
                "rank_hist": _summarize_rank(llm_ranks),
                "decision_match": llm_match,
                "decision_review": llm_review,
                "decision_unknown": llm_unknown,
            },
        }

        DETAIL_OUT.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
        METRICS_OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metrics, ensure_ascii=False, indent=2))
    finally:
        await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
