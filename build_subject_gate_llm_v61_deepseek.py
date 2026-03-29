#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_subject_gate_llm_v70_evidence_profile.py

v7.0（一次性收敛版）核心改动：
1) 证据分层：knowledge vs event
   - knowledge：来自 children taxonomy + detail(非日期段落/结构段落/标题段落)
   - event：来自 detail 的按日期段落 + top-history/history
2) must 只允许来自 knowledge candidates（并要求 evidence_refs.source_type=knowledge）
3) should/not 可来自 knowledge + event（event 仅白名单 event_type）
4) 强校验 + 自动修复：
   - must>=8，process>=2，equipment_type>=3，vendor占比<=25%
   - must 禁词命中立即 fail（并触发 repair 重生成）
   - must 每个 term 必须有 knowledge evidence_refs
5) LLM 输出 slot 体系：process/equipment_type/component/material/standard/vendor/org
6) 彻底避免“年份/金额/比例/来源”等进入 must（候选阶段就过滤 + 校验阶段再硬拦）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests


# ==================== 配置 ====================
DEFAULT_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"  # or deepseek-reasoner

DEFAULT_TEMP = 0.1
DEFAULT_TOP_P = 0.9

DEBUG_DIR = Path("llm_debug_v70")

# 硬规则（你要求的）
MUST_MIN = 8
MUST_PROCESS_MIN = 2
MUST_EQUIP_MIN = 3
MUST_VENDOR_RATIO_MAX = 0.25

# 候选过滤阈值
MIN_TERM_LEN = 2
MIN_CONF_EXTRACT = 0.55

# Repair 最大回炉次数
MAX_REPAIR_ROUNDS = 3

# detail 分块（只用于“非日期知识段落”）
DETAIL_CHUNK_SIZE = 1200
DETAIL_CHUNK_OVERLAP = 100

# history 取多少条用于 should/not 的 event candidates
DEFAULT_HISTORY_TOPK = 10

# children 里哪些字段进入 knowledge
CHILD_NAME_FIELD = 1  # row[1] = "离子注入设备"
CHILD_PATH_FIELD = 2  # row[2] = "半导体设备-离子注入设备"
# ==============================================


# -------------------- util --------------------
def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def safe_json_loads(s: str) -> Optional[Any]:
    s = (s or "").strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        end = max(s.rfind("]"), s.rfind("}"))
        if end != -1:
            s2 = s[: end + 1]
            s2 = re.sub(r",\s*([}\]])", r"\1", s2)
            try:
                return json.loads(s2)
            except json.JSONDecodeError:
                return None
        return None


