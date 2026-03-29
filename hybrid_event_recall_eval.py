#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
hybrid_event_recall_eval.py

批量事件 Hybrid Recall 测试
- Dense Recall: theme_profile_ext.embedding (pgvector + text2vec)
- Sparse Recall: theme_gate_profile.search_vector (FTS)
- RRF Merge
- 输出 TopK 召回指标及失败案例
"""

from __future__ import annotations
import argparse
import json
from typing import List, Dict
import psycopg2
import psycopg2.extras
from text2vec import SentenceModel

# -----------------------------
# 工具函数
# -----------------------------

def normalize_text(text: str) -> str:
    return text.strip() if text else ""

def vector_to_pgvector_literal(vec: List[float]) -> str:
    return "'[" + ",".join(f"{x:.6f}" for x in vec) + "]'::vector"

def safe_json_loads(line: str) -> Dict:
    line = line.strip()
    if not line:
        return {}
    return json.loads(line)

def rrf_merge(dense_rows: List[Dict], sparse_rows: List[Dict], k: int = 60) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for rank, row in enumerate(dense_rows, start=1):
        sk = row["subject_key"]
        merged.setdefault(sk, {
            "subject_key": sk,
            "dense_rank": rank,
            "dense_score": row.get("score"),
            "sparse_rank": None,
            "sparse_score": None,
            "rrf_score": 1.0 / (k + rank)
        })
    for rank, row in enumerate(sparse_rows, start=1):
        sk = row["subject_key"]
        if sk not in merged:
            merged[sk] = {
                "subject_key": sk,
                "dense_rank": None,
                "dense_score": None,
                "sparse_rank": rank,
                "sparse_score": row.get("score"),
                "rrf_score": 1.0 / (k + rank)
            }
        else:
            merged[sk]["sparse_rank"] = rank
            merged[sk]["sparse_score"] = row.get("score")
            merged[sk]["rrf_score"] += 1.0 / (k + rank)
    out = list(merged.values())
    out.sort(key=lambda x: (-x["rrf_score"], x["subject_key"]))
    return out

def load_concept_to_subject_keys(conn) -> dict:
    """
    将 theme_gate_profile.concept 映射到 subject_key 列表
    """
    sql = """
    SELECT subject_key, concept
    FROM theme_gate_profile
    WHERE concept IS NOT NULL AND trim(concept) <> ''
    """
    out = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql)
        for row in cur.fetchall():
            concept = row["concept"].strip()
            sk = row["subject_key"].strip()
            out.setdefault(concept, []).append(sk)
    return out

def build_event_query_text(event: Dict[str, Any]) -> str:
    """
    将事件对象拼成查询文本。
    兼容你当前 structured_events.jsonl 的字段：
    - summary
    - raw_text
    - event_type
    - entities
    - causal_claim
    - evidence_set.core_concepts
    """
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

# -----------------------------
# Recall 查询函数
# -----------------------------

def dense_recall(conn, query_text: str, model: SentenceModel, top_k: int) -> List[Dict]:
    """
    稳定版 dense recall：
    1. 主查询：纯 pgvector topK
    2. 若异常或返回空，自动重试一次
    3. 若仍为空，做兜底查询；若兜底能查到，则直接返回兜底结果
    4. 若最终仍为空，抛异常而不是静默返回 []，避免继续污染评估结果
    """
    query_vec = model.encode(query_text)
    if hasattr(query_vec, "tolist"):
        query_vec = query_vec.tolist()

    literal = vector_to_pgvector_literal(query_vec)

    main_sql = f"""
        SELECT
            t.subject_key,
            1 - (t.embedding <=> {literal}) AS score
        FROM theme_profile_ext t
        WHERE t.embedding IS NOT NULL
        ORDER BY t.embedding <=> {literal}
        LIMIT {int(top_k)}
    """

    fallback_sql = f"""
        SELECT
            subject_key,
            1 - (embedding <=> {literal}) AS score
        FROM theme_profile_ext
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> {literal}
        LIMIT 5
    """

    # 第一次主查询
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(main_sql)
            rows = list(cur.fetchall())
        if rows:
            return rows
    except Exception as e:
        print(f"[WARN] dense_recall main_sql first try failed: {repr(e)}")

    # 第二次主查询重试
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(main_sql)
            rows = list(cur.fetchall())
        if rows:
            return rows
    except Exception as e:
        print(f"[WARN] dense_recall main_sql second try failed: {repr(e)}")

    # 兜底查询
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(fallback_sql)
            fallback_rows = list(cur.fetchall())
        if fallback_rows:
            print("[WARN] dense_recall main_sql empty, fallback_sql returned rows; using fallback result")
            return fallback_rows[:int(top_k)]
    except Exception as e:
        print(f"[WARN] dense_recall fallback_sql failed: {repr(e)}")

    raise RuntimeError(
        f"dense_recall returned no rows. query_text_head={query_text[:120]!r}"
    )

def sparse_recall(conn, query_text: str, top_k: int) -> List[Dict]:
    sql = """
        SELECT subject_key, concept,
               ts_rank_cd(search_vector, websearch_to_tsquery('simple', %s)) AS score
        FROM theme_gate_profile
        WHERE search_vector @@ websearch_to_tsquery('simple', %s)
        ORDER BY score DESC, subject_key
        LIMIT %s
    """
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, (query_text, query_text, top_k))
        return list(cur.fetchall())


def flatten_text_items(value):
    out = []

    def _walk(x):
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


def token_hit_terms(text, terms):
    text = normalize_text(text)
    hits = []
    for t in terms:
        t = normalize_text(t)
        if not t:
            continue
        if t in text:
            hits.append(t)
    return hits


def load_gate_profile(conn, subject_key):
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


def gate_decide(event_text, gate_row):
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

    # 先看正证据，再看负证据
    if must_hit_count >= 1:
        verdict = "accept" if negative_score < 6 else "review"
    elif strong_hit_count >= 2:
        verdict = "accept" if negative_score < 6 else "review"
    elif strong_hit_count >= 1 and should_hit_count >= 1:
        verdict = "accept" if negative_score < 4 else "review"
    elif strong_hit_count >= 1:
        verdict = "review"
    elif should_hit_count >= 2:
        verdict = "review" if negative_score < 3 else "reject"
    elif should_hit_count == 1:
        verdict = "review" if negative_score < 2 else "reject"
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


def evaluate_gate_events(
    conn,
    model,
    events_path,
    gt_field,
    top_k,
    dense_top_k,
    sparse_top_k,
    print_failures=20,
):
    total = 0
    dense_top1_correct = 0
    gate_accept_total = 0
    gate_accept_correct = 0
    gate_review_total = 0
    gate_reject_total = 0
    failures = []

    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            event = safe_json_loads(line)
            if not event:
                continue

            gt_subject_key = normalize_text(event.get(gt_field))
            if not gt_subject_key:
                continue

            query_text = build_event_query_text(event)
            if not query_text:
                continue

            total += 1

            # 直接复用当前文件里已经验证过的 dense_recall
            dense_rows = dense_recall(conn, query_text, model, 1)
            if not dense_rows:
                failures.append({
                    "event_id": event.get("event_id"),
                    "reason": "dense_top1 empty",
                    "query_text": query_text,
                })
                continue

            top1 = dense_rows[0]
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

# -----------------------------
# 批量事件评估
# -----------------------------

def evaluate_events(
    conn,
    model: SentenceModel,
    events_path: str,
    gt_field: str,
    top_k: int,
    dense_top_k: int,
    sparse_top_k: int,
    print_failures: int = 20,
) -> None:
    total = 0
    dense_hit = 0
    sparse_hit = 0
    merge_hit = 0
    failures: list = []

    # 加载 theme_name -> subject_key 映射
    concept_to_subject_keys = load_concept_to_subject_keys(conn)

    with open(events_path, "r", encoding="utf-8") as f:
        for line in f:
            event = json.loads(line.strip())
            if not event:
                continue

            gt_raw = event.get(gt_field)
            if not gt_raw:
                continue

            # 将 theme_name 转成 subject_key 列表
            gt_subject_keys = concept_to_subject_keys.get(gt_raw, [])
            if not gt_subject_keys:
                # 如果没有映射，兼容原始值
                gt_subject_keys = [gt_raw]

            query_text = build_event_query_text(event)
            if not query_text:
                continue

            total += 1

            dense_rows = dense_recall(conn, query_text, model, dense_top_k)
            sparse_rows = sparse_recall(conn, query_text, sparse_top_k)
            merged_rows = rrf_merge(dense_rows, sparse_rows)

            dense_keys = [r["subject_key"] for r in dense_rows[:top_k]]
            sparse_keys = [r["subject_key"] for r in sparse_rows[:top_k]]
            merge_keys = [r["subject_key"] for r in merged_rows[:top_k]]

            if any(gt in dense_keys for gt in gt_subject_keys):
                dense_hit += 1
            if any(gt in sparse_keys for gt in gt_subject_keys):
                sparse_hit += 1
            if any(gt in merge_keys for gt in gt_subject_keys):
                merge_hit += 1
            else:
                failures.append({
                    "event_id": event.get("event_id"),
                    "theme_name": gt_raw,
                    "gt_subject_keys": gt_subject_keys,
                    "summary": event.get("summary"),
                    "merge_top5": merge_keys[:5],
                })

            if total % 20 == 0:
                print(
                    f"[INFO] 已评估 {total} 条 | "
                    f"dense@{top_k}={dense_hit/total:.4f} | "
                    f"sparse@{top_k}={sparse_hit/total:.4f} | "
                    f"merge@{top_k}={merge_hit/total:.4f}"
                )

    print("\n" + "="*100)
    print(f"[DONE] 总样本数: {total}")
    if total > 0:
        print(f"dense_recall@{top_k}:  {dense_hit/total:.4f}")
        print(f"sparse_recall@{top_k}: {sparse_hit/total:.4f}")
        print(f"merge_recall@{top_k}:  {merge_hit/total:.4f}")

    if failures:
        print("\n" + "="*100)
        print(f"[部分失败样本，最多展示 {print_failures} 条]")
        for item in failures[:print_failures]:
            print(json.dumps(item, ensure_ascii=False))

# -----------------------------
# 主函数
# -----------------------------

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument("--model-name", default="shibing624/text2vec-base-chinese")
    parser.add_argument("--query", help="单条事件文本")
    parser.add_argument("--events", help="批量事件 JSONL 文件路径")
    parser.add_argument("--gt-field", default="gt_subject_key")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--dense-top-k", type=int, default=50)
    parser.add_argument("--sparse-top-k", type=int, default=50)
    parser.add_argument("--mode", choices=["recall", "gate"], default="recall")
    args = parser.parse_args()

    print("[INFO] 加载模型...")
    model = SentenceModel(args.model_name)

    print("[INFO] 连接数据库...")
    conn = psycopg2.connect(args.db_dsn)

    try:
        if args.mode == "recall":
            if args.query:
                query_text = normalize_text(args.query)
                dense_rows = dense_recall(conn, query_text, model, args.dense_top_k)
                sparse_rows = sparse_recall(conn, query_text, args.sparse_top_k)
                merged_rows = rrf_merge(dense_rows, sparse_rows)
                print_top_results(dense_rows, sparse_rows, merged_rows, top_n=min(10, args.top_k))

            if args.events:
                evaluate_events(
                    conn=conn,
                    model=model,
                    events_path=args.events,
                    gt_field=args.gt_field,
                    top_k=args.top_k,
                    dense_top_k=args.dense_top_k,
                    sparse_top_k=args.sparse_top_k,
                )

        elif args.mode == "gate":
            if not args.events:
                raise ValueError("--mode gate 时必须提供 --events")

            evaluate_gate_events(
                conn=conn,
                model=model,
                events_path=args.events,
                gt_field=args.gt_field,
                top_k=args.top_k,
                dense_top_k=args.dense_top_k,
                sparse_top_k=args.sparse_top_k,
            )
    finally:
        conn.close()

if __name__ == "__main__":
    main()