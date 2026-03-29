#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from openai import OpenAI  # DeepSeek 兼容 API


def safe_str(x: Any) -> str:
    return "" if x is None else str(x).strip()


def safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def truncate_text(text: str, max_len: int) -> str:
    text = safe_str(text)
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


def normalize_event_list(events: List[Dict[str, Any]], max_events: int = 12) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for e in events[:max_events]:
        out.append(
            {
                "event_id": safe_str(e.get("event_id")),
                "date": safe_str(e.get("date")),
                "title": safe_str(e.get("title")),
                "summary": truncate_text(safe_str(e.get("summary")), 300),
                "event_type": safe_str(e.get("event_type")),
                "entities": e.get("entities") or [],
                "core_concepts": e.get("core_concepts") or [],
                "tech_phrases": e.get("tech_phrases") or [],
            }
        )
    return out


def build_system_prompt() -> str:
    return """你是金融题材股票动态映射分析助手。

任务：
- 给定题材、题材分支、相关事件、股票静态证据，判断股票与题材关联。
- 输出 JSON，只允许 link_level: verified|related|semantic_only|reject
- link_type: core_mapping|technology_mapping|supply_mapping|scenario_mapping|event_mapping|other
- select_reason 必须列出核心证据，evidence_json 列出使用字段。
- 参考 Stage1 score 辅助置信度判断。
- 如果证据不足，使用 semantic_only 而非 reject。
"""


def build_user_prompt(stock_entry: Dict[str, Any]) -> str:
    event_list = normalize_event_list(stock_entry.get("event_list") or [], max_events=12)

    payload = {
        "topic_context": {
            "root_subject_key": safe_str(stock_entry.get("root_subject_key")),
            "root_subject_name": safe_str(stock_entry.get("root_subject_name")),
            "direction_subject_key": safe_str(stock_entry.get("direction_subject_key")),
            "direction_subject_name": safe_str(stock_entry.get("direction_subject_name")),
            "subject_reason": truncate_text(safe_str(stock_entry.get("subject_reason")), 1000),
            "aliases": stock_entry.get("aliases") or [],
            "component_words": stock_entry.get("component_words") or [],
        },
        "events": event_list,
        "stock_context": {
            "stock_id": safe_str(stock_entry.get("stock_id")),
            "stock_name": safe_str(stock_entry.get("stock_name")),
            "profile_text": truncate_text(safe_str(stock_entry.get("profile_text")), 2500),
            "remark": truncate_text(safe_str(stock_entry.get("remark")), 1200),
            "lightspots": (stock_entry.get("lightspots") or [])[:12],
            "detail_html_text": truncate_text(safe_str(stock_entry.get("detail_html_text")), 6000),
        },
        "stage1_context": {
            "stage1_score": safe_float(stock_entry.get("stage1_score")),
            "stage1_confidence": safe_str(stock_entry.get("stage1_confidence")),
            "stage1_gate_reason": safe_str(stock_entry.get("stage1_gate_reason")),
        },
        "instructions": "请基于 component_words / aliases / subject_reason / stock evidence /事件列表 输出 JSON，必填 link_level, link_type, confidence, select_reason, evidence_json",
    }

    return json.dumps(payload, ensure_ascii=False, indent=2)


def parse_llm_json(text: str) -> Dict[str, Any]:
    text = safe_str(text)
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()

    try:
        return json.loads(text)
    except Exception:
        return {
            "link_level": "reject",
            "link_type": "other",
            "confidence": 0.0,
            "select_reason": "",
            "evidence_json": {
                "matched_profile_terms": [],
                "matched_remark_terms": [],
                "matched_lightspots_terms": [],
                "matched_event_terms": [],
                "used_sources": [],
                "support_strength": "weak",
            },
            "_raw_text": text,
            "_parse_error": True,
        }


