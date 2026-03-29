#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from typing import Any, Dict, List, Optional

import psycopg2
import psycopg2.extras
from text2vec import SentenceModel


def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    return str(text).strip()


def safe_json_loads(line: str) -> Optional[Dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    return json.loads(line)


def vector_to_pgvector_literal(vec: List[float]) -> str:
    return "'[" + ",".join(f"{x:.6f}" for x in vec) + "]'::vector"


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


# =========================
# Dense / Rerank
# =========================

def dense_recall(conn, query_text: str, model: SentenceModel, top_k: int) -> List[Dict[str, Any]]:
    query_vec = model.encode(query_text)
    if hasattr(query_vec, "tolist"):
        query_vec = query_vec.tolist()
    query_vec_literal = vector_to_pgvector_literal(query_vec)

    sql = f"""
    select
        t.subject_key,
        t.rerank_text,
        1 - (t.embedding <=> {query_vec_literal}) as dense_score
    from theme_profile_ext t
    where t.embedding is not null
    order by t.embedding <=> {query_vec_literal}
    limit %s
    """

    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (top_k,))
        return list(cur.fetchall())


def rerank_candidates(
    query_text: str,
    candidates: List[Dict[str, Any]],
    model: SentenceModel,
) -> List[Dict[str, Any]]:
    if not candidates:
        return []

    query_vec = model.encode(query_text)
    if hasattr(query_vec, "tolist"):
        query_vec = query_vec.tolist()

    docs = [normalize_text(x.get("rerank_text")) for x in candidates]
    doc_vecs = model.encode(docs)

    reranked = []
    for cand, doc_vec in zip(candidates, doc_vecs):
        if hasattr(doc_vec, "tolist"):
            doc_vec = doc_vec.tolist()

        import math
        dot = sum(a * b for a, b in zip(query_vec, doc_vec))
        qn = math.sqrt(sum(a * a for a in query_vec))
        dn = math.sqrt(sum(a * a for a in doc_vec))
        score = dot / (qn * dn + 1e-12)

        row = dict(cand)
        row["rerank_score"] = score
        reranked.append(row)

    reranked.sort(key=lambda x: (-x["rerank_score"], -x["dense_score"], x["subject_key"]))
    return reranked


# =========================
# Gate
# =========================