def clean_html(html: str) -> str:
    if not html:
        return ""
    text = html
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    text = re.sub(r"</p>|<br\s*/?>|</li>|</h\d>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    return text


# -------------------- date/event split --------------------
DATE_LINE_RE = re.compile(
    r"^\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*$"
)
DATE_INLINE_RE = re.compile(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日")


def split_detail_into_event_and_knowledge(detail_html: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    把 detail 分成：
    - event_blocks：按日期组织的动态段落（全部视为 event）
    - knowledge_blocks：非日期段落（标题/说明/结构段落等）
    输出 block:
      {
        "block_id": "...",
        "source_type": "knowledge|event",
        "text": "...",
        "meta": {...}
      }
    """
    text = clean_html(detail_html)
    if not text:
        return [], []

    lines = [ln.strip() for ln in text.splitlines()]
    lines = [ln for ln in lines if ln]

    event_blocks: List[Dict[str, Any]] = []
    knowledge_blocks: List[Dict[str, Any]] = []

    cur_date: Optional[str] = None
    cur_buf: List[str] = []

    def flush_event():
        nonlocal cur_date, cur_buf
        if cur_date and cur_buf:
            body = "\n".join(cur_buf).strip()
            if body:
                event_blocks.append({
                    "block_id": f"detail_event_{sha256(cur_date + body)[:10]}",
                    "source_type": "event",
                    "text": f"{cur_date}\n{body}",
                    "meta": {"date": cur_date}
                })
        cur_buf = []

    # 策略：
    # - 单独一行日期：开启 event 模式
    # - event 模式一直收集，直到遇到下一行日期
    # - 不在 event 模式的内容，累积为 knowledge
    know_buf: List[str] = []

    def flush_knowledge():
        nonlocal know_buf
        body = "\n".join(know_buf).strip()
        if body:
            knowledge_blocks.append({
                "block_id": f"detail_know_{sha256(body)[:10]}",
                "source_type": "knowledge",
                "text": body,
                "meta": {}
            })
        know_buf = []

    for ln in lines:
        m = DATE_LINE_RE.match(ln)
        if m:
            # 进入新的日期 event
            flush_knowledge()
            flush_event()
            cur_date = ln
            continue

        if cur_date:
            # event 模式
            cur_buf.append(ln)
        else:
            # knowledge 模式（但过滤“明显新闻标题式”的纯日期行已经处理）
            know_buf.append(ln)

    flush_knowledge()
    flush_event()

    return event_blocks, knowledge_blocks


def split_long_text(text: str, size: int, overlap: int) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    parts = re.split(r"(。|；|;|\n)", t)
    segs: List[str] = []
    buf = ""
    for p in parts:
        if not p:
            continue
        if len(buf) + len(p) <= size:
            buf += p
        else:
            if buf.strip():
                segs.append(buf.strip())
            tail = buf[-overlap:] if overlap > 0 and len(buf) > overlap else ""
            buf = tail + p
    if buf.strip():
        segs.append(buf.strip())
    return segs


# -------------------- children taxonomy -> knowledge blocks --------------------
def parse_children_lines(children_path: Path, subject_id: str) -> List[Dict[str, Any]]:
    """
    children.jsonl 你给的是每行一个类似 list 的文本：
    [9011411, "离子注入设备", "半导体设备-离子注入设备", ...]
    我们把这些作为“强结构知识证据”，直接变成 knowledge blocks。
    """
    if not children_path.exists():
        return []

    blocks: List[Dict[str, Any]] = []
    with children_path.open("r", encoding="utf-8") as f:
        for line in f:
            ln = line.strip()
            if not ln:
                continue
            obj = safe_json_loads(ln)
            if not isinstance(obj, list) or len(obj) < 3:
                continue
            name = str(obj[CHILD_NAME_FIELD]).strip()
            path = str(obj[CHILD_PATH_FIELD]).strip()
            if not name:
                continue
            text = f"设备分类：{path}\n节点名称：{name}"
            blocks.append({
                "block_id": f"children_know_{sha256(ln)[:10]}",
                "source_type": "knowledge",
                "text": text,
                "meta": {"name": name, "path": path, "subject_id": subject_id}
            })
    return blocks


# -------------------- history -> event blocks --------------------
def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            ln = line.strip()
            if not ln:
                continue
            obj = safe_json_loads(ln)
            if isinstance(obj, dict):
                out.append(obj)
    return out


def history_to_event_blocks(history_items: List[Dict[str, Any]], topk: int) -> List[Dict[str, Any]]:
    def sort_key(x: Dict[str, Any]) -> str:
        return str(x.get("rankDate") or x.get("createTime") or x.get("updateTime") or "")

    picked: List[Dict[str, Any]] = []
    for it in sorted(history_items, key=sort_key, reverse=True):
        desc = (it.get("description") or "").strip()
        if not desc or len(desc) < 20:
            continue
        sid = it.get("subjectRankId") or sha256(desc)[:8]
        picked.append({
            "block_id": f"hist_event_{sid}",
            "source_type": "event",
            "text": desc,
            "meta": {"subjectRankId": sid, "rankDate": it.get("rankDate")}
        })
        if len(picked) >= topk:
            break
    return picked


# -------------------- term filters (hard) --------------------
YEAR_RE = re.compile(r"20\d{2}\s*年|20\d{2}\s*-\s*20\d{2}")
MONEY_RE = re.compile(r"\d+(\.\d+)?\s*(亿|万)?(美元|欧元|人民币|元)")
PCT_RE = re.compile(r"\d+(\.\d+)?\s*%")
PURE_NUM_RE = re.compile(r"^\d+(\.\d+)?$")


# must 禁词（你列的）
MUST_FORBIDDEN = {
    "GPU", "DRAM", "HBM", "EDA", "先进封装", "封装", "IPO",
    "关税", "资本开支", "销量", "涨跌幅", "协会", "SIA", "SEMI",
    "营收", "净利润", "同比", "环比", "市值", "股价", "涨停", "反弹",
    "路透", "彭博", "财联社", "科创板日报", "IT之家",
    "实体清单", "黑名单", "出口管制", "VEU",
}


# 非 must 噪声（抽 candidates 时就要剔除）
NOISE_TERMS = {
    "公司", "市场", "行业", "增长", "下降", "预计", "表示", "指出",
    "报道", "日讯", "公告", "相关", "发布", "推进", "规划", "建设",
    "落地", "实施", "提升", "保持", "持续", "消息", "人士", "媒体",
    "驱动事件", "新闻来源",
}


def looks_like_time_or_number(term: str) -> bool:
    t = term.strip()
    if not t:
        return True
    if PURE_NUM_RE.fullmatch(t):
        return True
    if YEAR_RE.search(t):
        return True
    if MONEY_RE.search(t):
        return True
    if PCT_RE.search(t):
        return True
    if DATE_INLINE_RE.search(t):
        return True
    return False


def is_noisy_term(term: str) -> bool:
    t = term.strip()
    if len(t) < MIN_TERM_LEN:
        return True
    if t in NOISE_TERMS:
        return True
    if looks_like_time_or_number(t):
        return True
    return False


# -------------------- event type classifier (rule) --------------------
def classify_event_type(text: str) -> str:
    """
    只用于 event blocks 的 should/not 白名单控制。
    规则优先：快、稳、可控（不需要 LLM）
    """
    t = text or ""
    # price_move
    if any(k in t for k in ["涨停", "涨超", "大涨", "反弹", "下跌", "震荡", "股价", "pctChg", "涨幅"]):
        return "price_move"
    # finance/macro
    if any(k in t for k in ["资本开支", "营收", "净利润", "市值", "同比", "环比", "销售额", "出货金额", "规模", "亿美元", "%", "万亿美元"]):
        # 注意：这里很多会落 finance/macro（不进 must，只能 should/not）
        if "协会" in t or "SIA" in t or "SEMI" in t:
            return "macro"
        return "finance"
    # control
    if any(k in t for k in ["出口管制", "实体清单", "黑名单", "VEU", "许可证", "限制"]):
        return "control"
    # release / order
    if any(k in t for k in ["发布", "推出", "首款", "交付", "到货", "导入"]):
        return "release"
    if any(k in t for k in ["中标", "订单", "招标", "采购", "签署"]):
        return "order"
    # policy
    if any(k in t for k in ["政策", "措施", "行动方案", "印发", "目录", "支持", "鼓励"]):
        return "policy"
    return "other"


EVENT_SHOULD_WHITELIST = {"order", "release", "control", "policy"}


# -------------------- DeepSeek client --------------------
class DeepSeekClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_DEEPSEEK_BASE_URL,
        model: str = DEFAULT_DEEPSEEK_MODEL,
        timeout: Tuple[int, int] = (10, 600),
        debug_http: bool = False,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.debug_http = debug_http
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
        max_tokens: int,
        temperature: float,
        debug_tag: str,
        subject_id: str,
        max_retries: int = 4,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/v1/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": float(temperature),
            "top_p": float(DEFAULT_TOP_P),
            "max_tokens": int(max_tokens),
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        debug_dir = DEBUG_DIR / str(subject_id)
        debug_dir.mkdir(parents=True, exist_ok=True)

        backoff = 1.2
        last_err: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                if self.debug_http:
                    print(f"[DEBUG] POST {url} model={self.model} tag={debug_tag} attempt={attempt}")

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

                (debug_dir / f"{debug_tag}_raw_attempt{attempt}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2)[:200000],
                    encoding="utf-8"
                )

                content = data["choices"][0]["message"]["content"]
                obj = safe_json_loads(content)

                if not isinstance(obj, dict):
                    block = self._extract_json_block_loose(content)
                    obj2 = safe_json_loads(block or "")
                    if isinstance(obj2, dict):
                        obj = obj2
                    elif isinstance(obj2, list):
                        obj = {"items": obj2}
                    else:
                        (debug_dir / f"{debug_tag}_badjson_attempt{attempt}.txt").write_text(
                            content[:20000], encoding="utf-8"
                        )
                        raise RuntimeError("DeepSeek returned non-json_object")

                return obj

            except Exception as e:
                last_err = e
                (debug_dir / f"{debug_tag}_ex_attempt{attempt}.txt").write_text(
                    repr(e), encoding="utf-8"
                )
                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 1.6, 12.0)
                    continue
                break

        raise RuntimeError(f"DeepSeek run_json_object failed: {repr(last_err)}")


# -------------------- prompts --------------------
EXTRACTOR_SYSTEM_V2 = """你是“题材证据术语抽取器”。你必须只输出合法 JSON 对象，不要输出解释文字。
输出格式必须为：
{
  "items": [
    {
      "term": "...",
      "slot": "process|equipment_type|component|material|standard|org|vendor",
      "confidence": 0.0,
      "spans": { "text": "必须是原文连续子串（原样复制）" }
    }
  ]
}

严格规则（必须遵守）：
1) 只能从原文中抽取，严禁编造。
2) 只能抽“定义题材本体”的术语：工艺/设备类型/关键部件/关键材料/标准或机构/组织/厂商。
3) 严禁抽取：年份/日期/数值/金额/百分比/资本开支/IPO/关税/股价/涨跌幅/协会数据/媒体来源/公司泛称/政策空话。
4) spans.text 必须在原文中连续出现，尽量短以便定位。
5) term 尽量短、可判别；避免“推进/提升/规划/建设/落地/预计/表示”等泛词。
6) 输出 12~30 条；少于 10 条视为失败。
"""

NORMALIZER_SYSTEM_V2 = """你是“题材 Gate 生成器”。你必须只输出合法 JSON 对象，不要输出解释文字。
输出格式：
{
  "must": [
    {"terms":["..."], "min_hit":1, "slot":"process|equipment_type|component|material|standard|org|vendor", "explain":"..."}
  ],
  "should": [
    {"terms":["..."], "boost":0.2}
  ],
  "not": [
    {"terms":["..."], "reason":"...", "contrast":"..."}
  ],
  "evidence_refs": [
    {"term":"...", "source_type":"knowledge", "source_id":"...", "span_text":"..."}
  ]
}

