#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
build_subject_blocks_from_details_v4.py

题材详情解析器 v4.1.1（批处理与缓存优化版）
- 支持批量处理题材列表
- 可配置缓存目录
- 第三层规范化添加缓存，大幅提升重复处理效率
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import html
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

import requests
from tqdm import tqdm

# ==================== 配置 ====================
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_TEMP = 0.1
DEFAULT_MAX_TOKENS = 4000
DEFAULT_SLEEP = 0.05
DEFAULT_MAX_RETRIES = 3

DEFAULT_CACHE_DIR = Path("chunk_role_cache")
DEBUG_DIR = Path("llm_debug") 
PROMPT_VERSION = "chunk_role_v4_1_0_semantic_final"

VALID_LABELS = {"strict_knowledge", "candidate_mixed", "pure_event", "noise"}
VALID_ONTOLOGY = {"high", "medium", "low"}
VALID_DECISIONS = {"keep", "split", "drop"}
VALID_KNOWLEDGE_TYPES = {"core", "related", "signal"}

STRICT_KNOWLEDGE_MIN_CONF = 0.85
CANDIDATE_MIXED_MIN_CONF = 0.70
PURE_EVENT_MIN_CONF = 0.60

BATCH_MAX_CHARS = 6000
BATCH_MAX_ITEMS = 8
FALLBACK_MIN_TEXT_LEN = 8
EVENT_RESIDUE_MIN_LEN = 12
MIN_KNOWLEDGE_LEN = 6

TYPE_PRIORITY = {"core": 3, "related": 2, "signal": 1}

# 全局缓存目录（可在main中修改）
CACHE_DIR = DEFAULT_CACHE_DIR
# ==============================================


# ==================== 数据结构 ====================
@dataclasses.dataclass
class LLMConfig:
    model: str = DEFAULT_MODEL
    temperature: float = DEFAULT_TEMP
    max_tokens: int = DEFAULT_MAX_TOKENS
    sleep: float = DEFAULT_SLEEP
    max_retries: int = DEFAULT_MAX_RETRIES


@dataclasses.dataclass
class DetailSection:
    heading: str
    lines: List[str]
    section_type: str  # "event" or "knowledge" or "unknown"
    start_idx: int
    end_idx: int


@dataclasses.dataclass
class SubjectDetail:
    subject_id: str
    name: str
    reason: str
    detail_html: str
    source_id: str


@dataclasses.dataclass
class DetailChunk:
    chunk_id: str
    subject_id: str
    subject_name: str
    source_id: str
    area: str  # "event_area" or "knowledge_area"
    context_heading: str
    date_hint: str
    text: str
    order: int
    global_order: int
    image_only: bool = False


@dataclasses.dataclass
class ExtractResult:
    events: List[dict]
    knowledge_strict: List[dict]
    knowledge_core: List[dict]
    knowledge_related: List[dict]
    knowledge_signal: List[dict]
    knowledge_all: List[dict]
    candidates_debug: List[dict]
    knowledge_from_events: List[dict]
    noise_chunks: List[dict]
    dropped_knowledge_debug: List[dict]


# ==================== 基础函数 ====================
def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def sha_uid(*parts: str, n: int = 12) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update((p or "").encode("utf-8", errors="ignore"))
        h.update(b"\x1f")
    return h.hexdigest()[:n]


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def write_jsonl(path: Path, rows: Iterable[dict]) -> None:
    ensure_dir(path.parent)
    try:
        rows_list = list(rows)  # 转为列表，避免迭代器问题
        with path.open("w", encoding="utf-8") as f:
            for r in rows_list:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    except Exception as e:
        print(f"[write_jsonl ERROR] 写入 {path} 失败: {repr(e)}")
        raise  # 重新抛出，让外层捕获并打印