def load_gate_profile(conn, subject_key: str) -> Optional[Dict[str, Any]]:
    sql = """
    select
        subject_key,
        concept,
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
    limit 1
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (subject_key,))
        row = cur.fetchone()
        return dict(row) if row else None


def flatten_text_items(value: Any) -> List[str]:
    out: List[str] = []

    def _walk(x: Any):
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

    # 去重负分，避免同一词重复处罚
    unique_negative_hits = list(dict.fromkeys(not_hits + negative_hits))
    negative_score = len(unique_negative_hits)
    positive_score = must_hit_count * 3 + strong_hit_count * 2 + should_hit_count

    if must_hit_count >= 1:
        verdict = "accept" if negative_score <= 2 else "review"
    elif strong_hit_count >= 2:
        verdict = "accept" if negative_score <= 2 else "review"
    elif strong_hit_count >= 1 and should_hit_count >= 1:
        verdict = "accept" if negative_score <= 2 else "review"
    elif strong_hit_count >= 1:
        verdict = "review"
    elif should_hit_count >= 2:
        verdict = "review" if negative_score <= 2 else "reject"
    elif should_hit_count == 1:
        verdict = "review" if negative_score <= 1 else "reject"
    else:
        verdict = "reject" if negative_score >= 1 else "review"

    return {
        "verdict": verdict,
        "positive_score": positive_score,
        "negative_score": negative_score,
        "must_hit_count": must_hit_count,
        "strong_hit_count": strong_hit_count,
        "should_hit_count": should_hit_count,
        "must_hits": must_hits,
        "strong_hits": strong_hits,
        "should_hits": should_hits,
        "not_hits": not_hits,
        "negative_hits": negative_hits,
        "unique_negative_hits": unique_negative_hits,
    }


# =========================
# Eval
# =========================

def evaluate(
    conn,
    model: SentenceModel,
    events_path: str,
    recall_top_k: int,
    print_failures: int = 20,
) -> None:
    total = 0

    dense_hit_1 = dense_hit_3 = dense_hit_5 = dense_hit_20 = 0
    rerank_hit_1 = rerank_hit_3 = rerank_hit_5 = rerank_hit_20 = 0

    failures: List[Dict[str, Any]] = []

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

            dense_rows = dense_recall(conn, query_text, model, recall_top_k)
            reranked_rows = rerank_candidates(query_text, dense_rows, model)

            dense_keys = [r["subject_key"] for r in dense_rows]
            rerank_keys = [r["subject_key"] for r in reranked_rows]

            if gt_subject_key in dense_keys[:1]:
                dense_hit_1 += 1
            if gt_subject_key in dense_keys[:3]:
                dense_hit_3 += 1
            if gt_subject_key in dense_keys[:5]:
                dense_hit_5 += 1
            if gt_subject_key in dense_keys[:20]:
                dense_hit_20 += 1

            if gt_subject_key in rerank_keys[:1]:
                rerank_hit_1 += 1
            if gt_subject_key in rerank_keys[:3]:
                rerank_hit_3 += 1
            if gt_subject_key in rerank_keys[:5]:
                rerank_hit_5 += 1
            if gt_subject_key in rerank_keys[:20]:
                rerank_hit_20 += 1
            else:
                failures.append({
                    "event_id": event.get("event_id"),
                    "gt_subject_key": gt_subject_key,
                    "summary": event.get("summary"),
                    "dense_top5": dense_keys[:5],
                    "rerank_top5": rerank_keys[:5],
                })

            if total % 20 == 0:
                print(
                    f"[INFO] 已评估 {total} 条 | "
                    f"dense@1={dense_hit_1/total:.4f} dense@5={dense_hit_5/total:.4f} dense@20={dense_hit_20/total:.4f} | "
                    f"rerank@1={rerank_hit_1/total:.4f} rerank@5={rerank_hit_5/total:.4f} rerank@20={rerank_hit_20/total:.4f}"
                )

    print("\n" + "=" * 100)
    print(f"[DONE] 总样本数: {total}")
    if total > 0:
        print(f"dense_recall@1:   {dense_hit_1/total:.4f}")
        print(f"dense_recall@3:   {dense_hit_3/total:.4f}")
        print(f"dense_recall@5:   {dense_hit_5/total:.4f}")
        print(f"dense_recall@20:  {dense_hit_20/total:.4f}")
        print("-" * 60)
        print(f"rerank_recall@1:  {rerank_hit_1/total:.4f}")
        print(f"rerank_recall@3:  {rerank_hit_3/total:.4f}")
        print(f"rerank_recall@5:  {rerank_hit_5/total:.4f}")
        print(f"rerank_recall@20: {rerank_hit_20/total:.4f}")

    if failures:
        print("\n" + "=" * 100)
        print(f"[部分失败样本，最多展示 {print_failures} 条]")
        for item in failures[:print_failures]:
            print(json.dumps(item, ensure_ascii=False))


def evaluate_gate(
    conn,
    model: SentenceModel,
    events_path: str,
    recall_top_k: int,
    candidate_source: str = "dense",
    print_failures: int = 20,
) -> None:
    total = 0
    dense_top1_correct = 0
    gate_accept_total = 0
    gate_accept_correct = 0
    gate_review_total = 0
    gate_reject_total = 0

    failures: List[Dict[str, Any]] = []

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

            dense_rows = dense_recall(conn, query_text, model, recall_top_k)
            if not dense_rows:
                failures.append({
                    "event_id": event.get("event_id"),
                    "gt_subject_key": gt_subject_key,
                    "reason": "dense recall empty",
                    "summary": event.get("summary"),
                })
                continue

            if candidate_source == "rerank":
                candidate_rows = rerank_candidates(query_text, dense_rows, model)
            else:
                candidate_rows = dense_rows

            if not candidate_rows:
                failures.append({
                    "event_id": event.get("event_id"),
                    "gt_subject_key": gt_subject_key,
                    "reason": "candidate rows empty",
                    "summary": event.get("summary"),
                })
                continue

            top1 = candidate_rows[0]
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
                    "summary": event.get("summary"),
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

            if verdict != "accept" or not dense_correct:
                failures.append({
                    "event_id": event.get("event_id"),
                    "gt_subject_key": gt_subject_key,
                    "pred_subject_key": pred_subject_key,
                    "summary": event.get("summary"),
                    "gate_verdict": verdict,
                    "gate_result": gate_result,
                })

            if total % 20 == 0:
                print(
                    f"[INFO] 已评估 {total} 条 | "
                    f"top1_acc={dense_top1_correct/total:.4f} | "
                    f"accept_rate={gate_accept_total/total:.4f} | "
                    f"review_rate={gate_review_total/total:.4f} | "
                    f"reject_rate={gate_reject_total/total:.4f}"
                )

    print("\n" + "=" * 100)
    print(f"[DONE] 总样本数: {total}")
    if total > 0:
        print(f"top1_accuracy:         {dense_top1_correct/total:.4f}")
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
    parser = argparse.ArgumentParser(description="Dense Recall + Rerank Eval + Gate Eval")
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument("--events", required=True)
    parser.add_argument("--model-name", default="shibing624/text2vec-base-chinese")
    parser.add_argument("--recall-top-k", type=int, default=20)
    parser.add_argument("--mode", choices=["eval", "gate"], default="eval")
    parser.add_argument("--candidate-source", choices=["dense", "rerank"], default="dense")
    args = parser.parse_args()

    print("[INFO] 加载模型...")
    model = SentenceModel(args.model_name)

    print("[INFO] 连接数据库...")
    conn = psycopg2.connect(args.db_dsn)

    try:
        if args.mode == "eval":
            evaluate(
                conn=conn,
                model=model,
                events_path=args.events,
                recall_top_k=args.recall_top_k,
            )
        else:
            evaluate_gate(
                conn=conn,
                model=model,
                events_path=args.events,
                recall_top_k=args.recall_top_k,
                candidate_source=args.candidate_source,
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()