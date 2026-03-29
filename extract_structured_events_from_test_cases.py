#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
对测试集文本进行解析，并调用 LLM 生成结构化事件输出。

支持：
1. 解析“题材名称 + 多条事件”格式测试集
2. 对每条事件输出结构化 JSON
3. 输出 JSONL 文件
4. 缓存处理（避免重复调用 LLM）
5. 断点续跑（processed 标记）
6. 失败清单输出
7. tqdm 进度条显示

默认输入：
--input /mnt/data/test_cases.txt

输出字段示例：
{
  "event_id": "evt_xxx",
  "theme_name": "可控核聚变",
  "event_type": "技术突破",
  "entities": [...],
  "summary": "...",
  "causal_claim": [...],
  "evidence_set": {...},
  "severity_score": 0.9,
  "confidence": 0.95,
  "source_weight": 1.2,
  "timestamp": "2026-02-28T10:00:05Z",
  "raw_text": "..."
}
"""

import os
import re
import sys
import json
import time
import uuid
import hashlib
import argparse
from pathlib import Path
from typing import Dict, List, Any, Optional

import requests
from tqdm import tqdm
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# =========================
# Config
# =========================
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"


# =========================
# LLM Prompt
# =========================
EVENT_STRUCT_SYSTEM = """你是一个新闻事件结构化抽取器。
你的任务是把单条新闻事件文本抽取为结构化 JSON，用于后续“事件 -> 题材树 -> 股票映射”。

必须遵守以下要求：
1. 只基于输入文本抽取，不得编造事实。
2. 输出必须是合法 JSON 对象。
3. event_type 需尽量归一为简洁类型，如：
   - 政策
   - 制裁
   - 技术突破
   - 会议论坛
   - 行业观点
   - 融资IPO
   - 并购重组
   - 产品发布
   - 订单合作
   - 市场预测
   - 组织设立
   - 产能扩张
   - 事故冲突
   - 其他
4. entities 只保留对题材匹配有用的实体，格式：
   {"name":"原文实体","type":"国家|公司|组织|产品|技术|人物|地点|行业","normalized":"归一化名称"}
5. summary 必须是简洁事件摘要，不超过60字。
6. causal_claim 必须是短语数组，表达“事件 -> 影响链路 -> 潜在题材方向”，不得写长句。
7. evidence_set 必须包含：
   - tech_phrases: 技术/政策/事件短语数组
   - normalized_terms: 实体归一化映射对象
   - evidence_spans: 关键证据片段数组，元素格式 {"text":"...","start":0,"end":10}
   - core_concepts: 核心概念数组
8. severity_score 范围 0~1，表示事件强度。
9. confidence 范围 0~1，表示抽取置信度。
10. source_weight 范围建议 0.5~1.5。若文本末尾明确提到“新华社/财联社/科创板日报/财经网”等来源，可按权威度给权重；若不明确则给 1.0。
11. timestamp 若文本里能明确提取日期，则尽量标准化输出 ISO8601 字符串；若无法确定，输出 null。
12. 不要输出 markdown，不要输出解释。