def call_deepseek(
    client: OpenAI,
    model: str,
    stock_entry: Dict[str, Any],
    temperature: float = 0.0,
    max_retries: int = 3,
) -> Dict[str, Any]:
    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(stock_entry)

    last_err = None
    for i in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            result = parse_llm_json(content)

            result.setdefault("stock_id", safe_str(stock_entry.get("stock_id")))
            result.setdefault("stock_name", safe_str(stock_entry.get("stock_name")))
            result.setdefault("subject_key", safe_str(stock_entry.get("direction_subject_key")))
            result.setdefault("subject_name", safe_str(stock_entry.get("direction_subject_name")))
            result.setdefault("link_level", "reject")
            result.setdefault("link_type", "other")
            result.setdefault("confidence", 0.0)
            result.setdefault("select_reason", "")
            result.setdefault("evidence_json", {
                "matched_profile_terms": [],
                "matched_remark_terms": [],
                "matched_lightspots_terms": [],
                "matched_event_terms": [],
                "used_sources": [],
                "support_strength": "weak",
            })
            return result
        except Exception as e:
            last_err = e
            time.sleep(1.5)

    return {
        "stock_id": safe_str(stock_entry.get("stock_id")),
        "stock_name": safe_str(stock_entry.get("stock_name")),
        "subject_key": safe_str(stock_entry.get("direction_subject_key")),
        "subject_name": safe_str(stock_entry.get("direction_subject_name")),
        "link_level": "reject",
        "link_type": "other",
        "confidence": 0.0,
        "select_reason": "",
        "evidence_json": {
            "matched_profile_terms": [],
            "matched_remark_terms": [],
            "matched_lightspots_terms": [],
            "matched_event_terms": [],
            "used_sources": [],
            "support_strength": "weak",
        },
        "_error": safe_str(last_err),
    }


def run_stage2(
    stage2_input_path: str,
    output_path: str,
    api_key: str,
    base_url: str,
    model: str,
    temperature: float = 0.0,
    limit: int = 0,
) -> None:
    with open(stage2_input_path, "r", encoding="utf-8") as f:
        inputs = json.load(f)
    if limit > 0:
        inputs = inputs[:limit]

    client = OpenAI(api_key=api_key, base_url=base_url)

    results: List[Dict[str, Any]] = []

    for idx, stock_entry in enumerate(inputs, start=1):
        print(f"[Stage2] {idx}/{len(inputs)} stock={stock_entry.get('stock_name')} subject={stock_entry.get('direction_subject_name')}")
        llm_result = call_deepseek(client, model, stock_entry, temperature=temperature)

        final_row = {
            "run_id": safe_str(stock_entry.get("run_id")),
            "event_id": safe_str(stock_entry.get("event_id")),
            "root_subject_key": safe_str(stock_entry.get("root_subject_key")),
            "root_subject_name": safe_str(stock_entry.get("root_subject_name")),
            "direction_subject_key": safe_str(stock_entry.get("direction_subject_key")),
            "direction_subject_name": safe_str(stock_entry.get("direction_subject_name")),
            "stock_id": llm_result.get("stock_id", stock_entry.get("stock_id")),
            "stock_name": llm_result.get("stock_name", stock_entry.get("stock_name")),
            "stage1_score": safe_float(stock_entry.get("stage1_score")),
            "stage1_confidence": safe_str(stock_entry.get("stage1_confidence")),
            "stage1_gate_reason": safe_str(stock_entry.get("stage1_gate_reason")),
            "link_level": llm_result.get("link_level"),
            "link_type": llm_result.get("link_type"),
            "confidence": safe_float(llm_result.get("confidence")),
            "select_reason": llm_result.get("select_reason"),
            "evidence_json": llm_result.get("evidence_json"),
        }

        results.append(final_row)

    Path(output_path).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] Stage2 输出写入: {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stage2 动态股票-题材映射（DeepSeek版）")
    parser.add_argument("--stage2-input", required=True, help="Stage2 输入 JSON 文件")
    parser.add_argument("--output", required=True, help="Stage2 输出 JSON 文件")
    parser.add_argument("--api-key", required=True, help="DeepSeek API Key")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1", help="DeepSeek Base URL")
    parser.add_argument("--model", default="deepseek-chat", help="DeepSeek Model")
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--limit", type=int, default=0, help="仅处理前 N 条")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_stage2(
        stage2_input_path=args.stage2_input,
        output_path=args.output,
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
        temperature=args.temperature,
        limit=args.limit,
    )