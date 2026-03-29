#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
from pathlib import Path
from typing import Any, Dict, List


def safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x).strip()


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def unique_keep_order(items: List[str]) -> List[str]:
    out = []
    seen = set()
    for x in items:
        s = safe_str(x)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def load_events_jsonl(path: str) -> List[Dict[str, Any]]:
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = safe_str(line)
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def build_subject_events_map(events_path: str) -> Dict[str, List[Dict[str, Any]]]:
    rows = load_events_jsonl(events_path)
    out: Dict[str, List[Dict[str, Any]]] = {}

    for obj in rows:
        gt_subject_key = safe_str(obj.get("gt_subject_key"))
        if not gt_subject_key:
            continue

        evidence_set = obj.get("evidence_set") or {}

        title = safe_str(obj.get("title") or obj.get("summary") or obj.get("theme_name"))
        summary = safe_str(obj.get("summary") or obj.get("raw_text"))
        date_hint = safe_str(obj.get("date_hint") or obj.get("date") or obj.get("publish_time"))

        entities = []
        for e in obj.get("entities") or []:
            if isinstance(e, dict):
                name = safe_str(e.get("normalized") or e.get("name"))
            else:
                name = safe_str(e)
            if name:
                entities.append(name)

        event_row = {
            "event_id": safe_str(obj.get("event_id")),
            "date": date_hint,
            "title": title,
            "summary": summary,
            "event_type": safe_str(obj.get("event_type")),
            "entities": unique_keep_order(entities),
            "core_concepts": unique_keep_order(evidence_set.get("core_concepts") or []),
            "tech_phrases": unique_keep_order(evidence_set.get("tech_phrases") or []),
        }

        out.setdefault(gt_subject_key, []).append(event_row)

    return out


def load_stage1_results(path: str) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_stock_profile_json(path: str) -> Dict[str, Dict[str, Any]]:
    """
    可先用 json 过渡。
    结构：
    {
      "688070": {
        "profile_text": "...",
        "remark": "...",
        "detail_html_text": "...",
        "lightspots": ["...", "..."]
      }
    }
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def choose_best_direction(root_stock: Dict[str, Any], root_subject_key: str, root_subject_name: str) -> Dict[str, str]:
    matched_directions = root_stock.get("matched_directions") or []
    if matched_directions:
        best = sorted(
            matched_directions,
            key=lambda x: safe_float(x.get("score")),
            reverse=True
        )[0]
        return {
            "direction_subject_key": safe_str(best.get("subject_key")) or root_subject_key,
            "direction_subject_name": safe_str(best.get("subject_name")) or root_subject_name,
        }

    return {
        "direction_subject_key": root_subject_key,
        "direction_subject_name": root_subject_name,
    }


def build_stage2_inputs(
    stage1_path: str,
    events_path: str,
    stock_profile_path: str,
    out_path: str,
    run_id: str,
) -> None:
    stage1_rows = load_stage1_results(stage1_path)
    subject_events_map = build_subject_events_map(events_path)
    stock_profile_map = load_stock_profile_json(stock_profile_path)

    outputs: List[Dict[str, Any]] = []

    for event_block in stage1_rows:
        event_id = safe_str(event_block.get("event_id"))
        root_theme_candidates = event_block.get("root_theme_candidates") or []

        for root in root_theme_candidates:
            root_subject_key = safe_str(root.get("root_subject_key"))
            root_subject_name = safe_str(root.get("root_subject_name"))
            directions = root.get("directions") or []
            root_stocks = root.get("root_stocks") or []

            # 为 direction 建索引，便于补 aliases/component_words/reason
            direction_map = {}
            for d in directions:
                direction_map[safe_str(d.get("subject_key"))] = {
                    "subject_name": safe_str(d.get("subject_name")),
                    "aliases": d.get("aliases") or [],
                    "keywords": d.get("keywords") or [],
                    "component_words": d.get("component_words") or [],
                    "reason": safe_str(d.get("reason")),
                }

            event_list = subject_events_map.get(root_subject_key, [])

            for stock in root_stocks:
                stock_id = safe_str(stock.get("stock_id"))
                stock_name = safe_str(stock.get("stock_name"))

                best_direction = choose_best_direction(stock, root_subject_key, root_subject_name)
                direction_subject_key = best_direction["direction_subject_key"]
                direction_subject_name = best_direction["direction_subject_name"]

                dmeta = direction_map.get(direction_subject_key, {})
                sp = stock_profile_map.get(stock_id, {})

                evidence_json = stock.get("evidence_json") or {}
                stage1_confidence = ""
                if isinstance(evidence_json, dict):
                    audit = evidence_json.get("audit") or {}
                    # 兼容不同版本输出
                    stage1_confidence = (
                        safe_str(audit.get("confidence_level"))
                        or safe_str(stock.get("confidence_level"))
                    )

                outputs.append(
                    {
                        "run_id": run_id,
                        "event_id": event_id,
                        "root_subject_key": root_subject_key,
                        "root_subject_name": root_subject_name,
                        "direction_subject_key": direction_subject_key,
                        "direction_subject_name": direction_subject_name,
                        "subject_reason": safe_str(dmeta.get("reason")),
                        "aliases": dmeta.get("aliases", []),
                        "component_words": dmeta.get("component_words", []),
                        "event_list": event_list,
                        "stock_id": stock_id,
                        "stock_name": stock_name,
                        "profile_text": safe_str(sp.get("profile_text")),
                        "remark": safe_str(sp.get("remark")),
                        "lightspots": sp.get("lightspots", []),
                        "detail_html_text": safe_str(sp.get("detail_html_text")),
                        "stage1_score": safe_float(stock.get("root_score")),
                        "stage1_confidence": stage1_confidence,
                        "stage1_gate_reason": safe_str(stock.get("gate_reason")),
                    }
                )

    Path(out_path).write_text(
        json.dumps(outputs, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"[DONE] wrote: {out_path}")


if __name__ == "__main__":
    build_stage2_inputs(
        stage1_path="root_stock_stage1_candidates_one.json",
        events_path="structured_events_with_gt.jsonl",
        stock_profile_path="stock_profile_snapshot.json",
        out_path="stage2_inputs_satcom.json",
        run_id="2026-03-28_satcom_test_001",
    )