硬约束（必须遵守）：
A) must 只能从输入的 knowledge_candidates 中选择（禁止从 event_candidates 选）。
B) must 必须满足配额：
   - process：>=2
   - equipment_type：>=3
   - must 总数：>=8
   - vendor：最多 2 且 vendor 占比 <=25%
C) 严禁把以下类别放入 must：年份/日期/金额/百分比/资本开支/IPO/关税/实体清单/出口管制/GPU/DRAM/EDA/先进封装/封装/股价/涨跌幅/协会数据/媒体来源。
D) evidence_refs：每个 must term 必须至少 1 条 evidence_refs，且 source_type 必须为 knowledge。
E) should/not 可以使用 knowledge_candidates + event_candidates（但 event_candidates 已过滤白名单事件类型）。
F) 严禁新增不在 candidates 里的新 term。
"""

REPAIR_SYSTEM_V2 = """你是“Gate 修复器”。你必须只输出合法 JSON 对象，不要输出解释文字。
输入会给你：旧 gate、失败原因、knowledge_candidates、event_candidates。
你必须：
- 重新生成 gate（不是微调），并严格满足所有硬约束。
- must 只能来自 knowledge_candidates。
- 必须补齐 process>=2、equipment_type>=3、must>=8。
- 每个 must term 都要补齐 evidence_refs（source_type=knowledge）。
输出格式同 normalizer。
"""


# -------------------- candidate struct --------------------
@dataclass
class Candidate:
    term: str
    slot: str
    confidence: float
    source_type: str  # knowledge|event
    source_id: str
    span_text: str
    event_type: Optional[str] = None


def normalize_slot(slot: str) -> str:
    s = (slot or "").strip()
    allowed = {"process", "equipment_type", "component", "material", "standard", "org", "vendor"}
    if s in allowed:
        return s
    # 宽松映射（防模型偶发输出）
    m = {
        "equipment": "equipment_type",
        "equip": "equipment_type",
        "entity": "vendor",
        "company": "vendor",
        "material/component": "material",
    }
    return m.get(s, "component")


def attach_candidates_from_llm_items(
    items: List[Dict[str, Any]],
    source_type: str,
    source_id: str,
    content: str,
    event_type: Optional[str] = None
) -> List[Candidate]:
    out: List[Candidate] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        term = str(it.get("term", "")).strip()
        slot = normalize_slot(str(it.get("slot", "")).strip())
        conf = float(it.get("confidence", 0) or 0)
        spans = it.get("spans") or {}
        span_text = str(spans.get("text", "")).strip()

        if is_noisy_term(term):
            continue
        if conf < MIN_CONF_EXTRACT:
            continue
        if not span_text or span_text not in content:
            # 兜底：用 term 作为 span
            if term in content:
                span_text = term
            else:
                continue

        # event 白名单过滤（只影响 event candidates）
        if source_type == "event":
            if event_type and event_type not in EVENT_SHOULD_WHITELIST:
                continue

        out.append(Candidate(
            term=term,
            slot=slot,
            confidence=conf,
            source_type=source_type,
            source_id=source_id,
            span_text=span_text,
            event_type=event_type
        ))
    return out


def dedup_candidates(cands: List[Candidate]) -> List[Candidate]:
    best: Dict[Tuple[str, str, str], Candidate] = {}
    for c in cands:
        key = (c.term, c.slot, c.source_type)
        if key not in best or c.confidence > best[key].confidence:
            best[key] = c
    return list(best.values())


# -------------------- LLM steps --------------------
def llm_extract(ds: DeepSeekClient, subject_id: str, text: str, debug_tag: str) -> List[Dict[str, Any]]:
    messages = [
        {"role": "system", "content": EXTRACTOR_SYSTEM_V2},
        {"role": "user", "content": f"TEXT:\n{text}"},
    ]
    obj = ds.run_json_object(
        messages=messages,
        max_tokens=3500,
        temperature=DEFAULT_TEMP,
        debug_tag=debug_tag,
        subject_id=subject_id,
    )
    items = obj.get("items", [])
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]


def llm_normalize(ds: DeepSeekClient, subject_id: str, knowledge_cands: List[Candidate], event_cands: List[Candidate]) -> Dict[str, Any]:
    # 给 LLM 的 candidates：只给必要字段，控制长度
    kn = sorted(knowledge_cands, key=lambda x: x.confidence, reverse=True)[:220]
    ev = sorted(event_cands, key=lambda x: x.confidence, reverse=True)[:220]

    kn_payload = [{
        "term": c.term, "slot": c.slot, "confidence": c.confidence,
        "source_type": c.source_type, "source_id": c.source_id, "span_text": c.span_text
    } for c in kn]

    ev_payload = [{
        "term": c.term, "slot": c.slot, "confidence": c.confidence,
        "source_type": c.source_type, "source_id": c.source_id, "span_text": c.span_text,
        "event_type": c.event_type
    } for c in ev]

    messages = [
        {"role": "system", "content": NORMALIZER_SYSTEM_V2},
        {"role": "user", "content":
            "knowledge_candidates(JSON array):\n" + json.dumps(kn_payload, ensure_ascii=False) +
            "\n\nevent_candidates(JSON array):\n" + json.dumps(ev_payload, ensure_ascii=False)
        },
    ]
    obj = ds.run_json_object(
        messages=messages,
        max_tokens=7000,
        temperature=DEFAULT_TEMP,
        debug_tag="normalize",
        subject_id=subject_id,
    )
    obj["subject_id"] = int(subject_id) if str(subject_id).isdigit() else subject_id
    obj["meta"] = {"generated_at": now_iso(), "pipeline": "v70_evidence_profile"}
    return obj


def llm_repair(ds: DeepSeekClient, subject_id: str, old_gate: Dict[str, Any], reasons: List[str], knowledge_cands: List[Candidate], event_cands: List[Candidate], round_id: int) -> Dict[str, Any]:
    kn = sorted(knowledge_cands, key=lambda x: x.confidence, reverse=True)[:240]
    ev = sorted(event_cands, key=lambda x: x.confidence, reverse=True)[:240]

    kn_payload = [{
        "term": c.term, "slot": c.slot, "confidence": c.confidence,
        "source_type": c.source_type, "source_id": c.source_id, "span_text": c.span_text
    } for c in kn]
    ev_payload = [{
        "term": c.term, "slot": c.slot, "confidence": c.confidence,
        "source_type": c.source_type, "source_id": c.source_id, "span_text": c.span_text,
        "event_type": c.event_type
    } for c in ev]

    messages = [
        {"role": "system", "content": REPAIR_SYSTEM_V2},
        {"role": "user", "content":
            "failed_reasons:\n" + json.dumps(reasons, ensure_ascii=False) +
            "\n\nold_gate:\n" + json.dumps(old_gate, ensure_ascii=False) +
            "\n\nknowledge_candidates:\n" + json.dumps(kn_payload, ensure_ascii=False) +
            "\n\nevent_candidates:\n" + json.dumps(ev_payload, ensure_ascii=False)
        },
    ]
    obj = ds.run_json_object(
        messages=messages,
        max_tokens=7000,
        temperature=DEFAULT_TEMP,
        debug_tag=f"repair_r{round_id}",
        subject_id=subject_id,
    )
    obj["subject_id"] = int(subject_id) if str(subject_id).isdigit() else subject_id
    obj["meta"] = {"generated_at": now_iso(), "pipeline": "v70_evidence_profile", "repair_round": round_id}
    return obj


# -------------------- gate validation (hard) --------------------
def gate_collect_terms(gate: Dict[str, Any]) -> Tuple[List[Tuple[str, str]], List[str]]:
    """
    返回：
      - must_terms: [(term, slot)]
      - all_terms: [term]
    """
    must_terms: List[Tuple[str, str]] = []
    all_terms: List[str] = []

    def take_terms(arr: Any) -> List[str]:
        out: List[str] = []
        if isinstance(arr, list):
            for x in arr:
                if isinstance(x, str):
                    out.append(x)
        return out

    for m in gate.get("must") or []:
        if not isinstance(m, dict):
            continue
        slot = str(m.get("slot", "")).strip()
        terms = take_terms(m.get("terms"))
        for t in terms:
            must_terms.append((t, slot))
            all_terms.append(t)

    for s in gate.get("should") or []:
        if isinstance(s, dict):
            for t in take_terms(s.get("terms")):
                all_terms.append(t)

    for n in gate.get("not") or []:
        if isinstance(n, dict):
            for t in take_terms(n.get("terms")):
                all_terms.append(t)

    return must_terms, all_terms


def validate_gate_hard(gate: Dict[str, Any], knowledge_cands: List[Candidate]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    must = gate.get("must")
    if not isinstance(must, list) or len(must) < MUST_MIN:
        reasons.append(f"MUST_TOO_FEW(<{MUST_MIN})")

    must_terms, _ = gate_collect_terms(gate)

    # slot 计数
    process_cnt = sum(1 for _, slot in must_terms if slot == "process")
    equip_cnt = sum(1 for _, slot in must_terms if slot == "equipment_type")
    vendor_cnt = sum(1 for _, slot in must_terms if slot == "vendor")
    if process_cnt < MUST_PROCESS_MIN:
        reasons.append(f"PROCESS_TOO_FEW(<{MUST_PROCESS_MIN})")
    if equip_cnt < MUST_EQUIP_MIN:
        reasons.append(f"EQUIP_TOO_FEW(<{MUST_EQUIP_MIN})")
    if must_terms:
        if vendor_cnt / max(1, len(must_terms)) > MUST_VENDOR_RATIO_MAX:
            reasons.append("VENDOR_RATIO_TOO_HIGH")

    # must 禁词
    for term, _slot in must_terms:
        t = term.strip()
        # 直接命中禁词（包含式）
        if any(bad in t for bad in MUST_FORBIDDEN):
            reasons.append(f"MUST_FORBIDDEN_TERM({t})")
            break
        if looks_like_time_or_number(t):
            reasons.append(f"MUST_TIME_OR_NUMBER({t})")
            break

    # evidence_refs：must 每个 term 必须有 knowledge 引用
    ev = gate.get("evidence_refs")
    if not isinstance(ev, list) or not ev:
        reasons.append("NO_EVIDENCE_REFS")
    else:
        ev_map: Dict[str, List[Dict[str, Any]]] = {}
        for e in ev:
            if not isinstance(e, dict):
                continue
            if e.get("source_type") != "knowledge":
                continue
            term = str(e.get("term", "")).strip()
            if not term:
                continue
            ev_map.setdefault(term, []).append(e)

        for term, _slot in must_terms:
            if term not in ev_map:
                reasons.append(f"MISSING_KNOWLEDGE_EVIDENCE({term})")
                break
            # 必须齐全
            one = ev_map[term][0]
            if not one.get("source_id") or not one.get("span_text"):
                reasons.append(f"EVIDENCE_INCOMPLETE({term})")
                break

    # must 只能来自 knowledge candidates（term 粗匹配）
    know_terms = {c.term for c in knowledge_cands}
    for term, _slot in must_terms:
        if term not in know_terms:
            reasons.append(f"MUST_NOT_IN_KNOWLEDGE_CANDS({term})")
            break

    return (len(reasons) == 0, reasons)


# -------------------- load subject sources --------------------
def load_subject_bundle(data_dir: Path, subject_id: str, history_topk: int) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    返回：
      knowledge_blocks, event_blocks
    """
    # details
    details_file = data_dir / "details" / f"{subject_id}_details.jsonl"
    details = read_jsonl(details_file)
    detail_html = ""
    reason_text = ""
    for item in details[:1]:
        detail_html = item.get("detail") or item.get("detail_html") or ""
        reason_text = item.get("reason") or ""

    event_from_detail, knowledge_from_detail = split_detail_into_event_and_knowledge(detail_html)

    # reason 作为 event（不是 knowledge），避免 must 被污染
    if reason_text and reason_text.strip():
        event_from_detail.insert(0, {
            "block_id": f"reason_event_{sha256(reason_text)[:10]}",
            "source_type": "event",
            "text": reason_text.strip(),
            "meta": {"reason": True}
        })

    # children -> knowledge
    children_file = data_dir / "children" / f"{subject_id}_children.jsonl"
    knowledge_from_children = parse_children_lines(children_file, subject_id)

    # history -> event
    history_file = data_dir / "history" / f"{subject_id}_history.jsonl"
    history_items = read_jsonl(history_file)
    event_from_history = history_to_event_blocks(history_items, topk=history_topk)

    knowledge_blocks = knowledge_from_children + knowledge_from_detail
    event_blocks = event_from_detail + event_from_history

    # 对 knowledge 中过长段落做切分（避免 extractor 被一段塞爆）
    final_knowledge: List[Dict[str, Any]] = []
    for b in knowledge_blocks:
        txt = (b.get("text") or "").strip()
        if len(txt) > DETAIL_CHUNK_SIZE:
            chunks = split_long_text(txt, DETAIL_CHUNK_SIZE, DETAIL_CHUNK_OVERLAP)
            for i, ck in enumerate(chunks):
                final_knowledge.append({
                    "block_id": f"{b['block_id']}_ck{i}",
                    "source_type": "knowledge",
                    "text": ck,
                    "meta": b.get("meta") or {}
                })
        else:
            final_knowledge.append(b)

    return final_knowledge, event_blocks


