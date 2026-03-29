#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_theme_profile_ext_tree.py

为整棵题材树生成 theme_profile_ext：
- 支持 L1/L2/L3 节点
- 不再依赖 theme_master
- 输入：theme_gate_profile + subject_detail + 树节点名称
- 输出：summary/core_anchors/supporting_entities/representative_events/embedding_text/rerank_text
"""

from __future__ import annotations
import argparse, html, json, re
from collections import OrderedDict
from typing import Any, Dict, Iterable, List, Optional, Sequence
import psycopg2
import psycopg2.extras

# =============================
# 工具函数
# =============================
MULTI_SPACE_PAT = re.compile(r"[ \t\r\f\v]+")
MULTI_NL_PAT = re.compile(r"\n{2,}")
CN_PUNCT_SPLIT_PAT = re.compile(r"(?<=[。！？；\n])")
GENERIC_TERMS = {
    "AI", "人工智能", "智能", "应用", "终端", "设备", "电子", "科技", "技术", "行业",
    "产业", "产业链", "赛道", "概念", "方向", "板块", "领域", "业务", "系统", "平台",
    "产品", "服务", "方案", "公司", "企业", "市场", "需求", "发展", "增长", "生态",
    "驱动", "主题", "逻辑", "预期", "创新", "升级", "龙头", "制造", "链条", "材料",
    "元件", "器件", "芯片", "软件", "硬件", "数据", "网络", "模型"
}

def normalize_text(text: Optional[str]) -> str:
    if text is None:
        return ""
    text = str(text)
    text = html.unescape(text).replace("\u3000", " ")
    text = MULTI_SPACE_PAT.sub(" ", text)
    return text.strip()

def html_to_text(raw_html: Optional[str]) -> str:
    if not raw_html:
        return ""
    text = html.unescape(raw_html)
    text = re.sub(r"</(p|div|br|li|tr|h[1-6])>", "\n", text, flags=re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&nbsp;", " ").replace("&#160;", " ")
    text = MULTI_SPACE_PAT.sub(" ", text)
    text = text.replace(" \n", "\n").replace("\n ", "\n")
    text = MULTI_NL_PAT.sub("\n", text)
    return text.strip()

def split_sentences(text: str) -> List[str]:
    if not text:
        return []
    parts = CN_PUNCT_SPLIT_PAT.split(text)
    return [normalize_text(s) for s in parts if normalize_text(s)]

def dedup_keep_order(items: Iterable[str]) -> List[str]:
    seen = OrderedDict()
    for x in items:
        x = normalize_text(x)
        if x and x not in seen:
            seen[x] = 1
    return list(seen.keys())

def is_good_anchor_term(term: str) -> bool:
    term = normalize_text(term)
    if not term or len(term) <= 1 or term in GENERIC_TERMS or len(term) >= 40:
        return False
    return True

def is_good_entity_term(term: str) -> bool:
    term = normalize_text(term)
    if not is_good_anchor_term(term) or len(term) > 30:
        return False
    return True

def flatten_text_items(value: Any) -> List[str]:
    out: List[str] = []
    def _walk(x: Any) -> None:
        if x is None: return
        if isinstance(x, str):
            s = normalize_text(x)
            if s: out.append(s)
            return
        if isinstance(x, (int, float, bool)):
            out.append(str(x))
            return
        if isinstance(x, dict):
            for k in ["name","term","text","label","value","title"]:
                if k in x: _walk(x[k])
            for v in x.values(): _walk(v)
            return
        if isinstance(x, (list, tuple)):
            for y in x: _walk(y)
            return
    _walk(value)
    return dedup_keep_order(out)

def extract_ontology_sections(ontology_json: Any) -> Dict[str, List[str]]:
    sections = {"core_anchors":[],"supporting_entities":[],"representative_events":[]}
    if not ontology_json: return sections
    obj = ontology_json
    if isinstance(obj,str):
        try: obj=json.loads(obj)
        except Exception: return sections
    if isinstance(obj,dict):
        for k,v in obj.items():
            lk=str(k).lower()
            if "anchor" in lk or "core" in lk:
                sections["core_anchors"].extend(flatten_text_items(v))
            elif "entity" in lk or "company" in lk or "product" in lk or "tech" in lk:
                sections["supporting_entities"].extend(flatten_text_items(v))
            elif "event" in lk or "driver" in lk:
                sections["representative_events"].extend(flatten_text_items(v))
    else:
        sections["core_anchors"]=flatten_text_items(obj)
    for k in sections:
        sections[k]=dedup_keep_order(sections[k])
    return sections

# =============================
# 数据库读取
# =============================
def fetch_theme_gate_profiles(conn, subject_key: Optional[str]=None) -> List[Dict[str, Any]]:
    sql="select * from theme_gate_profile"
    params=[]
    if subject_key:
        sql+=" where subject_key=%s"
        params.append(subject_key)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        return list(cur.fetchall())

def fetch_subject_detail_map(conn, subject_keys: List[str]) -> Dict[str, Dict[str, Any]]:
    if not subject_keys: return {}
    sql="select * from subject_detail where subject_key=any(%s)"
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql,(subject_keys,))
        rows=cur.fetchall()
    out={}
    for r in rows:
        sk=r["subject_key"]
        if sk not in out or r.get("is_current"): out[sk]=r
    return out

# =============================
# 画像生成
# =============================
def build_summary(subject_key:str, gate_row:Dict[str,Any], detail_row:Optional[Dict[str,Any]]) -> str:
    name=normalize_text(gate_row.get("concept")) or subject_key
    reason=normalize_text((detail_row or {}).get("reason_short"))
    detail_html=normalize_text((detail_row or {}).get("detail_html"))
    sentences=split_sentences(html_to_text(detail_html))
    summary_parts=[]
    if reason: summary_parts.append(reason)
    for s in sentences[:3]:
        summary_parts.append(s)
    summary=" ".join(dedup_keep_order(summary_parts))
    if name not in summary:
        summary=f"{name}：{summary}"
    return summary[:240]

def build_core_anchors(gate_row:Dict[str,Any]) -> List[str]:
    must=flatten_text_items(gate_row.get("must_terms"))
    strong=flatten_text_items(gate_row.get("strong_terms"))
    ontology=extract_ontology_sections(gate_row.get("ontology_json"))
    anchors=must+strong+ontology["core_anchors"]
    anchors=[a for a in dedup_keep_order(anchors) if is_good_anchor_term(a)]
    return anchors[:18]

def build_supporting_entities(gate_row:Dict[str,Any], core_anchors:List[str]) -> List[str]:
    strong=flatten_text_items(gate_row.get("strong_terms"))
    should=flatten_text_items(gate_row.get("should_terms"))
    ontology=extract_ontology_sections(gate_row.get("ontology_json"))
    entities=strong+should+ontology["supporting_entities"]
    entities=[e for e in dedup_keep_order(entities) if is_good_entity_term(e) and e not in core_anchors]
    return entities[:20]

def build_representative_events(detail_row:Optional[Dict[str,Any]], core_anchors:List[str]) -> List[str]:
    if not detail_row: return []
    text=html_to_text(detail_row.get("detail_html"))
    sents=split_sentences(text)
    results=[]
    for s in sents:
        if len(s)<12: continue
        if any(a in s for a in core_anchors): results.append(s[:100])
        if len(results)>=8: break
    return dedup_keep_order(results)

def build_embedding_text(summary:str, core_anchors:List[str], supporting_entities:List[str], representative_events:List[str], name:str) -> str:
    parts=[name+"。", summary]
    if core_anchors: parts.append("核心锚点："+ "，".join(core_anchors[:12]))
    if supporting_entities: parts.append("支持实体："+ "，".join(supporting_entities[:12]))
    if representative_events: parts.append("代表事件："+ "；".join(representative_events[:5]))
    return " ".join(parts)

def build_rerank_text(summary:str, core_anchors:List[str], supporting_entities:List[str], name:str) -> str:
    parts=[f"题材名：{name}", "题材摘要："+summary]
    if core_anchors: parts.append("核心锚点："+ "，".join(core_anchors[:8]))
    if supporting_entities: parts.append("代表实体："+ "，".join(supporting_entities[:8]))
    return " ".join(parts)

def build_one_profile_ext(subject_key:str, gate_row:Dict[str,Any], detail_row:Optional[Dict[str,Any]]) -> Dict[str,Any]:
    summary=build_summary(subject_key, gate_row, detail_row)
    core_anchors=build_core_anchors(gate_row)
    supporting_entities=build_supporting_entities(gate_row, core_anchors)
    representative_events=build_representative_events(detail_row, core_anchors)
    name=normalize_text(gate_row.get("concept")) or subject_key
    embedding_text=build_embedding_text(summary, core_anchors, supporting_entities, representative_events, name)
    rerank_text=build_rerank_text(summary, core_anchors, supporting_entities, name)
    return {
        "subject_key": subject_key,
        "summary": summary,
        "core_anchors": core_anchors,
        "supporting_entities": supporting_entities,
        "representative_events": representative_events,
        "embedding_text": embedding_text,
        "rerank_text": rerank_text
    }

# =============================
# 写库
# =============================
def upsert_theme_profile_ext(conn,row:Dict[str,Any]):
    sql="""
    insert into theme_profile_ext(subject_key,summary,core_anchors,supporting_entities,representative_events,embedding_text,rerank_text,updated_at)
    values (%(subject_key)s,%(summary)s,%(core_anchors)s::jsonb,%(supporting_entities)s::jsonb,%(representative_events)s::jsonb,%(embedding_text)s,%(rerank_text)s,now())
    on conflict (subject_key) do update set
        summary=excluded.summary,
        core_anchors=excluded.core_anchors,
        supporting_entities=excluded.supporting_entities,
        representative_events=excluded.representative_events,
        embedding_text=excluded.embedding_text,
        rerank_text=excluded.rerank_text,
        updated_at=now()
    """
    payload=dict(row)
    payload["core_anchors"]=json.dumps(row["core_anchors"],ensure_ascii=False)
    payload["supporting_entities"]=json.dumps(row["supporting_entities"],ensure_ascii=False)
    payload["representative_events"]=json.dumps(row["representative_events"],ensure_ascii=False)
    with conn.cursor() as cur:
        cur.execute(sql,payload)

# =============================
# 主流程
# =============================
def main():
    parser=argparse.ArgumentParser(description="构建 theme_profile_ext（树节点画像版）")
    parser.add_argument("--db-dsn", required=True)
    parser.add_argument("--subject-key")
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--limit",type=int,default=0)
    args=parser.parse_args()

    conn=psycopg2.connect(args.db_dsn)
    conn.autocommit=False

    try:
        gate_rows=fetch_theme_gate_profiles(conn,args.subject_key)
        if args.limit>0:
            gate_rows=gate_rows[:args.limit]
        if not gate_rows:
            print("[INFO] 未找到 theme_gate_profile")
            return

        subject_keys=[r["subject_key"] for r in gate_rows]
        detail_map=fetch_subject_detail_map(conn,subject_keys)

        print(f"[INFO] 读取 gate_profile: {len(gate_rows)} 条")
        print(f"[INFO] 读取 subject_detail: {len(detail_map)} 条")

        processed=0
        for gate_row in gate_rows:
            sk=gate_row["subject_key"]
            detail_row=detail_map.get(sk)
            built=build_one_profile_ext(sk,gate_row,detail_row)

            if args.dry_run:
                print("="*80)
                print(f"[DRY-RUN] subject_key={sk}")
                print("summary:",built["summary"])
                print("core_anchors:",built["core_anchors"])
                print("supporting_entities:",built["supporting_entities"])
                print("representative_events:",built["representative_events"])
                print("embedding_text:",built["embedding_text"][:200]+"…")
                print("rerank_text:",built["rerank_text"][:200]+"…")
            else:
                upsert_theme_profile_ext(conn,built)
            processed+=1
            if processed%50==0 and not args.dry_run:
                conn.commit()
                print(f"[INFO] 已处理 {processed} 条")
        if not args.dry_run: conn.commit()
        print(f"[DONE] 完成 {processed} 条, {'未写库(dry-run)' if args.dry_run else '已写入数据库'}")
    finally:
        conn.close()

if __name__=="__main__":
    main()