def read_json_or_jsonl(path: Path) -> List[dict]:
    txt = path.read_text(encoding="utf-8", errors="ignore").strip()
    if not txt:
        return []
    if txt.startswith("["):
        data = json.loads(txt)
        if isinstance(data, list):
            return data
        return [data]
    out: List[dict] = []
    for line in txt.splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def compact_spaces(s: str) -> str:
    s = s.replace("\u00a0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s+\n", "\n", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ==================== HTML -> lines ====================
_IMG_RE = re.compile(r"""<img\b[^>]*?\bsrc\s*=\s*["']([^"']+)["'][^>]*>""", re.I)
_TAG_RE = re.compile(r"<[^>]+>")


def html_to_lines(detail_html: str) -> List[str]:
    if not detail_html:
        return []
    s = detail_html
    s = s.replace("</p>", "</p>\n")
    s = s.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    s = s.replace("</div>", "</div>\n")
    s = s.replace("</li>", "</li>\n")

    lines: List[str] = []
    parts: List[str] = []
    last = 0
    for m in _IMG_RE.finditer(s):
        if m.start() > last:
            parts.append(s[last:m.start()])
        parts.append(f"[IMAGE] {m.group(1)}")
        last = m.end()
    if last < len(s):
        parts.append(s[last:])

    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("[IMAGE] "):
            lines.append(part)
            continue

        t = _TAG_RE.sub("", part)
        t = html.unescape(t)
        for ln in t.splitlines():
            ln = ln.strip()
            if not ln:
                lines.append("[PARA_BREAK]")
                continue
            lines.append(ln)

    cleaned: List[str] = []
    prev_break = False
    for ln in lines:
        if ln == "[PARA_BREAK]":
            if not prev_break:
                cleaned.append(ln)
                prev_break = True
        else:
            cleaned.append(ln)
            prev_break = False
    return cleaned


# ==================== 标题 / 日期 / 图片 ====================
HEADING_RE = re.compile(r"^(?:(?:[一二三四五六七八九十]+、)|(?:\d+[\.\、]))\s*(.+)$")
DATE_VARIANTS_RE = re.compile(
    r"^(?P<date>"
    r"(?:\d{4})年\s*(?:\d{1,2})月\s*(?:\d{1,2})日?"
    r"|(?:\d{4})[-/](?:\d{1,2})[-/](?:\d{1,2})"
    r"|(?:\d{1,2})月\s*(?:\d{1,2})日"
    r"|(?:\d{4})年\s*(?:\d{1,2})月"
    r")"
    r"\s*[:：]?\s*(?:\([^)]*\))?\s*$",
    re.ASCII,
)


def heading_title(line: str) -> str:
    m = HEADING_RE.match(line)
    if not m:
        return line
    return compact_spaces(m.group(1))


def is_heading(line: str) -> bool:
    if not HEADING_RE.match(line):
        return False
    title = heading_title(line)
    if len(title) > 20:
        return False
    if re.match(r"^\d", title) or re.match(r"^\d+%", title) or re.match(r"^[《（]", title):
        return False
    media_prefixes = ["科创板日报", "路透社", "据消息", "报道称", "业界称"]
    if any(title.startswith(p) for p in media_prefixes):
        return False
    return True


def looks_like_date(line: str) -> bool:
    return bool(DATE_VARIANTS_RE.search(line))


def parse_date_raw(line: str, last_year: Optional[int]) -> Tuple[Optional[str], Optional[int]]:
    line = line.strip()
    m = DATE_VARIANTS_RE.search(line)
    if not m:
        return (None, last_year)
    date_str = m.group("date")

    m_ymd = re.match(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日?", date_str)
    if m_ymd:
        y = int(m_ymd.group(1))
        mm = int(m_ymd.group(2))
        dd = int(m_ymd.group(3))
        return (f"{y:04d}-{mm:02d}-{dd:02d}", y)

    m_ymd_dash = re.match(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", date_str)
    if m_ymd_dash:
        y = int(m_ymd_dash.group(1))
        mm = int(m_ymd_dash.group(2))
        dd = int(m_ymd_dash.group(3))
        return (f"{y:04d}-{mm:02d}-{dd:02d}", y)

    m_md = re.match(r"(\d{1,2})月\s*(\d{1,2})日", date_str)
    if m_md and last_year is not None:
        mm = int(m_md.group(1))
        dd = int(m_md.group(2))
        y = last_year
        return (f"{y:04d}-{mm:02d}-{dd:02d}", y)

    m_ym = re.match(r"(\d{4})年\s*(\d{1,2})月", date_str)
    if m_ym:
        y = int(m_ym.group(1))
        mm = int(m_ym.group(2))
        return (f"{y:04d}-{mm:02d}-01", y)

    return (None, last_year)


def is_image(line: str) -> bool:
    return line.startswith("[IMAGE] ")


def looks_like_event_start(line: str) -> bool:
    if looks_like_date(line):
        return True
    if re.match(r"^(公告|报道称|消息称|据悉|数据显示|文件显示|通知)", line):
        return True
    if re.search(r"(发布|披露)[了：:，, ]", line):
        return True
    return False


def default_knowledge_start_patterns() -> List[str]:
    return [
        "产业链介绍", "核心环节", "关键技术", "相关公司", "龙头企业", "上下游",
        "投资逻辑", "行业概览", "发展历程", "市场格局",
        "题材逻辑", "逻辑梳理", "应用领域", "受益方向", "核心驱动",
        "赛道介绍", "行业解析", "产业图谱", "概念解析", "定义",
    ]


# ==================== 分段 / 切块 ====================
def split_into_sections(lines: List[str]) -> List[DetailSection]:
    sections: List[DetailSection] = []
    current_heading = "无标题"
    start_idx = 0

    for i, line in enumerate(lines):
        if is_heading(line):
            if i > start_idx:
                sections.append(
                    DetailSection(
                        heading=current_heading,
                        lines=lines[start_idx:i],
                        section_type="unknown",
                        start_idx=start_idx,
                        end_idx=i,
                    )
                )
            current_heading = heading_title(line)
            start_idx = i + 1

    if start_idx < len(lines):
        sections.append(
            DetailSection(
                heading=current_heading,
                lines=lines[start_idx:],
                section_type="unknown",
                start_idx=start_idx,
                end_idx=len(lines),
            )
        )
    return sections


def build_event_chunks_from_section(
    section: DetailSection,
    subject: SubjectDetail,
    global_order_start: int,
) -> Tuple[List[DetailChunk], int]:
    chunks: List[DetailChunk] = []
    last_year = None
    cur_anchor = ""
    cur_date_raw = ""
    cur_text_parts: List[str] = []
    chunk_order = 0
    global_order = global_order_start

    def flush() -> None:
        nonlocal cur_anchor, cur_date_raw, cur_text_parts, chunk_order, global_order
        if cur_anchor and cur_text_parts:
            text = compact_spaces("\n".join(cur_text_parts))
            chunk_id = sha_uid(subject.subject_id, "event_area", section.heading, cur_anchor, text)
            chunks.append(
                DetailChunk(
                    chunk_id=chunk_id,
                    subject_id=subject.subject_id,
                    subject_name=subject.name,
                    source_id=subject.source_id,
                    area="event_area",
                    context_heading=section.heading,
                    date_hint=cur_date_raw,
                    text=text,
                    order=chunk_order,
                    global_order=global_order,
                )
            )
            chunk_order += 1
            global_order += 1
        cur_anchor = ""
        cur_date_raw = ""
        cur_text_parts = []

    for line in section.lines:
        if line == "[PARA_BREAK]" or is_image(line):
            continue
        if looks_like_event_start(line):
            flush()
            cur_anchor = line
            cur_date_raw = line if looks_like_date(line) else ""
            _, last_year = parse_date_raw(line, last_year)
        elif cur_anchor:
            cur_text_parts.append(line)

    flush()
    return chunks, global_order


def build_knowledge_chunks_from_section(
    section: DetailSection,
    subject: SubjectDetail,
    global_order_start: int,
) -> Tuple[List[DetailChunk], int]:
    chunks: List[DetailChunk] = []
    cur_text_parts: List[str] = []
    chunk_order = 0
    global_order = global_order_start

    def flush() -> None:
        nonlocal cur_text_parts, chunk_order, global_order
        if cur_text_parts:
            if all(p == "[IMAGE]" for p in cur_text_parts):
                image_only = True
                text = ""
            else:
                image_only = False
                text = compact_spaces("\n".join([p for p in cur_text_parts if p != "[IMAGE]"]))

            chunk_id = sha_uid(
                subject.subject_id,
                "knowledge_area",
                section.heading,
                "",
                text if not image_only else "[IMAGE_ONLY]",
            )
            chunks.append(
                DetailChunk(
                    chunk_id=chunk_id,
                    subject_id=subject.subject_id,
                    subject_name=subject.name,
                    source_id=subject.source_id,
                    area="knowledge_area",
                    context_heading=section.heading,
                    date_hint="",
                    text=text,
                    order=chunk_order,
                    global_order=global_order,
                    image_only=image_only,
                )
            )
            chunk_order += 1
            global_order += 1
            cur_text_parts = []

    for line in section.lines:
        if line == "[PARA_BREAK]":
            flush()
            continue
        if is_image(line):
            cur_text_parts.append("[IMAGE]")
        elif line.strip():
            cur_text_parts.append(line)

    flush()
    return chunks, global_order


# ==================== 查找题材记录 ====================
def find_subject_detail_record(data_dir: Path, subject_id: str) -> SubjectDetail:
    subject_id_str = str(subject_id)
    candidates: List[Path] = []

    for ext in (".jsonl", ".json"):
        for p in data_dir.rglob(f"*{subject_id_str}*{ext}"):
            candidates.append(p)

    candidates.sort(key=lambda x: (len(x.name), x.stat().st_size if x.exists() else 10**18))

    print(f"  找到 {len(candidates)} 个包含 ID {subject_id_str} 的候选文件")

    def record_from_obj(obj: dict, sid: str) -> Optional[SubjectDetail]:
        id_fields = ["subjectId", "subject_id", "bizKey", "biz_key", "id", "ID", "subjectID"]
        found_id = None
        for field in id_fields:
            val = obj.get(field)
            if val is not None:
                found_id = str(val)
                break
        if found_id != sid:
            return None

        detail_html = obj.get("detail") or obj.get("detail_html") or obj.get("content") or ""
        if not detail_html:
            return None

        name = obj.get("name") or obj.get("subjectName") or obj.get("subject_name") or ""
        reason = obj.get("reason") or ""
        source_id = obj.get("source_id") or obj.get("sourceId") or f"detail_{sid}_0"

        return SubjectDetail(
            subject_id=sid,
            name=str(name),
            reason=str(reason),
            detail_html=str(detail_html),
            source_id=str(source_id),
        )

    for p in candidates:
        try:
            rows = read_json_or_jsonl(p)
            if not rows:
                continue
            if isinstance(rows, dict):
                rows = [rows]
            for obj in rows:
                if not isinstance(obj, dict):
                    continue
                if "data" in obj and isinstance(obj["data"], dict):
                    obj = obj["data"]
                rec = record_from_obj(obj, subject_id_str)
                if rec:
                    print(f"    成功从 {p} 找到题材记录")
                    return rec
        except Exception as e:
            print(f"    解析文件 {p} 失败: {e}")

    # 全目录扫描
    print(f"  未在候选文件中找到，开始全目录扫描（最多500个文件）...")
    scanned = 0
    for p in data_dir.rglob("*.jsonl"):
        scanned += 1
        if scanned > 500:
            break
        try:
            rows = read_json_or_jsonl(p)
            if not rows:
                continue
            if isinstance(rows, dict):
                rows = [rows]
            for obj in rows:
                if not isinstance(obj, dict):
                    continue
                if "data" in obj and isinstance(obj["data"], dict):
                    obj = obj["data"]
                rec = record_from_obj(obj, subject_id_str)
                if rec and rec.detail_html:
                    print(f"    成功从 {p} 找到题材记录")
                    return rec
        except Exception:
            continue

    raise FileNotFoundError(
        f"\n无法找到 subject_id={subject_id_str} 的详情 HTML。\n"
        f"已扫描 {len(candidates)} 个候选文件和至少 {scanned} 个全局文件。"
    )


# ==================== LLM Client ====================
class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        config: LLMConfig = LLMConfig(),
        base_url: str = DEEPSEEK_BASE_URL,
        debug_http: bool = False,
        timeout: Tuple[int, int] = (10, 600),
    ):
        self.api_key = api_key
        self.config = config
        self.base_url = base_url.rstrip("/")
        self.debug_http = debug_http
        self.timeout = timeout
        self.sess = requests.Session()

    @staticmethod
    def _extract_json_block_loose(text: str) -> Optional[str]:
        if not text:
            return None
        t = text.strip()
        if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
            return t
        m = re.search(r"(\{[\s\S]*\})", t)
        if m:
            return m.group(1).strip()
        m = re.search(r"(\[[\s\S]*\])", t)
        if m:
            return m.group(1).strip()
        return None

    def run_json_object(
        self,
        messages: List[Dict[str, str]],
        debug_tag: str = "deepseek",
        subject_id: str = "unknown",
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature if temperature is None else float(temperature),
            "max_tokens": self.config.max_tokens if max_tokens is None else int(max_tokens),
            "response_format": {"type": "json_object"},
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        debug_dir = DEBUG_DIR / str(subject_id)
        debug_dir.mkdir(parents=True, exist_ok=True)

        backoff = 1.2
        last_err: Optional[Exception] = None

        for attempt in range(self.config.max_retries + 1):
            try:
                r = self.sess.post(url, headers=headers, json=payload, timeout=self.timeout)
                status = r.status_code
                raw_text = r.text or ""

                if status == 429 or status >= 500:
                    (debug_dir / f"{debug_tag}_http_{status}_attempt{attempt}.txt").write_text(
                        raw_text[:20000], encoding="utf-8"
                    )
                    time.sleep(backoff)
                    backoff = min(backoff * 1.8, 12.0)
                    continue

                r.raise_for_status()
                data = r.json()
                (debug_dir / f"{debug_tag}_raw_json_attempt{attempt}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2)[:200000],
                    encoding="utf-8",
                )

                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise RuntimeError("DeepSeek returned empty message content")

                try:
                    obj = json.loads(content)
                except json.JSONDecodeError:
                    block = self._extract_json_block_loose(content)
                    if not block:
                        raise
                    obj = json.loads(block)

                if isinstance(obj, list):
                    obj = {"items": obj}
                if not isinstance(obj, dict):
                    raise RuntimeError(f"DeepSeek did not return valid json_object: {content[:300]}")

                return obj

            except Exception as e:
                last_err = e
                (debug_dir / f"{debug_tag}_exception_attempt{attempt}.txt").write_text(
                    repr(e), encoding="utf-8"
                )
                if attempt < self.config.max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 1.6, 12.0)
                    continue
                break

        raise RuntimeError(f"DeepSeek run_json_object failed after retries: {repr(last_err)}")


# ==================== Prompt ====================
CHUNK_CLASSIFIER_SYSTEM_PROMPT = """你是一个题材详情页段落分类器。你必须输出合法的 JSON 对象。
你的任务是判断每个段落在题材知识构建中的角色。

给定题材名称和若干段落，请将每个段落分类为以下四类之一：

1. strict_knowledge
- 该段主要用于静态说明题材本身，包括定义、核心构成、结构、关键要素、机制等。
- 必须是纯静态说明，不应包含明确的事件发布、政策出台、公告、时间推进、公司动态等内容。
- 如果段落包含静态知识但同时夹杂事件信息，应优先标为 candidate_mixed，而不是 strict_knowledge。

2. candidate_mixed
- 该段可能包含有价值的知识，但也可能混有事件、新闻、景气数据等。它处于知识候选状态，需要进一步裁决。

3. pure_event
- 该段主要描述某个具体事件、新闻、政策发布、公司公告、业绩、订单、价格变化、市场表现、监管进展、时间性动态等。

4. noise
- 该段是重复、无信息量、媒体来源、纯行情噪音、格式残留、广告性文本或与题材本体无关的内容。

请注意：
- 不要因为段落带有日期就自动判为 pure_event。
- 关键判断标准是：该段是否可能含有可用于题材本体构建的稳定知识。如果有，即使混合事件，也应判为 candidate_mixed。
- 请基于语义理解，而不是机械依赖关键词。

请输出严格 JSON：
{
  "items": [
    {
      "chunk_id": "...",
      "label": "strict_knowledge|candidate_mixed|pure_event|noise",
      "confidence": 0.0,
      "ontology_value": "high|medium|low",
      "reason": "..."
    }
  ]
}"""

KNOWLEDGE_JUDGE_SYSTEM_PROMPT = """你是一个题材知识候选抽取器。给定题材名称和一批已被标记为 candidate_mixed 的段落，请判断其中是否包含可沉淀为题材知识的内容，并进行提取。

你需要为每个段落输出以下 JSON 对象：
{
  "chunk_id": "...",
  "decision": "keep|split|drop",
  "confidence": 0.0,
  "knowledge_value": "high|medium|low",
  "reason": "...",
  "knowledge_spans": [
    {
      "text": "抽取的知识候选片段文本",
      "role": "请用简短中文短语概括该知识片段在当前题材中的语义角色",
      "stability": "high|medium|low"
    }
  ],
  "event_residue": "可选的剩余文本（如事件部分）",
  "drop_target": "event|noise"
}

请注意：
1. 本阶段不要判断 core / related / signal。
2. 只负责抽取“可沉淀的知识候选片段”，不负责最终分层。
3. 不要输出纯碎片、单个名词、无法脱离上下文理解的指代短语。
4. 若段落中同时包含知识与事件，优先使用 split。
5. role 不要使用固定预设枚举，请根据当前题材语义自由概括。

请输出严格 JSON：
{
  "items": [ ... ]
}"""

KNOWLEDGE_CANONICALIZE_SYSTEM_PROMPT = """你是一个题材知识规范化器。给定题材名称、上下文信息以及若干知识候选片段，请将它们整理为最终可入库的题材知识块。

你的任务是：
1. 判断该候选片段是否适合保留；
2. 如有必要，将其改写为更稳定、可脱离原新闻上下文独立成立的知识表达；
3. 最终确认它的 type 和 role；
4. 对无法形成有效知识块的片段直接丢弃。

请输出 JSON：
{
  "items": [
    {
      "span_uid": "...",
      "action": "keep|rewrite|drop",
      "canonical_text": "最终可入库文本；若 drop 则为空字符串",
      "final_type": "core|related|signal",
      "final_role": "请用简短中文短语概括其在当前题材中的语义角色",
      "stability": "high|medium|low",
      "reason": "..."
    }
  ]
}

请严格遵守以下通用本体分层原则：

1. canonical_text 必须是一个相对完整、可独立理解的知识表达，不要输出单个名词、残句、强指代短语。

2. 可以进行去事件化和去新闻口吻改写：
- 去掉不必要的具体公司动作、具体发布日期、新闻口吻、引用口吻；
- 保留对题材知识本身有价值的事实、机制、结构、逻辑、景气信号。

3. 若候选片段本身只是一条事件、公告、预测、主观看法、口号式表述，且无法整理成稳定知识块，则 drop。

4. final_type 的定义：
- core：直接定义当前题材本体，回答“这个题材是什么 / 由什么构成 / 核心机制或核心环节是什么”。
- related：与当前题材高度相关，但不直接定义题材本体，例如关联环节、配套条件、关联技术、关联主体、相关领域信息。
- signal：体现阶段性变化的信息，例如景气变化、供需变化、政策催化、市场规模、产能、商业化推进、技术进展、产业节奏变化。

5. 如果候选片段同时包含本体定义与趋势/政策/进展信息，应按语义重心决定最终类型；必要时优先保留更稳定、更独立成立的那一部分表达。

6. final_role 不要使用固定预设枚举，请根据当前题材语义给出简短中文短语。

请输出严格 JSON：
{
  "items": [ ... ]
}"""


# ==================== 缓存 ====================
def get_chunk_cache_key(chunk: DetailChunk, model_name: str, stage: str = "classify") -> str:
    content = (
        f"{PROMPT_VERSION}|{model_name}|{stage}|{chunk.subject_id}|{chunk.subject_name}|"
        f"{chunk.area}|{chunk.context_heading}|{chunk.date_hint}|{chunk.text}|{int(chunk.image_only)}"
    )
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_cached_result(chunk: DetailChunk, model_name: str, stage: str = "classify") -> Optional[dict]:
    cache_key = get_chunk_cache_key(chunk, model_name, stage)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("prompt_version") == PROMPT_VERSION and data.get("model") == model_name:
                res = data.get("result")
                if isinstance(res, dict) and "is_fallback" not in res:
                    res["is_fallback"] = False
                return res
        except Exception:
            pass
    return None


def save_cached_result(chunk: DetailChunk, result: dict, model_name: str, stage: str = "classify") -> None:
    cache_key = get_chunk_cache_key(chunk, model_name, stage)
    cache_file = CACHE_DIR / f"{cache_key}.json"
    data = {
        "prompt_version": PROMPT_VERSION,
        "model": model_name,
        "timestamp": now_iso(),
        "result": result,
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ==================== 第三层规范化缓存 ====================
def get_canonicalize_cache_key(subject_id: str, subject_name: str, span: dict, model_name: str) -> str:
    content = f"{PROMPT_VERSION}|{model_name}|{subject_id}|{subject_name}|{span['span_uid']}|{span['text']}|{span.get('role','')}"
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def load_canonicalize_cache(subject_id: str, subject_name: str, span: dict, model_name: str) -> Optional[dict]:
    key = get_canonicalize_cache_key(subject_id, subject_name, span, model_name)
    cache_file = CACHE_DIR / f"canonicalize_{key}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            if data.get("prompt_version") == PROMPT_VERSION and data.get("model") == model_name:
                return data.get("result")
        except Exception:
            pass
    return None


def save_canonicalize_cache(subject_id: str, subject_name: str, span: dict, result: dict, model_name: str) -> None:
    key = get_canonicalize_cache_key(subject_id, subject_name, span, model_name)
    cache_file = CACHE_DIR / f"canonicalize_{key}.json"
    data = {
        "prompt_version": PROMPT_VERSION,
        "model": model_name,
        "timestamp": now_iso(),
        "result": result,
    }
    cache_file.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


# ==================== 结果标准化 ====================
def normalize_classification_item(item: dict, valid_chunk_ids: Set[str]) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    chunk_id = str(item.get("chunk_id") or "").strip()
    if not chunk_id or chunk_id not in valid_chunk_ids:
        return None

    label = str(item.get("label") or "").strip()
    if label not in VALID_LABELS:
        label = None

    try:
        confidence = float(item.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    ontology_value = str(item.get("ontology_value") or "low").strip().lower()
    if ontology_value not in VALID_ONTOLOGY:
        ontology_value = "low"

    reason = str(item.get("reason") or "").strip()[:500]

    return {
        "chunk_id": chunk_id,
        "label": label,
        "confidence": confidence,
        "ontology_value": ontology_value,
        "reason": reason,
    }


def normalize_judge_item(item: dict, valid_chunk_ids: Set[str]) -> Optional[dict]:
    if not isinstance(item, dict):
        return None

    chunk_id = str(item.get("chunk_id") or "").strip()
    if not chunk_id or chunk_id not in valid_chunk_ids:
        return None

    decision = str(item.get("decision") or "").strip()
    if decision not in VALID_DECISIONS:
        return None

    try:
        confidence = float(item.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    knowledge_value = str(item.get("knowledge_value") or "low").strip().lower()
    if knowledge_value not in VALID_ONTOLOGY:
        knowledge_value = "low"

    reason = str(item.get("reason") or "").strip()[:500]

    raw_spans = item.get("knowledge_spans", [])
    if not isinstance(raw_spans, list):
        raw_spans = []

    knowledge_spans = []
    for span in raw_spans:
        if not isinstance(span, dict):
            continue
        text = str(span.get("text") or "").strip()
        if not text:
            continue
        role = str(span.get("role") or "").strip() or "unspecified"
        stability = str(span.get("stability") or "low").strip().lower()
        if stability not in ("high", "medium", "low"):
            stability = "low"
        knowledge_spans.append({
            "text": text,
            "role": role,
            "stability": stability,
        })

    event_residue = item.get("event_residue", "")
    if not isinstance(event_residue, str):
        event_residue = ""

    drop_target = item.get("drop_target", "noise")
    if drop_target not in ("event", "noise"):
        drop_target = "noise"

    return {
        "chunk_id": chunk_id,
        "decision": decision,
        "confidence": confidence,
        "knowledge_value": knowledge_value,
        "reason": reason,
        "knowledge_spans": knowledge_spans,
        "event_residue": event_residue,
        "drop_target": drop_target,
    }


# ==================== 分批 ====================
def make_batches_by_chars(
    items: List[Any],
    max_chars: int = BATCH_MAX_CHARS,
    max_items: int = BATCH_MAX_ITEMS,
    get_text: Optional[callable] = None,
) -> List[List[Any]]:
    """
    将 items 按字符数和条目数分批。
    若提供 get_text 函数，则使用它获取每个 item 的文本长度；否则尝试使用 item.text 或直接转为字符串。
    """
    batches: List[List[Any]] = []
    cur: List[Any] = []
    cur_chars = 0

    def text_len(item: Any) -> int:
        if get_text:
            return len(get_text(item))
        if hasattr(item, "text"):
            return len(item.text)
        return len(str(item))

    for item in items:
        item_len = text_len(item) + 100  # 加一些余量
        if cur and (len(cur) >= max_items or cur_chars + item_len > max_chars):
            batches.append(cur)
            cur = []
            cur_chars = 0
        cur.append(item)
        cur_chars += item_len

    if cur:
        batches.append(cur)
    return batches


# ==================== 第一层分类 ====================
def classify_chunks_with_llm(ds: DeepSeekClient, subject_name: str, chunks: List[DetailChunk]) -> List[dict]:
    text_chunks = [c for c in chunks if not c.image_only]
    if not text_chunks:
        return []

    batches = make_batches_by_chars(text_chunks)
    all_results: List[dict] = []
    valid_chunk_ids = {c.chunk_id for c in text_chunks}
    subject_id = text_chunks[0].subject_id

    for batch in tqdm(batches, desc="LLM 分类批次", unit="batch"):
        input_items = [
            {
                "chunk_id": c.chunk_id,
                "area": c.area,
                "context_heading": c.context_heading,
                "date_hint": c.date_hint,
                "text": c.text,
            }
            for c in batch
        ]

        user_prompt = (
            f"题材名称：{subject_name}\n\n"
            f"下面是该题材详情页中的若干段落。请逐条判断每个段落的角色。\n\n"
            f"{json.dumps(input_items, ensure_ascii=False, indent=2)}"
        )

        messages = [
            {"role": "system", "content": CHUNK_CLASSIFIER_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = ds.run_json_object(
                messages,
                debug_tag="chunk_classify",
                subject_id=subject_id,
            )
            raw_items = response.get("items", [])
            seen = set()
            clean_items = []
            for raw in raw_items:
                norm = normalize_classification_item(raw, valid_chunk_ids)
                if not norm:
                    continue
                if norm["chunk_id"] in seen:
                    continue
                seen.add(norm["chunk_id"])
                clean_items.append(norm)
            all_results.extend(clean_items)
        except Exception as e:
            print(f"分类批次失败: {e}")

    result_map = {r["chunk_id"]: r for r in all_results}
    final_results: List[dict] = []
    for c in text_chunks:
        if c.chunk_id in result_map:
            final_results.append(result_map[c.chunk_id])
        else:
            label = "candidate_mixed" if c.area == "knowledge_area" else "pure_event"
            final_results.append({
                "chunk_id": c.chunk_id,
                "label": label,
                "confidence": 0.5,
                "ontology_value": "low",
                "reason": "fallback: missing from LLM response",
                "is_fallback": True,
            })
    return final_results


# ==================== 第二层：只抽候选，不判 type ====================
def judge_candidate_mixed(
    ds: DeepSeekClient,
    subject_name: str,
    candidate_blocks: List[dict],
    chunks_map: Dict[str, DetailChunk],
    force_refresh: bool = False,
) -> List[dict]:
    if not candidate_blocks:
        return []

    valid_chunk_ids = {b["chunk_id"] for b in candidate_blocks if "chunk_id" in b}
    subject_id = candidate_blocks[0]["subject_id"]
    result_map: Dict[str, dict] = {}
    uncached_pairs: List[Tuple[DetailChunk, dict]] = []

    for block in candidate_blocks:
        chunk = chunks_map.get(block["chunk_id"])
        if not chunk:
            continue
        if not force_refresh:
            cached = load_cached_result(chunk, ds.config.model, stage="judge")
            if cached:
                norm = normalize_judge_item(cached, valid_chunk_ids)
                if norm:
                    result_map[chunk.chunk_id] = norm
                continue
        uncached_pairs.append((chunk, block))

    if uncached_pairs:
        uncached_map = {chunk.chunk_id: (chunk, block) for chunk, block in uncached_pairs}
        judge_chunks = [pair[0] for pair in uncached_pairs]
        batches = make_batches_by_chars(judge_chunks, max_chars=3000, max_items=5)

        for batch in tqdm(batches, desc="知识裁决批次", unit="batch"):
            input_items = [
                {
                    "chunk_id": c.chunk_id,
                    "text": c.text,
                    "context_heading": c.context_heading,
                    "date_hint": c.date_hint,
                }
                for c in batch
            ]

            user_prompt = (
                f"题材名称：{subject_name}\n\n"
                f"以下是已被初步识别为 candidate_mixed 的段落，请对每个段落进行知识候选抽取。\n\n"
                f"{json.dumps(input_items, ensure_ascii=False, indent=2)}"
            )
            messages = [
                {"role": "system", "content": KNOWLEDGE_JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]

            try:
                response = ds.run_json_object(
                    messages,
                    debug_tag="knowledge_judge",
                    subject_id=subject_id,
                )
                raw_items = response.get("items", [])
                if not raw_items and "chunk_id" in response:
                    raw_items = [response]

                seen = set()
                for raw in raw_items:
                    norm = normalize_judge_item(raw, valid_chunk_ids)
                    if not norm:
                        continue
                    chunk_id = norm["chunk_id"]
                    if chunk_id in seen:
                        continue
                    seen.add(chunk_id)
                    result_map[chunk_id] = norm
                    if chunk_id in uncached_map:
                        chunk, _ = uncached_map[chunk_id]
                        save_cached_result(chunk, norm, ds.config.model, stage="judge")
            except Exception as e:
                print(f"裁决批次失败: {e}")

    judged_results: List[dict] = []
    for block in candidate_blocks:
        chunk_id = block["chunk_id"]
        if chunk_id in result_map:
            merged = block.copy()
            merged.update(result_map[chunk_id])
        else:
            merged = block.copy()
            merged.update({
                "decision": "drop",
                "confidence": 0.5,
                "knowledge_value": "low",
                "reason": "fallback: missing from judge response",
                "knowledge_spans": [],
                "event_residue": "",
                "drop_target": "noise",
            })
        judged_results.append(merged)

    return judged_results


# ==================== 路由 ====================
def route_chunks_by_role(
    chunks: List[DetailChunk],
    classification_results: Dict[str, dict],
    created_at: str,
) -> Tuple[List[dict], List[dict], List[dict], List[dict], Dict[str, str]]:
    strict_blocks: List[dict] = []
    candidate_blocks: List[dict] = []
    pure_events: List[dict] = []
    noise_chunks: List[dict] = []
    final_bucket_map: Dict[str, str] = {}

    for chunk in chunks:
        if chunk.image_only:
            if chunk.area == "knowledge_area":
                strict_blocks.append({
                    "subject_id": chunk.subject_id,
                    "chunk_id": chunk.chunk_id,
                    "area": chunk.area,
                    "context_heading": chunk.context_heading,
                    "date_hint": chunk.date_hint,
                    "global_order": chunk.global_order,
                    "text": "[IMAGE]",
                    "source": "knowledge_image_placeholder",
                    "created_at": created_at,
                    "source_id": chunk.source_id,
                    "order": chunk.order,
                    "used_fallback": True,
                    "uid": sha_uid(chunk.subject_id, "image_only"),
                })
                final_bucket_map[chunk.chunk_id] = "strict_knowledge"
            else:
                noise_chunks.append({
                    "subject_id": chunk.subject_id,
                    "chunk_id": chunk.chunk_id,
                    "area": chunk.area,
                    "context_heading": chunk.context_heading,
                    "date_hint": chunk.date_hint,
                    "global_order": chunk.global_order,
                    "text": "[IMAGE]",
                    "image_only": True,
                    "label": "noise",
                    "confidence": 0.0,
                    "created_at": created_at,
                    "source_id": chunk.source_id,
                    "order": chunk.order,
                    "used_fallback": True,
                })
                final_bucket_map[chunk.chunk_id] = "noise"
            continue

        res = classification_results.get(chunk.chunk_id)
        if not res or res.get("label") is None or res.get("is_fallback") is True:
            used_fallback = True
            label = "candidate_mixed" if chunk.area == "knowledge_area" else "pure_event"
            conf = 0.5
        else:
            used_fallback = False
            label = res["label"]
            conf = res.get("confidence", 0.0)

        def make_block(source_type: str, **kwargs: Any) -> dict:
            block = {
                "subject_id": chunk.subject_id,
                "chunk_id": chunk.chunk_id,
                "area": chunk.area,
                "context_heading": chunk.context_heading,
                "date_hint": chunk.date_hint,
                "global_order": chunk.global_order,
                "source": source_type,
                "created_at": created_at,
                "source_id": chunk.source_id,
                "order": chunk.order,
                "used_fallback": used_fallback,
            }
            block.update(kwargs)
            return block

        if used_fallback:
            text_len = len(chunk.text.strip())
            if text_len == 0 or text_len < FALLBACK_MIN_TEXT_LEN:
                noise_chunks.append({
                    "subject_id": chunk.subject_id,
                    "chunk_id": chunk.chunk_id,
                    "area": chunk.area,
                    "context_heading": chunk.context_heading,
                    "date_hint": chunk.date_hint,
                    "global_order": chunk.global_order,
                    "text": chunk.text,
                    "image_only": False,
                    "label": label,
                    "confidence": conf,
                    "created_at": created_at,
                    "source_id": chunk.source_id,
                    "order": chunk.order,
                    "used_fallback": used_fallback,
                })
                final_bucket_map[chunk.chunk_id] = "noise"
            elif chunk.area == "knowledge_area":
                candidate_blocks.append(make_block(
                    source_type="candidate_mixed",
                    title=chunk.context_heading,
                    text=chunk.text,
                    uid=sha_uid(chunk.subject_id, chunk.text),
                ))
                final_bucket_map[chunk.chunk_id] = "candidate_mixed"
            else:
                pure_events.append(make_block(
                    source_type="detail_html",
                    event_date_raw=chunk.date_hint,
                    text=chunk.text,
                ))
                final_bucket_map[chunk.chunk_id] = "pure_event"

        elif label == "strict_knowledge" and conf >= STRICT_KNOWLEDGE_MIN_CONF:
            if chunk.area == "knowledge_area":
                strict_blocks.append(make_block(
                    source_type="strict_knowledge",
                    title=chunk.context_heading,
                    text=chunk.text,
                    uid=sha_uid(chunk.subject_id, chunk.text),
                ))
                final_bucket_map[chunk.chunk_id] = "strict_knowledge"
            else:
                candidate_blocks.append(make_block(
                    source_type="candidate_mixed",
                    title=chunk.context_heading,
                    text=chunk.text,
                    uid=sha_uid(chunk.subject_id, chunk.text),
                ))
                final_bucket_map[chunk.chunk_id] = "candidate_mixed"

        elif label == "candidate_mixed" and conf >= CANDIDATE_MIXED_MIN_CONF:
            candidate_blocks.append(make_block(
                source_type="candidate_mixed",
                title=chunk.context_heading,
                text=chunk.text,
                uid=sha_uid(chunk.subject_id, chunk.text),
            ))
            final_bucket_map[chunk.chunk_id] = "candidate_mixed"

        elif label == "pure_event" and conf >= PURE_EVENT_MIN_CONF:
            pure_events.append(make_block(
                source_type="detail_html",
                event_date_raw=chunk.date_hint,
                text=chunk.text,
            ))
            final_bucket_map[chunk.chunk_id] = "pure_event"

        else:
            noise_chunks.append({
                "subject_id": chunk.subject_id,
                "chunk_id": chunk.chunk_id,
                "area": chunk.area,
                "context_heading": chunk.context_heading,
                "date_hint": chunk.date_hint,
                "global_order": chunk.global_order,
                "text": chunk.text,
                "image_only": False,
                "label": label,
                "confidence": conf,
                "created_at": created_at,
                "source_id": chunk.source_id,
                "order": chunk.order,
                "used_fallback": used_fallback,
            })
            final_bucket_map[chunk.chunk_id] = "noise"

    return strict_blocks, candidate_blocks, pure_events, noise_chunks, final_bucket_map


# ==================== 非语义清洗/门禁 ====================
def clean_text_basic(text: str) -> str:
    text = compact_spaces(text)
    text = re.sub(r"^\d{1,2}月\d{1,2}日电[，,]\s*", "", text)
    text = re.sub(r"^据[^，,。；;]{1,20}[，,]\s*", "", text)
    text = re.sub(r"^[《<【][^，,。]{1,20}[》>】]\d*日讯[，,]\s*", "", text)
    text = re.sub(r"^(消息人士称|业内人士表示|业内称|报告指出)[，,]\s*", "", text)
    return text.strip()


def looks_like_real_event_text(text: str) -> bool:
    text = clean_text_basic(text)
    return len(text) >= EVENT_RESIDUE_MIN_LEN


def validate_knowledge_text(text: str) -> Tuple[bool, str]:
    t = compact_spaces(text)
    if not t:
        return False, "empty"
    if len(t) < MIN_KNOWLEDGE_LEN:
        return False, "too_short"
    if re.match(r"^(这|该|上述|这些|其|此|这一|该项|这项)", t):
        return False, "deictic"
    if len(t) <= 6 and not re.search(r"[，。；：:,、]", t):
        return False, "fragment"
    return True, "ok"


def dedup_knowledge_by_priority(entries: List[dict]) -> List[dict]:
    best: Dict[str, dict] = {}
    for e in entries:
        txt = compact_spaces(e.get("text", ""))
        if not txt:
            continue
        old = best.get(txt)
        if old is None:
            best[txt] = e
            continue
        old_p = TYPE_PRIORITY.get(old.get("knowledge_type", "signal"), 1)
        new_p = TYPE_PRIORITY.get(e.get("knowledge_type", "signal"), 1)
        if new_p > old_p:
            best[txt] = e
    return list(best.values())


def make_knowledge_entry(
    source_block: dict,
    source_type: str,
    text: str,
    role: str = "",
    stability: str = "low",
    knowledge_type: str = "signal",
    parent_chunk_id: Optional[str] = None,
    **extra: Any,
) -> dict:
    base_parent = parent_chunk_id or source_block.get("chunk_id", "")
    chunk_id = sha_uid(source_block["subject_id"], base_parent, source_type, text)
    uid = sha_uid(source_block["subject_id"], source_type, text)
    entry = {
        "subject_id": source_block["subject_id"],
        "chunk_id": chunk_id,
        "parent_chunk_id": base_parent,
        "area": source_block.get("area"),
        "context_heading": source_block.get("context_heading"),
        "date_hint": source_block.get("date_hint"),
        "global_order": source_block.get("global_order"),
        "source": source_type,
        "text": text,
        "role": role,
        "stability": stability,
        "knowledge_type": knowledge_type,
        "created_at": source_block.get("created_at"),
        "source_id": source_block.get("source_id"),
        "order": source_block.get("order"),
        "uid": uid,
    }
    entry.update(extra)
    return entry


# ==================== 第三层规范化（带缓存） ====================
def canonicalize_knowledge_spans_with_llm(
    ds: DeepSeekClient,
    subject_name: str,
    span_items: List[dict],
    subject_id: str,
) -> List[dict]:
    if not span_items:
        return []

    # 先尝试从缓存加载
    cached_results = []
    uncached_spans = []
    for span in span_items:
        cached = load_canonicalize_cache(subject_id, subject_name, span, ds.config.model)
        if cached is not None:
            cached_results.append(cached)
        else:
            uncached_spans.append(span)

    if uncached_spans:
        valid_uids = {span["span_uid"] for span in uncached_spans}
        # 分批处理未缓存的 spans
        batches = make_batches_by_chars(
            uncached_spans,
            max_chars=3500,
            max_items=6,
            get_text=lambda s: s.get("text", "")
        )
        new_results = []
        for batch in batches:
            user_prompt = (
                f"题材名称：{subject_name}\n\n"
                f"下面是待规范化的知识候选片段，请逐条处理：\n\n"
                f"{json.dumps(batch, ensure_ascii=False, indent=2)}"
            )
            messages = [
                {"role": "system", "content": KNOWLEDGE_CANONICALIZE_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ]
            try:
                response = ds.run_json_object(
                    messages,
                    max_tokens=2500,
                    temperature=0.1,
                    debug_tag="knowledge_canonicalize",
                    subject_id=subject_id,
                )
                raw_items = response.get("items", [])
                if isinstance(raw_items, list):
                    for item in raw_items:
                        if not isinstance(item, dict):
                            continue
                        span_uid = str(item.get("span_uid") or "").strip()
                        if span_uid in valid_uids:
                            new_results.append(item)
                            # 保存到缓存
                            orig_span = next((s for s in uncached_spans if s["span_uid"] == span_uid), None)
                            if orig_span:
                                save_canonicalize_cache(subject_id, subject_name, orig_span, item, ds.config.model)
            except Exception as e:
                print(f"知识规范化批次失败: {e}")
        final_results = cached_results + new_results
    else:
        final_results = cached_results

    return final_results


# ==================== 事件蒸馏 ====================
def event_sort_key(ev: dict) -> str:
    d_raw = str(ev.get("event_date_raw") or "").strip()
    d_iso, _ = parse_date_raw(d_raw, None)
    return d_iso or "0000-00-00"


def best_title_from_text(text: str, fallback: str, max_len: int = 18) -> str:
    t = compact_spaces(text)
    if not t:
        return fallback
    seg = re.split(r"[。；;！!？?\n]", t, maxsplit=1)[0].strip()
    if len(seg) <= max_len:
        return seg or fallback
    return seg[:max_len] + "…"


def distill_events_to_knowledge(
    events: List[dict],
    subject: SubjectDetail,
    created_at: str,
    max_events: int = 10,
) -> List[dict]:
    out: List[dict] = []
    order = 0
    last_year = None
    seen_texts = set()

    sorted_events = sorted(events, key=event_sort_key, reverse=True)[:max_events]
    for ev in sorted_events:
        d_raw = str(ev.get("event_date_raw") or "").strip()
        text = str(ev.get("text") or "").strip()
        if not text or text in seen_texts:
            continue
        seen_texts.add(text)

        date_iso, last_year = parse_date_raw(d_raw, last_year)
        date_tag = date_iso or d_raw or "unknown-date"
        cat = best_title_from_text(text, "事件")
        title = f"{cat}（{date_tag}）" if date_tag else cat
        uid = sha_uid(subject.subject_id, title, text)

        out.append({
            "subject_id": subject.subject_id,
            "title": title,
            "text": compact_spaces(text),
            "source": "events_distill",
            "created_at": created_at,
            "source_id": "hybrid",
            "order": order,
            "uid": uid,
        })
        order += 1

    return out


# ==================== 主流程 ====================
def build_for_subject(
    ds: DeepSeekClient,
    data_dir: Path,
    subject_id: str,
    mode: str,
    debug: bool,
    force_refresh: bool = False,
) -> ExtractResult:
    subj = find_subject_detail_record(data_dir, subject_id)
    created_at = now_iso()
    lines = html_to_lines(subj.detail_html)

    if debug:
        reason_lines = [x.strip() for x in (subj.reason or "").splitlines() if x.strip()]
        head = (reason_lines[0] if reason_lines else "")[:80]
        print(f"[{subj.subject_id}] reason_lines={len(reason_lines)} head={head}")
        print(f"[{subj.subject_id}] lines={len(lines)} source_id={subj.source_id}")

    sections = split_into_sections(lines)

    knowledge_patterns = default_knowledge_start_patterns()
    for sec in sections:
        if any(kw in sec.heading for kw in knowledge_patterns):
            sec.section_type = "knowledge"
        else:
            has_event_start = False
            for line in sec.lines:
                if line == "[PARA_BREAK]" or is_image(line):
                    continue
                if looks_like_event_start(line):
                    has_event_start = True
                    break
            sec.section_type = "event" if has_event_start else "unknown"

    global_order = 0
    event_chunks: List[DetailChunk] = []
    knowledge_chunks: List[DetailChunk] = []

    for sec in sections:
        if sec.section_type == "event":
            chks, global_order = build_event_chunks_from_section(sec, subj, global_order)
            event_chunks.extend(chks)
        else:
            chks, global_order = build_knowledge_chunks_from_section(sec, subj, global_order)
            knowledge_chunks.extend(chks)

    all_chunks = event_chunks + knowledge_chunks

    text_chunks: List[DetailChunk] = []
    image_chunks: List[DetailChunk] = []
    for chunk in all_chunks:
        if chunk.image_only:
            image_chunks.append(chunk)
        else:
            text_chunks.append(chunk)

    classification_results: Dict[str, dict] = {}
    for chunk in image_chunks:
        if chunk.area == "knowledge_area":
            classification_results[chunk.chunk_id] = {
                "label": "strict_knowledge",
                "confidence": 0.5,
                "ontology_value": "low",
                "reason": "image_only",
                "is_fallback": True,
            }
        else:
            classification_results[chunk.chunk_id] = {
                "label": "noise",
                "confidence": 0.0,
                "ontology_value": "low",
                "reason": "image_only",
                "is_fallback": True,
            }

    uncached_chunks: List[DetailChunk] = []
    for chunk in text_chunks:
        if force_refresh:
            uncached_chunks.append(chunk)
        else:
            cached = load_cached_result(chunk, ds.config.model, stage="classify")
            if cached:
                classification_results[chunk.chunk_id] = cached
            else:
                uncached_chunks.append(chunk)

    if uncached_chunks:
        print(f"  调用 LLM 分类 {len(uncached_chunks)} 个未缓存块")
        new_results = classify_chunks_with_llm(ds, subj.name, uncached_chunks)
        for res in new_results:
            chunk_id = res["chunk_id"]
            classification_results[chunk_id] = res
            for chunk in uncached_chunks:
                if chunk.chunk_id == chunk_id:
                    save_cached_result(chunk, res, ds.config.model, stage="classify")
                    break

    strict_blocks, candidate_blocks, pure_events, noise_chunks, final_bucket_map = route_chunks_by_role(
        all_chunks,
        classification_results,
        created_at,
    )

    chunks_map = {c.chunk_id: c for c in all_chunks}

    judged_candidates: List[dict] = []
    if candidate_blocks:
        print(f"  对 {len(candidate_blocks)} 个 candidate_mixed 候选进行知识裁决")
        judged_candidates = judge_candidate_mixed(ds, subj.name, candidate_blocks, chunks_map, force_refresh)

    span_candidates: List[dict] = []
    dropped_knowledge_debug: List[dict] = []

    for blk in strict_blocks:
        if blk.get("source") == "knowledge_image_placeholder":
            continue
        text = clean_text_basic(blk["text"])
        if not text:
            continue
        span_uid = sha_uid(blk["chunk_id"], text, "strict")
        span_candidates.append({
            "subject_id": blk["subject_id"],
            "span_uid": span_uid,
            "chunk_id": blk["chunk_id"],
            "context_heading": blk.get("context_heading"),
            "date_hint": blk.get("date_hint"),
            "text": text,
            "role": "strict_knowledge",
            "stability": "high",
            "source_block_text": blk["text"],
            "source_id": blk.get("source_id"),
            "order": blk.get("order"),
            "global_order": blk.get("global_order"),
            "created_at": blk.get("created_at"),
            "area": blk.get("area"),
            "parent_chunk_id": blk["chunk_id"],
        })

    def append_span_candidate(judged: dict, span: dict, chunk_id: str) -> None:
        text = clean_text_basic(span.get("text", ""))
        if not text:
            return
        span_uid = sha_uid(chunk_id, text, span.get("role", ""))
        span_candidates.append({
            "subject_id": judged["subject_id"],
            "span_uid": span_uid,
            "chunk_id": chunk_id,
            "context_heading": judged.get("context_heading"),
            "date_hint": judged.get("date_hint"),
            "text": text,
            "role": span.get("role", "unspecified"),
            "stability": span.get("stability", "low"),
            "source_block_text": judged.get("text", ""),
            "source_id": judged.get("source_id"),
            "order": judged.get("order"),
            "global_order": judged.get("global_order"),
            "created_at": judged.get("created_at"),
            "area": judged.get("area"),
            "parent_chunk_id": chunk_id,
        })

    for judged in judged_candidates:
        chunk_id = judged["chunk_id"]
        decision = judged.get("decision")

        if decision == "keep":
            spans = judged.get("knowledge_spans") or []
            if spans:
                for span in spans:
                    append_span_candidate(judged, span, chunk_id)
            else:
                raw_text = clean_text_basic(judged["text"])
                if raw_text:
                    span_uid = sha_uid(chunk_id, raw_text, "keep")
                    span_candidates.append({
                        "subject_id": judged["subject_id"],
                        "span_uid": span_uid,
                        "chunk_id": chunk_id,
                        "context_heading": judged.get("context_heading"),
                        "date_hint": judged.get("date_hint"),
                        "text": raw_text,
                        "role": "mixed_kept",
                        "stability": judged.get("knowledge_value", "low"),
                        "source_block_text": judged.get("text", ""),
                        "source_id": judged.get("source_id"),
                        "order": judged.get("order"),
                        "global_order": judged.get("global_order"),
                        "created_at": judged.get("created_at"),
                        "area": judged.get("area"),
                        "parent_chunk_id": chunk_id,
                    })
            final_bucket_map[chunk_id] = "knowledge_candidate"

        elif decision == "split":
            for span in judged.get("knowledge_spans", []):
                append_span_candidate(judged, span, chunk_id)

            residue = judged.get("event_residue", "").strip()
            if residue and len(compact_spaces(residue)) >= EVENT_RESIDUE_MIN_LEN and looks_like_real_event_text(residue):
                pure_events.append({
                    "subject_id": judged["subject_id"],
                    "chunk_id": sha_uid(judged["subject_id"], residue),
                    "area": judged.get("area"),
                    "context_heading": judged.get("context_heading"),
                    "date_hint": judged.get("date_hint"),
                    "global_order": judged.get("global_order"),
                    "source": "detail_html",
                    "created_at": created_at,
                    "source_id": judged.get("source_id"),
                    "order": judged.get("order"),
                    "used_fallback": judged.get("used_fallback", False),
                    "event_date_raw": judged.get("date_hint"),
                    "text": residue,
                })
            final_bucket_map[chunk_id] = "knowledge_candidate_split"

        elif decision == "drop":
            drop_target = judged.get("drop_target", "noise")
            if drop_target == "event":
                pure_events.append({
                    "subject_id": judged["subject_id"],
                    "chunk_id": judged["chunk_id"],
                    "area": judged.get("area"),
                    "context_heading": judged.get("context_heading"),
                    "date_hint": judged.get("date_hint"),
                    "global_order": judged.get("global_order"),
                    "source": "detail_html",
                    "created_at": created_at,
                    "source_id": judged.get("source_id"),
                    "order": judged.get("order"),
                    "used_fallback": judged.get("used_fallback", False),
                    "event_date_raw": judged.get("date_hint"),
                    "text": judged["text"],
                })
                final_bucket_map[chunk_id] = "dropped_to_event"
            else:
                noise_chunks.append({
                    "subject_id": judged["subject_id"],
                    "chunk_id": judged["chunk_id"],
                    "area": judged.get("area"),
                    "context_heading": judged.get("context_heading"),
                    "date_hint": judged.get("date_hint"),
                    "global_order": judged.get("global_order"),
                    "text": judged["text"],
                    "label": "noise",
                    "confidence": judged.get("confidence", 0.0),
                    "created_at": created_at,
                    "source_id": judged.get("source_id"),
                    "order": judged.get("order"),
                    "used_fallback": judged.get("used_fallback", False),
                })
                final_bucket_map[chunk_id] = "dropped_to_noise"

    core_knowledge: List[dict] = []
    related_knowledge: List[dict] = []
    signal_knowledge: List[dict] = []

    if span_candidates:
        print(f"  对 {len(span_candidates)} 个知识候选进行第三层规范化")
        canonicalized_items = canonicalize_knowledge_spans_with_llm(ds, subj.name, span_candidates, subject_id)
        candidate_by_uid = {item["span_uid"]: item for item in span_candidates if "span_uid" in item}

        for item in canonicalized_items:
            span_uid = item["span_uid"]
            action = item["action"]
            canonical_text = compact_spaces(item["canonical_text"])

            if action == "drop":
                dropped_knowledge_debug.append(item)
                continue

            ok, why = validate_knowledge_text(canonical_text)
            if not ok:
                dropped_knowledge_debug.append({**item, "drop_reason": f"format_gate:{why}"})
                continue

            matched = candidate_by_uid.get(span_uid)
            if not matched:
                dropped_knowledge_debug.append({**item, "drop_reason": "candidate_not_found"})
                continue

            source_block = {
                "subject_id": matched["subject_id"],
                "chunk_id": matched["chunk_id"],
                "area": matched.get("area"),
                "context_heading": matched.get("context_heading"),
                "date_hint": matched.get("date_hint"),
                "global_order": matched.get("global_order"),
                "created_at": matched.get("created_at"),
                "source_id": matched.get("source_id"),
                "order": matched.get("order"),
            }

            entry = make_knowledge_entry(
                source_block=source_block,
                source_type="knowledge_canonicalized",
                text=canonical_text,
                role=item.get("final_role", "unspecified"),
                stability=item.get("stability", "low"),
                knowledge_type=item.get("final_type", "signal"),
                parent_chunk_id=matched.get("parent_chunk_id") or matched["chunk_id"],
                canonical_action=action,
                canonical_reason=item.get("reason", ""),
                source_text=matched["text"],
            )

            if entry["knowledge_type"] == "core":
                core_knowledge.append(entry)
            elif entry["knowledge_type"] == "related":
                related_knowledge.append(entry)
            else:
                signal_knowledge.append(entry)

    merged_knowledge = dedup_knowledge_by_priority(core_knowledge + related_knowledge + signal_knowledge)
    core_knowledge = [x for x in merged_knowledge if x.get("knowledge_type") == "core"]
    related_knowledge = [x for x in merged_knowledge if x.get("knowledge_type") == "related"]
    signal_knowledge = [x for x in merged_knowledge if x.get("knowledge_type") == "signal"]
    all_knowledge = merged_knowledge

    knowledge_from_events: List[dict] = []
    if mode == "hybrid":
        filtered_events = [e for e in pure_events if e.get("text", "").strip()]
        knowledge_from_events = distill_events_to_knowledge(filtered_events, subj, created_at)

    debug_candidates = judged_candidates

    if debug or mode in ("all", "hybrid"):
        log_dir = data_dir / "chunk_classification"
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / f"{subject_id}.jsonl"
        judged_map = {j["chunk_id"]: j for j in judged_candidates}
        log_entries: List[dict] = []
        for chunk in all_chunks:
            res = classification_results.get(chunk.chunk_id, {})
            entry = {
                "chunk_id": chunk.chunk_id,
                "area": chunk.area,
                "context_heading": chunk.context_heading,
                "date_hint": chunk.date_hint,
                "text": chunk.text,
                "image_only": chunk.image_only,
                "classification": res,
                "final_bucket": final_bucket_map.get(chunk.chunk_id, "unknown"),
                "used_fallback": (not res) or res.get("is_fallback") is True,
            }
            if chunk.chunk_id in judged_map:
                jinfo = judged_map[chunk.chunk_id]
                entry["judge_decision"] = jinfo.get("decision")
                entry["judge_confidence"] = jinfo.get("confidence")
                entry["judge_reason"] = jinfo.get("reason")
            log_entries.append(entry)
        write_jsonl(log_path, log_entries)

    return ExtractResult(
        events=pure_events,
        knowledge_strict=strict_blocks,
        knowledge_core=core_knowledge,
        knowledge_related=related_knowledge,
        knowledge_signal=signal_knowledge,
        knowledge_all=all_knowledge,
        candidates_debug=debug_candidates,
        knowledge_from_events=knowledge_from_events,
        noise_chunks=noise_chunks,
        dropped_knowledge_debug=dropped_knowledge_debug,
    )


# ==================== CLI ====================
def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="题材详情解析器 v4.1.1（批处理与缓存优化版）")
    p.add_argument("--data-dir", required=True, help="数据目录，包含题材详情文件")
    p.add_argument("--subject", help="单题材 ID（与 --list-file 二选一）")
    p.add_argument("--list-file", help="题材列表文件，每行一个题材 ID 或 JSONL 格式")
    p.add_argument("--mode", default="all", choices=["all", "events", "knowledge", "hybrid"])
    p.add_argument("--debug", action="store_true", help="输出调试信息")
    p.add_argument("--force-refresh", action="store_true", help="强制刷新缓存，重新调用 LLM")
    p.add_argument("--cache-dir", default="chunk_role_cache", help="LLM 结果缓存目录")
    p.add_argument("--deepseek-api-key", default="", help="DeepSeek API Key，也可通过环境变量 DEEPSEEK_API_KEY 设置")
    p.add_argument("--limit", type=int, default=0, help="限制处理的题材数量（与 --list-file 配合使用）")
    return p.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)

    if not args.subject and not args.list_file:
        raise SystemExit("请指定 --subject 或 --list-file")

    api_key = args.deepseek_api_key.strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请提供 DeepSeek API Key")

    data_dir = Path(args.data_dir)
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)

    global CACHE_DIR
    CACHE_DIR = cache_dir

    config = LLMConfig()
    ds = DeepSeekClient(api_key=api_key, config=config, debug_http=args.debug)

    # 收集题材 ID 列表
    subject_ids = []
    if args.subject:
        subject_ids = [str(args.subject)]
    elif args.list_file:
        list_path = Path(args.list_file)
        if not list_path.exists():
            raise SystemExit(f"题材列表文件不存在: {list_path}")
        with list_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    sid = obj.get("subjectId") or obj.get("subject_id") or obj.get("bizKey")
                except json.JSONDecodeError:
                    sid = line
                if sid:
                    subject_ids.append(str(sid))
        if args.limit > 0:
            subject_ids = subject_ids[:args.limit]

    print(f"题材总数: {len(subject_ids)}")

    # 创建标记文件目录（用于断点续传）
    processed_dir = data_dir / ".processed"
    processed_dir.mkdir(exist_ok=True)

    stats = {"total": len(subject_ids), "ok": 0, "fail": 0, "skipped": 0, "fails": {}}

    for sid in tqdm(subject_ids, desc="处理题材"):
        processed_flag = processed_dir / f"{sid}.processed"

        # 如果已处理且未强制刷新，则跳过
        if not args.force_refresh and processed_flag.exists():
            stats["skipped"] += 1
            continue

        try:
            res = build_for_subject(
                ds=ds,
                data_dir=data_dir,
                subject_id=sid,
                mode=args.mode,
                debug=args.debug,
                force_refresh=args.force_refresh,
            )
            # 输出简要结果
            print(
                f"[OK] {sid} events={len(res.events)} strict_knowledge={len(res.knowledge_strict)} "
                f"core={len(res.knowledge_core)} related={len(res.knowledge_related)} "
                f"signal={len(res.knowledge_signal)} all_knowledge={len(res.knowledge_all)} "
                f"candidates_debug={len(res.candidates_debug)} noise={len(res.noise_chunks)} "
                f"dropped={len(res.dropped_knowledge_debug)}"
            )
            if args.mode == "hybrid":
                print(f" knowledge_from_events={len(res.knowledge_from_events)}")

            # ========== 写入文件（仅当列表非空时写入） ==========
            out_events = data_dir / "event_feed" / f"{sid}_events.jsonl"
            out_strict = data_dir / "knowledge_blocks_strict" / f"{sid}_knowledge_strict.jsonl"
            out_core = data_dir / "knowledge_core" / f"{sid}_knowledge_core.jsonl"
            out_related = data_dir / "knowledge_related" / f"{sid}_knowledge_related.jsonl"
            out_signal = data_dir / "knowledge_signal" / f"{sid}_knowledge_signal.jsonl"
            out_all = data_dir / "knowledge_all" / f"{sid}_knowledge_all.jsonl"
            out_candidates = data_dir / "knowledge_candidates_debug" / f"{sid}_candidates_debug.jsonl"
            out_event_kn = data_dir / "knowledge_from_events" / f"{sid}_knowledge_from_events.jsonl"
            out_noise = data_dir / "noise_chunks" / f"{sid}_noise.jsonl"
            out_dropped = data_dir / "knowledge_dropped_debug" / f"{sid}_knowledge_dropped.jsonl"

            if args.mode in ("all", "events", "hybrid") and res.events:
                write_jsonl(out_events, res.events)
            if args.mode in ("all", "knowledge", "hybrid"):
                if res.knowledge_strict:
                    write_jsonl(out_strict, res.knowledge_strict)
                if res.knowledge_core:
                    write_jsonl(out_core, res.knowledge_core)
                if res.knowledge_related:
                    write_jsonl(out_related, res.knowledge_related)
                if res.knowledge_signal:
                    write_jsonl(out_signal, res.knowledge_signal)
                if res.knowledge_all:
                    write_jsonl(out_all, res.knowledge_all)
                if res.candidates_debug:
                    write_jsonl(out_candidates, res.candidates_debug)
            if args.mode == "hybrid" and res.knowledge_from_events:
                write_jsonl(out_event_kn, res.knowledge_from_events)
            if res.noise_chunks:
                write_jsonl(out_noise, res.noise_chunks)
            if res.dropped_knowledge_debug:
                write_jsonl(out_dropped, res.dropped_knowledge_debug)

            # 处理完成，创建标记文件
            processed_flag.touch()
            stats["ok"] += 1

        except Exception as e:
            stats["fail"] += 1
            reason = f"EX:{type(e).__name__}"
            stats["fails"][reason] = stats["fails"].get(reason, 0) + 1
            print(f"\n[ERROR] subject={sid} -> {repr(e)}")
        time.sleep(DEFAULT_SLEEP)

    print("\n==== SUMMARY ====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))