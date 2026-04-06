from __future__ import annotations

import asyncio
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "theme_service"))

from database_service.config import DatabaseConfig, DatabaseType, init_config
from database_service.gateway import DatabaseGateway, get_gateway
from theme_service.services.theme_service import ThemeService


DATASET_PATH = PROJECT_ROOT / "structured_events_with_gt.jsonl"
DETAIL_OUT = PROJECT_ROOT / "tmp/runtime_theme_match_detail_100.json"
METRICS_OUT = PROJECT_ROOT / "tmp/runtime_theme_match_metrics_100.json"
FILTER_GT_SUBJECT_KEY = os.getenv("FILTER_GT_SUBJECT_KEY", "").strip()


def _load_dataset() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in DATASET_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        if FILTER_GT_SUBJECT_KEY and str(obj.get("gt_subject_key") or "") != FILTER_GT_SUBJECT_KEY:
            continue
        rows.append(obj)
    return rows


def _build_event_row(obj: Dict[str, Any], idx: int) -> Dict[str, Any]:
    return {
        "event_id": idx,
        "news_id": idx,
        # Do not leak ground-truth theme labels into runtime matching input.
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

    rows = _load_dataset()
    details: List[Dict[str, Any]] = []
    group_stats = defaultdict(
        lambda: {
            "gt_subject_key": "",
            "gt_theme_name": "",
            "total": 0,
            "top1_hit": 0,
            "top3_hit": 0,
            "top5_hit": 0,
            "pred_counter": Counter(),
            "confusion_counter": Counter(),
        }
    )
    top1 = top3 = top5 = 0

    try:
        total = len(rows)
        for idx, obj in enumerate(rows, start=1):
            event_row = _build_event_row(obj, idx)
            result = await service.match_event(event_row)

            gt_key = str(obj.get("gt_subject_key") or "")
            gt_theme_name = str(obj.get("theme_name") or "")
            top_candidates = (result.get("audit") or {}).get("top_candidates") or []
            candidate_keys = [str(c.get("subject_key") or "") for c in top_candidates]
            pred_key = str(result.get("matched_subject_key") or "")

            is_top1 = pred_key == gt_key
            is_top3 = gt_key in candidate_keys[:3] if gt_key else False
            is_top5 = gt_key in candidate_keys[:5] if gt_key else False

            top1 += 1 if is_top1 else 0
            top3 += 1 if is_top3 else 0
            top5 += 1 if is_top5 else 0

            gs = group_stats[gt_key]
            gs["gt_subject_key"] = gt_key
            gs["gt_theme_name"] = gt_theme_name
            gs["total"] += 1
            gs["top1_hit"] += 1 if is_top1 else 0
            gs["top3_hit"] += 1 if is_top3 else 0
            gs["top5_hit"] += 1 if is_top5 else 0
            if pred_key:
                gs["pred_counter"][pred_key] += 1
                if pred_key != gt_key:
                    gs["confusion_counter"][pred_key] += 1

            details.append(
                {
                    "index": idx,
                    "event_id": obj.get("event_id"),
                    "gt_subject_key": gt_key,
                    "gt_theme_name": gt_theme_name,
                    "decision": result.get("decision"),
                    "matched_subject_key": pred_key,
                    "matched_theme_name": result.get("matched_theme_name"),
                    "matched_theme_id": result.get("matched_theme_id"),
                    "confidence": result.get("confidence"),
                    "reason_code": result.get("reason_code"),
                    "top_candidates": top_candidates,
                    "top1_hit": is_top1,
                    "top3_hit": is_top3,
                    "top5_hit": is_top5,
                }
            )
            print(
                f"[{idx}/{total}] event_id={obj.get('event_id')} "
                f"decision={result.get('decision')} pred={pred_key or 'NONE'} "
                f"top1={top1/idx:.4f}",
                flush=True,
            )

        per_theme_metrics: List[Dict[str, Any]] = []
        for gt_key, gs in group_stats.items():
            total_n = gs["total"]
            pred_counter = gs["pred_counter"]
            confusion_counter = gs["confusion_counter"]
            most_common_pred = ""
            most_common_pred_count = 0
            if pred_counter:
                most_common_pred, most_common_pred_count = pred_counter.most_common(1)[0]
            confusion_top3 = [
                {"pred_subject_key": pred_key, "count": cnt}
                for pred_key, cnt in confusion_counter.most_common(3)
            ]
            per_theme_metrics.append(
                {
                    "gt_subject_key": gt_key,
                    "gt_theme_name": gs["gt_theme_name"],
                    "total": total_n,
                    "top1_hit": gs["top1_hit"],
                    "top3_hit": gs["top3_hit"],
                    "top5_hit": gs["top5_hit"],
                    "top1_accuracy": round(gs["top1_hit"] / total_n, 4) if total_n else 0.0,
                    "top3_accuracy": round(gs["top3_hit"] / total_n, 4) if total_n else 0.0,
                    "top5_accuracy": round(gs["top5_hit"] / total_n, 4) if total_n else 0.0,
                    "most_common_top1_pred": most_common_pred,
                    "most_common_top1_pred_count": most_common_pred_count,
                    "confusion_top3": confusion_top3,
                }
            )

        per_theme_metrics.sort(key=lambda x: (-x["total"], x["gt_subject_key"]))
        metrics = {
            "events": len(rows),
            "processed": len(details),
            "top1_accuracy": round(top1 / len(details), 4) if details else 0.0,
            "top3_accuracy": round(top3 / len(details), 4) if details else 0.0,
            "top5_accuracy": round(top5 / len(details), 4) if details else 0.0,
            "per_theme_metrics": per_theme_metrics,
        }

        DETAIL_OUT.write_text(json.dumps(details, ensure_ascii=False, indent=2), encoding="utf-8")
        METRICS_OUT.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(metrics, ensure_ascii=False, indent=2), flush=True)

    finally:
        if hasattr(gateway, "close"):
            await gateway.close()


if __name__ == "__main__":
    asyncio.run(main())