# -------------------- pipeline --------------------
def build_gate_for_subject(
    ds: DeepSeekClient,
    data_dir: Path,
    subject_id: str,
    out_dir: Path,
    history_topk: int,
) -> Dict[str, Any]:
    knowledge_blocks, event_blocks = load_subject_bundle(data_dir, subject_id, history_topk=history_topk)

    if not knowledge_blocks:
        raise RuntimeError("NO_KNOWLEDGE_BLOCKS (children/detail结构段落为空)")

    # 1) Extract candidates from knowledge
    knowledge_cands: List[Candidate] = []
    for i, b in enumerate(knowledge_blocks):
        text = b["text"]
        block_id = b["block_id"]
        items = llm_extract(ds, subject_id, text, debug_tag=f"extract_kn_{i}")
        knowledge_cands.extend(
            attach_candidates_from_llm_items(
                items=items,
                source_type="knowledge",
                source_id=block_id,
                content=text,
                event_type=None
            )
        )

    knowledge_cands = dedup_candidates(knowledge_cands)

    # 2) Extract candidates from event（但只保留白名单 event_type 的）
    event_cands: List[Candidate] = []
    for j, b in enumerate(event_blocks):
        text = b["text"]
        block_id = b["block_id"]
        et = classify_event_type(text)
        # 只抽白名单事件类型，否则直接跳过（减少噪声）
        if et not in EVENT_SHOULD_WHITELIST:
            continue
        items = llm_extract(ds, subject_id, text, debug_tag=f"extract_ev_{j}")
        event_cands.extend(
            attach_candidates_from_llm_items(
                items=items,
                source_type="event",
                source_id=block_id,
                content=text,
                event_type=et
            )
        )

    event_cands = dedup_candidates(event_cands)

    # 基础 sanity：knowledge candidates 不够就必然过不了 must>=8
    if len(knowledge_cands) < 12:
        raise RuntimeError(f"KNOWLEDGE_CANDS_TOO_FEW({len(knowledge_cands)}) -> 需要更多 children/结构段落")

    # 3) Normalize gate
    gate = llm_normalize(ds, subject_id, knowledge_cands, event_cands)

    # 4) Hard validate + repair loop
    ok, reasons = validate_gate_hard(gate, knowledge_cands)
    if not ok:
        gate["risk_flags"] = reasons

    for r in range(1, MAX_REPAIR_ROUNDS + 1):
        if ok:
            break
        gate2 = llm_repair(ds, subject_id, gate, reasons, knowledge_cands, event_cands, round_id=r)
        ok2, reasons2 = validate_gate_hard(gate2, knowledge_cands)
        if ok2:
            gate = gate2
            ok = True
            reasons = []
            break
        else:
            gate = gate2
            gate["risk_flags"] = reasons2
            reasons = reasons2

    # 5) Write output
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{subject_id}_gate_v70.json"
    out_path.write_text(json.dumps(gate, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "ok": ok,
        "subject_id": subject_id,
        "knowledge_blocks": len(knowledge_blocks),
        "event_blocks": len(event_blocks),
        "knowledge_candidates": len(knowledge_cands),
        "event_candidates": len(event_cands),
        "out_path": str(out_path),
        "fail_reasons": reasons,
    }


# -------------------- cli --------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="theme_data_complete")
    ap.add_argument("--out-dir", default="subject_gates_out_v70")
    ap.add_argument("--subject", required=True)
    ap.add_argument("--history-topk", type=int, default=DEFAULT_HISTORY_TOPK)

    ap.add_argument("--deepseek-api-key", default="")
    ap.add_argument("--deepseek-base-url", default=DEFAULT_DEEPSEEK_BASE_URL)
    ap.add_argument("--deepseek-model", default=DEFAULT_DEEPSEEK_MODEL)
    ap.add_argument("--debug-http", action="store_true")

    args = ap.parse_args()

    api_key = args.deepseek_api_key.strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("需要 DeepSeek API Key：设置环境变量 DEEPSEEK_API_KEY 或传 --deepseek-api-key")

    ds = DeepSeekClient(
        api_key=api_key,
        base_url=args.deepseek_base_url,
        model=args.deepseek_model,
        debug_http=args.debug_http,
    )

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise SystemExit(f"data-dir not found: {data_dir}")
    out_dir = Path(args.out_dir)

    sid = str(args.subject).strip()
    stats = build_gate_for_subject(
        ds=ds,
        data_dir=data_dir,
        subject_id=sid,
        out_dir=out_dir,
        history_topk=args.history_topk,
    )

    print("\n==== RESULT ====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if not stats["ok"]:
        raise SystemExit(f"[FAIL] {sid} gate not pass hard rules: {stats['fail_reasons']}")
    print(f"[OK] wrote {stats['out_path']}")


if __name__ == "__main__":
    main()