输出 JSON 格式：
{
  "event_type": "技术突破",
  "entities": [
    {"name": "美国", "type": "国家", "normalized": "美国"},
    {"name": "华为", "type": "公司", "normalized": "华为"}
  ],
  "summary": "美国宣布对华为实施新出口管制",
  "causal_claim": ["出口管制", "芯片短缺", "国产替代"],
  "evidence_set": {
    "tech_phrases": ["出口管制", "5G", "芯片"],
    "normalized_terms": {"美国": "美国", "华为": "华为"},
    "evidence_spans": [
      {"text": "美国宣布对华为实施新出口管制", "start": 0, "end": 20}
    ],
    "core_concepts": ["制裁", "出口管制"]
  },
  "severity_score": 0.9,
  "confidence": 0.95,
  "source_weight": 1.2,
  "timestamp": "2026-02-28T10:00:05Z"
}
"""


# =========================
# LLM Client
# =========================
class DeepSeekClient:
    def __init__(self, api_key: str, base_url: str = DEEPSEEK_BASE_URL, model: str = DEEPSEEK_MODEL):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.sess = requests.Session()

    @staticmethod
    def _extract_json_block_loose(text: str) -> Optional[str]:
        if not text:
            return None
        t = text.strip()
        if t.startswith("{") and t.endswith("}"):
            return t
        m = re.search(r"(\{[\s\S]*\})", t)
        if m:
            return m.group(1).strip()
        return None

    def run_json_object(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 2500,
        temperature: float = 0.1,
        max_retries: int = 4,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        last_err = None
        backoff = 1.5

        for _ in range(max_retries + 1):
            try:
                resp = self.sess.post(url, headers=headers, json=payload, timeout=(10, 300))
                if resp.status_code in (429, 500, 502, 503, 504):
                    time.sleep(backoff)
                    backoff = min(backoff * 1.8, 15)
                    continue

                resp.raise_for_status()
                data = resp.json()
                content = data["choices"][0]["message"]["content"]

                try:
                    obj = json.loads(content)
                except json.JSONDecodeError:
                    block = self._extract_json_block_loose(content)
                    if block:
                        obj = json.loads(block)
                    else:
                        raise

                if not isinstance(obj, dict):
                    raise RuntimeError("LLM 返回不是 JSON object")
                return obj

            except Exception as e:
                last_err = e
                time.sleep(backoff)
                backoff = min(backoff * 1.8, 15)

        raise RuntimeError(f"LLM 调用失败: {repr(last_err)}")


# =========================
# Utils
# =========================
def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def save_json(path: Path, obj: Any):
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, row: Dict[str, Any]):
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def stable_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()[:16]


def normalize_source_weight(text: str) -> float:
    if "新华社" in text:
        return 1.3
    if "财联社" in text:
        return 1.2
    if "科创板日报" in text:
        return 1.15
    if "财经网" in text:
        return 1.05
    if "中国财富网" in text:
        return 1.0
    return 1.0


def maybe_extract_date(text: str) -> Optional[str]:
    """
    只做轻量日期兜底，不强行推断完整时间。
    若匹配到 YYYY年MM月DD日，则转 YYYY-MM-DDT00:00:00Z
    """
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if m:
        y, mo, d = m.groups()
        return f"{int(y):04d}-{int(mo):02d}-{int(d):02d}T00:00:00Z"
    return None


# =========================
# Parse test file
# =========================
def parse_test_cases(raw_text: str) -> List[Dict[str, Any]]:
    """
    兼容：
    - 测试集3:题材名称:可控核聚变
    - - 事件文本
    - 普通段落
    """
    lines = [x.rstrip() for x in raw_text.splitlines()]
    cases: List[Dict[str, Any]] = []

    current_theme = None
    pending_buffer: List[str] = []

    def flush_buffer_as_case():
        nonlocal pending_buffer, current_theme, cases
        text = "\n".join([x for x in pending_buffer if x.strip()]).strip(" -*\n")
        if text:
            cases.append({
                "theme_name": current_theme,
                "raw_text": text,
            })
        pending_buffer = []

    for line in lines:
        s = line.strip()
        if not s:
            continue

        # 新题材标题
        m = re.search(r"题材名称[:：]\s*([^\n]+)", s)
        if m:
            flush_buffer_as_case()
            current_theme = m.group(1).strip(" -*")
            continue

        # 明确 bullet 事件
        if s.startswith("- "):
            flush_buffer_as_case()
            cases.append({
                "theme_name": current_theme,
                "raw_text": s[2:].strip(" *"),
            })
            continue

        # 普通文本：累计到 buffer
        pending_buffer.append(s)

    flush_buffer_as_case()

    # 过滤过短噪声
    cleaned = []
    for c in cases:
        txt = str(c["raw_text"]).strip()
        if len(txt) < 8:
            continue
        cleaned.append(c)

    return cleaned


# =========================
# Normalize LLM output
# =========================
def normalize_event_obj(
    llm_obj: Dict[str, Any],
    raw_text: str,
    theme_name: Optional[str],
    fallback_event_id: str,
) -> Dict[str, Any]:
    event_type = str(llm_obj.get("event_type") or "其他").strip() or "其他"
    summary = str(llm_obj.get("summary") or "").strip()
    causal_claim = llm_obj.get("causal_claim") or []
    entities = llm_obj.get("entities") or []
    evidence_set = llm_obj.get("evidence_set") or {}
    severity_score = llm_obj.get("severity_score", 0.5)
    confidence = llm_obj.get("confidence", 0.7)
    source_weight = llm_obj.get("source_weight", normalize_source_weight(raw_text))
    timestamp = llm_obj.get("timestamp")

    if not isinstance(entities, list):
        entities = []
    if not isinstance(causal_claim, list):
        causal_claim = []
    if not isinstance(evidence_set, dict):
        evidence_set = {}

    # 兜底
    if not timestamp:
        timestamp = maybe_extract_date(raw_text)

    try:
        severity_score = float(severity_score)
    except Exception:
        severity_score = 0.5
    try:
        confidence = float(confidence)
    except Exception:
        confidence = 0.7
    try:
        source_weight = float(source_weight)
    except Exception:
        source_weight = normalize_source_weight(raw_text)

    severity_score = max(0.0, min(1.0, severity_score))
    confidence = max(0.0, min(1.0, confidence))

    return {
        "event_id": fallback_event_id,
        "theme_name": theme_name,
        "event_type": event_type,
        "entities": entities,
        "summary": summary,
        "causal_claim": causal_claim,
        "evidence_set": evidence_set,
        "severity_score": severity_score,
        "confidence": confidence,
        "source_weight": source_weight,
        "timestamp": timestamp,
        "raw_text": raw_text,
    }


# =========================
# Main
# =========================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/mnt/data/test_cases.txt", help="测试集文本路径")
    ap.add_argument("--output", default="tmp/structured_events.jsonl", help="输出 JSONL")
    ap.add_argument("--cache-dir", default="tmp/event_struct_cache", help="缓存目录")
    ap.add_argument("--processed-dir", default="tmp/event_struct_processed", help="断点标记目录")
    ap.add_argument("--failed-out", default="tmp/event_struct_failed/failed_cases.json", help="失败清单")
    ap.add_argument("--retry-failed-file", default="", help="按失败清单重跑")
    ap.add_argument("--deepseek-api-key", default="", help="DeepSeek API Key")
    ap.add_argument("--limit", type=int, default=0, help="限制处理数量")
    ap.add_argument("--force-refresh", action="store_true", help="忽略缓存和断点")
    ap.add_argument("--fail-fast", action="store_true", help="单条失败即中断")
    args = ap.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise FileNotFoundError(f"输入文件不存在: {input_path}")

    api_key = args.deepseek_api_key.strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请提供 DeepSeek API Key")

    ds = DeepSeekClient(api_key=api_key)

    raw_text = read_text(input_path)
    cases = parse_test_cases(raw_text)

    if args.retry_failed_file:
        retry_path = Path(args.retry_failed_file)
        retry_obj = read_text(retry_path)
        retry_records = json.loads(retry_obj)
        retry_ids = set()
        if isinstance(retry_records, list):
            for x in retry_records:
                if isinstance(x, dict) and x.get("case_id"):
                    retry_ids.add(str(x["case_id"]))
        tmp_cases = []
        for c in cases:
            cid = stable_hash((c.get("theme_name") or "") + "||" + c["raw_text"])
            if cid in retry_ids:
                tmp_cases.append(c)
        cases = tmp_cases

    if args.limit and args.limit > 0:
        cases = cases[:args.limit]

    cache_dir = Path(args.cache_dir)
    processed_dir = Path(args.processed_dir)
    output_path = Path(args.output)
    failed_out = Path(args.failed_out)

    # force_refresh 时清空本次输出，避免重复追加
    if args.force_refresh and output_path.exists():
        output_path.unlink()

    pre_stats = {
        "input_file": str(input_path),
        "parsed_cases": len(cases),
        "output": str(output_path),
        "cache_dir": str(cache_dir),
        "processed_dir": str(processed_dir),
        "failed_out": str(failed_out),
        "force_refresh": args.force_refresh,
    }
    logger.info("==== 处理前统计 ====")
    logger.info(json.dumps(pre_stats, ensure_ascii=False, indent=2))

    stats = {
        "processed_cases": 0,
        "used_cache": 0,
        "llm_called": 0,
        "skipped_already_processed": 0,
        "failed": 0,
    }
    failed_records: List[Dict[str, Any]] = []

    pbar = tqdm(cases, desc="结构化测试事件", unit="case")

    for case in pbar:
        theme_name = case.get("theme_name")
        raw_event_text = case["raw_text"]
        case_id = stable_hash((theme_name or "") + "||" + raw_event_text)

        cache_path = cache_dir / f"{case_id}.json"
        done_flag = processed_dir / f"{case_id}.done"

        if done_flag.exists() and not args.force_refresh:
            stats["skipped_already_processed"] += 1
            pbar.set_postfix({
                "done": stats["processed_cases"],
                "cache": stats["used_cache"],
                "llm": stats["llm_called"],
                "skip": stats["skipped_already_processed"],
                "fail": stats["failed"],
            })
            continue

        result_obj = None

        if not args.force_refresh and cache_path.exists():
            try:
                result_obj = json.loads(cache_path.read_text(encoding="utf-8"))
                stats["used_cache"] += 1
            except Exception:
                result_obj = None

        if result_obj is None:
            prompt = f"""题材名称：{theme_name or "未提供"}

