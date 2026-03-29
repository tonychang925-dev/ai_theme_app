#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
import_news_events.py

将 structured_events.jsonl 导入 PostgreSQL，并保持 event_id 与 JSON 文件一致
"""

import json
import argparse
import psycopg2
from psycopg2.extras import Json

def load_events(jsonl_file):
    events = []
    with open(jsonl_file, "r", encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line.strip())
            event = {
                "id": obj.get("event_id"),  # 使用 JSON 里的 event_id
                "news_id": obj.get("news_id"),
                "event_type": obj.get("event_type"),
                "impact_industries": obj.get("impact_industries"),
                "direction": obj.get("direction"),
                "confidence": obj.get("confidence"),
                "summary": obj.get("summary"),
                "event_time": obj.get("event_time"),
                "entities": Json(obj.get("entities", [])),
                "causal_claim": Json(obj.get("causal_claim", [])),
                "evidence_set": Json(obj.get("evidence_set", {})),
                "raw_event_json": Json(obj)
            }
            events.append(event)
    return events

def insert_events(events, db_dsn):
    conn = psycopg2.connect(db_dsn)
    cursor = conn.cursor()
    
    insert_sql = """
    INSERT INTO news_event
    (
        id,
        news_id,
        event_type,
        impact_industries,
        direction,
        confidence,
        summary,
        event_time,
        entities,
        causal_claim,
        evidence_set,
        raw_event_json
    )
    VALUES
    (
        %(id)s,
        %(news_id)s,
        %(event_type)s,
        %(impact_industries)s,
        %(direction)s,
        %(confidence)s,
        %(summary)s,
        %(event_time)s,
        %(entities)s,
        %(causal_claim)s,
        %(evidence_set)s,
        %(raw_event_json)s
    )
    ON CONFLICT (id) DO NOTHING
    """
    
    for event in events:
        cursor.execute(insert_sql, event)
    
    conn.commit()
    cursor.close()
    conn.close()
    print(f"导入完成，共 {len(events)} 条事件。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="导入 structured_events.jsonl 到 PostgreSQL")
    parser.add_argument("--events", required=True, help="structured_events.jsonl 文件路径")
    parser.add_argument("--db-dsn", required=True, help="PostgreSQL DSN，例如：postgresql://user:pwd@127.0.0.1:5432/dbname")
    args = parser.parse_args()
    
    events = load_events(args.events)
    insert_events(events, args.db_dsn)