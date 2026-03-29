#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from text2vec import SentenceModel

from dense_recall_common import dense_top1

import os
print("[DEBUG gate_eval.py]", os.path.abspath(__file__))

def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return str(text).strip()


def safe_json_loads(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def flatten_text_items(value: Any) -> List[str]:
    out: List[str] = []

    def _walk(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            s = normalize_text(x)
            if s:
                out.append(s)
            return
        if isinstance(x, (int, float, bool)):
            out.append(str(x))
            return
        if isinstance(x, dict):
            for k in ["name", "term", "text", "label", "value", "title", "normalized"]:
                if k in x:
                    _walk(x[k])
            for _, v in x.items():
                _walk(v)
            return
        if isinstance(x, (list, tuple)):
            for y in x:
                _walk(y)

    _walk(value)

    dedup = []
    seen = set()
    for x in out:
        if x not in seen:
            seen.add(x)
            dedup.append(x)
    return dedup


def build_event_query_text(event: Dict[str, Any]) -> str:
    parts: List[str] = []

    for key in ["title", "summary", "content", "text", "event_text", "raw_text"]:
        v = normalize_text(event.get(key))
        if v:
            parts.append(v)

    event_type = normalize_text(event.get("event_type"))
    if event_type:
        parts.append(f"事件类型：{event_type}")

    entities = event.get("entities")
    if isinstance(entities, list):
        vals = []
        for x in entities:
            if isinstance(x, dict):
                name = normalize_text(x.get("normalized") or x.get("name"))
                if name:
                    vals.append(name)
            else:
                s = normalize_text(x)
                if s:
                    vals.append(s)
        if vals:
            parts.append("实体：" + "，".join(vals[:20]))

    causal_claim = event.get("causal_claim")
    if isinstance(causal_claim, list):
        vals = [normalize_text(x) for x in causal_claim if normalize_text(x)]
        if vals:
            parts.append("因果主张：" + "；".join(vals[:10]))

    evidence_set = event.get("evidence_set")
    if isinstance(evidence_set, dict):
        core_concepts = evidence_set.get("core_concepts")
        if isinstance(core_concepts, list):
            vals = [normalize_text(x) for x in core_concepts if normalize_text(x)]
            if vals:
                parts.append("核心概念：" + "，".join(vals[:10]))

        tech_phrases = evidence_set.get("tech_phrases")
        if isinstance(tech_phrases, list):
            vals = [normalize_text(x) for x in tech_phrases if normalize_text(x)]
            if vals:
                parts.append("技术短语：" + "，".join(vals[:10]))

    return "\n".join(parts).strip()


def token_hit_terms(text: str, terms: List[str]) -> List[str]:
    text = normalize_text(text)
    hits = []
    for t in terms:
        t = normalize_text(t)
        if not t:
            continue
        if t in text:
            hits.append(t)
    return hits


def load_gate_profile(conn, subject_key: str) -> Optional[Dict[str, Any]]:
    sql = """
    select
        subject_key,
        gate_json,
        must_terms,
        should_terms,
        not_terms,
        strong_terms,
        weak_terms,
        negative_terms,
        search_text,
        quality
    from theme_gate_profile
    where subject_key = %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (subject_key,))
        row = cur.fetchone()
        return dict(row) if row else None


def gate_decide(event_text: str, gate_row: Dict[str, Any]) -> Dict[str, Any]:
    must_terms = flatten_text_items(gate_row.get("must_terms"))
    strong_terms = flatten_text_items(gate_row.get("strong_terms"))
    should_terms = flatten_text_items(gate_row.get("should_terms"))
    not_terms = flatten_text_items(gate_row.get("not_terms"))
    negative_terms = flatten_text_items(gate_row.get("negative_terms"))

    must_hits = token_hit_terms(event_text, must_terms)
    strong_hits = token_hit_terms(event_text, strong_terms)
    should_hits = token_hit_terms(event_text, should_terms)
    not_hits = token_hit_terms(event_text, not_terms)
    negative_hits = token_hit_terms(event_text, negative_terms)

    must_hit_count = len(must_hits)
    strong_hit_count = len(strong_hits)
    should_hit_count = len(should_hits)
    not_hit_count = len(not_hits)
    negative_hit_count = len(negative_hits)

    positive_score = must_hit_count * 3 + strong_hit_count * 2 + should_hit_count
    negative_score = not_hit_count * 2 + negative_hit_count

    if must_hit_count >= 1:
        verdict = "review" if negative_score >= 4 else "accept"
    elif strong_hit_count >= 2:
        verdict = "review" if negative_score >= 4 else "accept"
    elif strong_hit_count >= 1 and should_hit_count >= 1:
        verdict = "review" if negative_score >= 3 else "accept"
    elif strong_hit_count >= 1:
        verdict = "review"
    elif should_hit_count >= 2:
        verdict = "reject" if negative_score >= 3 else "review"
    elif should_hit_count == 1:
        verdict = "reject" if negative_score >= 2 else "review"
    else:
        verdict = "reject" if negative_score >= 1 else "review"

    return {
        "verdict": verdict,
        "positive_score": positive_score,
        "negative_score": negative_score,
        "must_hit_count": must_hit_count,
        "strong_hit_count": strong_hit_count,
        "should_hit_count": should_hit_count,
        "not_hit_count": not_hit_count,
        "negative_hit_count": negative_hit_count,
        "must_hits": must_hits,
        "strong_hits": strong_hits,
        "should_hits": should_hits,
        "not_hits": not_hits,
        "negative_hits": negative_hits,
    }


def evaluate(conn, model: SentenceModel, events_path: str, print_failures: int = 20) -> None:
    total = 0
    dense_top1_correct = 0
    gate_accept_correct = 0
    gate_accept_total = 0
    gate_review_total = 0
    gate_reject_total = 0

    failures = []

    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            event = safe_json_loads(line)
            if not event:
                continue

            gt_subject_key = normalize_text(event.get("gt_subject_key"))
            if not gt_subject_key:
                continue

            query_text = build_event_query_text(event)
            if not query_text:
                continue

            total += 1

            top1 = dense_top1(conn, query_text, model)
            if not top1:
                failures.append({
                    "event_id": event.get("event_id"),
                    "reason": "dense_top1 empty",
                })
                continue

            pred_subject_key = normalize_text(top1["subject_key"])
            dense_correct = (pred_subject_key == gt_subject_key)
            if dense_correct:
                dense_top1_correct += 1

            gate_row = load_gate_profile(conn, pred_subject_key)
            if not gate_row:
                failures.append({
                    "event_id": event.get("event_id"),
                    "gt_subject_key": gt_subject_key,
                    "pred_subject_key": pred_subject_key,
                    "reason": "gate profile missing",
                })
                continue

            gate_result = gate_decide(query_text, gate_row)
            verdict = gate_result["verdict"]

            if verdict == "accept":
                gate_accept_total += 1
                if dense_correct:
                    gate_accept_correct += 1
            elif verdict == "review":
                gate_review_total += 1
            else:
                gate_reject_total += 1

            if total % 20 == 0:
                print(
                    f"[INFO] 已评估 {total} 条 | "
                    f"dense_top1_acc={dense_top1_correct/total:.4f} | "
                    f"accept_rate={gate_accept_total/total:.4f} | "
                    f"review_rate={gate_review_total/total:.4f} | "
                    f"reject_rate={gate_reject_total/total:.4f}"
                )

            if verdict != "accept" or not dense_correct:
                failures.append({
                    "event_id": event.get("event_id"),
                    "summary": event.get("summary"),
                    "gt_subject_key": gt_subject_key,
                    "pred_subject_key": pred_subject_key,
                    "dense_score": top1.get("score"),
                    "gate_verdict": verdict,
                    "gate_result": gate_result,
                })

    print("\n" + "=" * 100)
    print(f"[DONE] 总样本数: {total}")
    if total > 0:
        print(f"dense_top1_accuracy:   {dense_top1_correct/total:.4f}")
        print(f"gate_accept_rate:      {gate_accept_total/total:.4f}")
        print(f"gate_review_rate:      {gate_review_total/total:.4f}")
        print(f"gate_reject_rate:      {gate_reject_total/total:.4f}")
        if gate_accept_total > 0:
            print(f"accept_precision:      {gate_accept_correct/gate_accept_total:.4f}")
        else:
            print("accept_precision:      N/A")

    if failures:
        print("\n" + "=" * 100)
        print(f"[部分失败/非accept样本，最多展示 {print_failures} 条]")
        for item in failures[:print_failures]:
            print(json.dumps(item, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="Dense Top1 + Gate Eval")
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--model-name", default="shibing624/text2vec-base-chinese")
    args = parser.parse_args()

    print("[INFO] 加载模型...")
    model = SentenceModel(args.model_name)

    print("[INFO] 连接数据库...")
    conn = psycopg2.connect(args.db_dsn)

    try:
        evaluate(conn, model, args.events)
    finally:
        conn.close()


if __name__ == "__main__":
    main()