新闻事件原文：
{raw_event_text}
"""
            messages = [
                {"role": "system", "content": EVENT_STRUCT_SYSTEM},
                {"role": "user", "content": prompt},
            ]

            try:
                llm_obj = ds.run_json_object(messages, max_tokens=2500, temperature=0.1)
                event_id = f"evt_{uuid.uuid4().hex[:12]}"
                result_obj = normalize_event_obj(
                    llm_obj=llm_obj,
                    raw_text=raw_event_text,
                    theme_name=theme_name,
                    fallback_event_id=event_id,
                )
                save_json(cache_path, result_obj)
                stats["llm_called"] += 1
            except Exception as e:
                stats["failed"] += 1
                failed_records.append({
                    "case_id": case_id,
                    "theme_name": theme_name,
                    "raw_text": raw_event_text,
                    "error": repr(e),
                })
                pbar.set_postfix({
                    "done": stats["processed_cases"],
                    "cache": stats["used_cache"],
                    "llm": stats["llm_called"],
                    "skip": stats["skipped_already_processed"],
                    "fail": stats["failed"],
                })
                if args.fail_fast:
                    save_json(failed_out, failed_records)
                    raise
                continue

        append_jsonl(output_path, result_obj)
        ensure_dir(done_flag.parent)
        done_flag.touch()

        stats["processed_cases"] += 1
        pbar.set_postfix({
            "done": stats["processed_cases"],
            "cache": stats["used_cache"],
            "llm": stats["llm_called"],
            "skip": stats["skipped_already_processed"],
            "fail": stats["failed"],
        })

    pbar.close()

    save_json(failed_out, failed_records)

    summary = {
        **stats,
        "failed_out": str(failed_out),
        "output": str(output_path),
    }
    logger.info("==== 处理完成统计 ====")
    logger.info(json.dumps(summary, ensure_ascii=False, indent=2))

    # 校验：本次应处理 case 数 = 已处理 + 已跳过 + 失败
    total = len(cases)
    accounted = (
        stats["processed_cases"]
        + stats["skipped_already_processed"]
        + stats["failed"]
    )
    validation = {
        "expected_cases": total,
        "accounted_cases": accounted,
        "missing_cases": total - accounted,
        "ok": (total == accounted),
    }
    logger.info("==== 全量校验 ====")
    logger.info(json.dumps(validation, ensure_ascii=False, indent=2))

    if not validation["ok"]:
        raise RuntimeError("测试事件结构化处理校验失败，请检查流程。")


if __name__ == "__main__":
    main()