#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最终稳定版 v6 - 自适应 llama-server + 强健 JSON 解析 + 进度可见
- 自动探测可用 endpoint (/completion, /v1/completions, /v1/chat/completions)
- 根据模式构建不同 payload
- 改进 JSON 提取，兼容 stop 截断
- 保留所有 v3/v5 优化：噪声过滤、证据校验、实体占比限制等
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from tqdm import tqdm


# ==================== 配置 ====================
DEFAULT_LLAMA_URL = "http://127.0.0.1:8080"      # 与 server bind 一致
DEFAULT_TEMP = 0.1
DEFAULT_TOP_P = 0.9
DEFAULT_REPEAT_PENALTY = 1.15
DEFAULT_N_PREDICT_EXTRACT = 128
DEFAULT_N_PREDICT_NORM = 192
DEFAULT_SLEEP_BETWEEN_CALLS = 0.25
DEFAULT_MAX_CALLS_PER_SUBJECT = 8
DEFAULT_HISTORY_TOPK = 6
DEFAULT_DETAIL_MAX_CHUNKS = 4
DEFAULT_MIN_HISTORY_LEN = 20
DEFAULT_CHUNK_SIZE = 900
DEFAULT_CHUNK_OVERLAP = 80
MIN_TERM_LEN = 2
MIN_CONF_EXTRACT = 0.55
EXTRACT_MIN_COUNT = 3                     # 抽取最少条数，否则重试
# ==============================================

DEBUG_DIR = Path("llm_debug")               # 调试输出目录


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def clean_html(text: str) -> str:
    """改进的 HTML 清洗：保留段落换行，并移除脚本/样式"""
    if not text:
        return ""
    # 清除脚本和样式
    text = re.sub(r"<script[\s\S]*?</script>", " ", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
    # 把块级标签转换为换行
    text = re.sub(r"</p>|<br\s*/?>|</li>|</h\d>", "\n", text, flags=re.I)
    # 移除所有标签
    text = re.sub(r"<[^>]+>", " ", text)
    # 合并连续空白
    text = re.sub(r"[ \t]+", " ", text)
    # 合并多余换行
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    return text


# ---------- JSON 解析增强（兼容被截断）----------
def extract_json_block(text: str) -> Optional[str]:
    """从模型输出中提取 JSON 字符串，即使只有 <json> 开头没有闭合也能处理"""
    # 1) <json> ... </json> 完整包裹
    m = re.search(r"<json>\s*(.*?)\s*</json>", text, flags=re.I | re.S)
    if m:
        return m.group(1).strip()

    # 2) <json> ... （可能被 stop 截断，没有闭合）
    m = re.search(r"<json>\s*(.*)", text, flags=re.I | re.S)
    if m:
        inner = m.group(1).strip()
        # 去掉任何尾随的闭合标签残余（如果有的话）
        inner = re.split(r"</json\s*>", inner, flags=re.I)[0].strip()
        if inner.startswith("[") or inner.startswith("{"):
            return inner

    # 3) 各种代码块包裹
    m = re.search(r"```json\s*(.*?)\s*```", text, flags=re.I | re.S)
    if m:
        return m.group(1).strip()

    m = re.search(r"```\s*(.*?)\s*```", text, flags=re.S)
    if m:
        inner = m.group(1).strip()
        if inner and (inner.startswith("[") or inner.startswith("{")):
            return inner

    # 4) 直接提取第一个 [ 或 { 开始的位置
    start_idx = None
    for ch in ("[", "{"):
        idx = text.find(ch)
        if idx != -1 and (start_idx is None or idx < start_idx):
            start_idx = idx
    if start_idx is not None:
        return text[start_idx:].strip()

    return None


def safe_json_loads(s: str) -> Optional[Any]:
    """安全解析 JSON，自动截断尾部多余字符"""
    s = s.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    end = max(s.rfind("]"), s.rfind("}"))
    if end != -1:
        s2 = s[: end + 1]
        s2 = re.sub(r",\s*([}\]])", r"\1", s2)
        try:
            return json.loads(s2)
        except json.JSONDecodeError:
            pass
    return None


# ---------- 自适应 llama-server 客户端 ----------
class LlamaServer:
    """
    自适应 llama-server 客户端：
    - 自动探测可用 endpoint (/completion, /v1/completions, /v1/chat/completions)
    - 根据 mode 构建不同 payload
    - 带连接/读取双超时
    """
    def __init__(self, base_url: str = DEFAULT_LLAMA_URL, debug: bool = False):
        self.base = base_url.rstrip("/")
        self.debug = debug
        self.sess = requests.Session()
        self.url, self.mode = self._detect_endpoint()

    def _detect_endpoint(self) -> Tuple[str, str]:
        candidates = [
            (f"{self.base}/completion", "llamacpp_completion"),
            (f"{self.base}/v1/completions", "openai_completions"),
            (f"{self.base}/v1/chat/completions", "openai_chat"),
        ]

        probe_prompt = "ping"
        for url, mode in candidates:
            try:
                payload = self._build_payload(mode, probe_prompt, n_predict=8, temp=0.0)
                # 连接超时 5 秒，读取超时 20 秒
                r = self.sess.post(url, json=payload, timeout=(5, 20))
                if r.status_code >= 400:
                    continue
                data = r.json()
                text = self._parse_text(mode, data)
                if isinstance(text, str) and text.strip():
                    if self.debug:
                        print(f"[DEBUG] endpoint detected: {url} mode={mode}")
                    return url, mode
            except Exception:
                continue

        raise RuntimeError(
            f"Cannot detect endpoint under base_url={self.base}. "
            f"Tried: {[u for u, _ in candidates]}. "
            "Please check that llama-server is running and reachable."
        )

    def _build_payload(self, mode: str, prompt: str, n_predict: int, temp: float) -> Dict[str, Any]:
        """根据模式构建请求 payload"""
        if mode == "llamacpp_completion":
            return {
                "prompt": prompt,
                "temperature": float(temp),
                "top_p": float(DEFAULT_TOP_P),
                "repeat_penalty": float(DEFAULT_REPEAT_PENALTY),
                "stop": ["</json>"],               # 只用一个最关键的 stop
                "n_predict": int(n_predict),
                "stream": False,
            }
        if mode == "openai_completions":
            return {
                "model": "local",
                "prompt": prompt,
                "temperature": float(temp),
                "top_p": float(DEFAULT_TOP_P),
                "max_tokens": int(n_predict),
                "stop": ["</json>"],
                "stream": False,
            }
        if mode == "openai_chat":
            return {
                "model": "local",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": float(temp),
                "top_p": float(DEFAULT_TOP_P),
                "max_tokens": int(n_predict),
                "stop": ["</json>"],
                "stream": False,
            }
        raise ValueError(f"unknown mode={mode}")

    def _parse_text(self, mode: str, data: Dict[str, Any]) -> str:
        """从不同模式返回的 JSON 中提取文本内容"""
        if not isinstance(data, dict):
            return ""

        if mode == "llamacpp_completion":
            return data.get("content", "") or ""

        if mode == "openai_completions":
            choices = data.get("choices") or []
            if choices and isinstance(choices[0], dict):
                return choices[0].get("text", "") or ""
            return ""

        if mode == "openai_chat":
            choices = data.get("choices") or []
            if choices and isinstance(choices[0], dict):
                msg = choices[0].get("message") or {}
                if isinstance(msg, dict):
                    return msg.get("content", "") or ""
            return ""

        return ""

    def run(self, prompt: str, n_predict: int, temp: Optional[float] = None) -> str:
        """发送请求，返回模型输出文本"""
        payload = self._build_payload(
            self.mode,
            prompt,
            n_predict,
            float(temp if temp is not None else DEFAULT_TEMP)
        )
        if self.debug:
            print(f"[DEBUG] POST {self.url} mode={self.mode} n_predict={n_predict}")
        # 连接超时 10 秒，读取超时 600 秒（确保慢速生成也能完成）
        r = self.sess.post(self.url, json=payload, timeout=(10, 600))
        r.raise_for_status()
        data = r.json()
        text = self._parse_text(self.mode, data)
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError(f"Empty response text (mode={self.mode}, url={self.url})")
        return text


# ---------- Prompt（强制 <json> 包裹）----------
EXTRACTOR_PROMPT = """你是“题材证据抽取器”。从下面文本中抽取“定义题材本体”的证据术语。
文本来源可能是题材详情(detail)、题材理由(reason)或历史驱动事件(history)。

严格规则：
1) 只能从文本中抽取，不能编造。
2) 每条必须给出 spans.text：它必须是原文中连续子串（原样复制）。
3) term 要尽量短且可判别，避免“公司、市场、增长、预计”等泛词。
4) **输出必须包裹在 <json> 和 </json> 之间**，且 <json> 后立刻是 [，</json> 前立刻是 ]。不要任何解释、不要 Markdown。
5) 如果没有证据，输出 <json>[]</json>。尽量输出 8~20 条证据；如果只有 0~2 条，说明你抽取失败，请重新阅读文本再输出。

字段说明：
- kind: anchor(核心装置/材料/概念), component(部件), process(工艺/技术), entity(公司/机构/标准), scene(应用场景)
- polarity: positive(本题材证据) 或 negative(混淆题材证据，用于否决)
- strength: must(硬证据) / should(加分证据) / not_suggest(建议否决)

输出 JSON 数组元素格式：
{{
  "term": "证据词",
  "kind": "anchor|component|process|entity|scene",
  "polarity": "positive|negative",
  "strength": "must|should|not_suggest",
  "spans": {{"text": "原文片段"}},
  "confidence": 0.0~1.0
}}

文本：
{content}

<json>
"""

NORMALIZER_PROMPT = """你是“题材门禁规则生成器”。给你同一题材的候选证据列表（来自不同来源），请生成最终 Gate 规则（must/should/not）。

目标：
- must: 6~10 个“判别锚点”术语（装置/工艺/材料/关键部件/专有术语），用于硬切断。每项必须给解释 explain。
- not: 5~10 个“混淆否决”术语（更属于相邻题材），命中即 veto。每项要说明 reason，尽量指出它更像哪类题材。
- should: 8~20 个加分词（不硬切断）。
- evidence_refs: 每个最终入选 term 至少给 1 条证据引用（source_type + source_id + span_text）。

严格规则：
1) **只能从输入 candidates 中选择 term**（可以做同义词合并，但只能把多个已存在 term 放在同一个 terms 数组里，不能新增不在 candidates 中的词）。
2) 不能编造新术语。
3) must 术语要尽量覆盖不同维度（装置/工艺/材料/关键部件/机构标准）。
4) **输出必须包裹在 <json> 和 </json> 之间**，且 <json> 后立刻是 {，</json> 前立刻是 }。不要任何解释、不要 Markdown。

输出格式：
{{
  "must": [
    {{"terms": ["托卡马克"], "min_hit": 1, "type": "anchor", "explain": "核心装置/原理"}},
    ...
  ],
  "not": [
    {{"terms": ["冷板"], "reason": "液冷散热部件，命中则更像液冷题材", "contrast": "液冷"}},
    ...
  ],
  "should": [
    {{"terms": ["聚变"], "boost": 0.2}},
    ...
  ],
  "evidence_refs": [
    {{"term": "托卡马克", "source_type": "detail", "source_id": "detail_9014636", "span_text": "托卡马克装置"}},
    ...
  ]
}}

输入 candidates（JSON 数组）：
{candidates}

<json>
"""


# ---------- 数据加载（与 v5 完全相同）----------
def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    out = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def split_into_chunks(text: str, chunk_size: int, overlap: int) -> List[str]:
    text = text.strip()
    if not text:
        return []
    parts = re.split(r"(。|；|;|\n)", text)
    segs = []
    buf = ""
    for p in parts:
        if not p:
            continue
        if len(buf) + len(p) <= chunk_size:
            buf += p
        else:
            if buf.strip():
                segs.append(buf.strip())
            tail = buf[-overlap:] if overlap > 0 and len(buf) > overlap else ""
            buf = tail + p
    if buf.strip():
        segs.append(buf.strip())
    return segs


def load_subject_sources(
    data_dir: Path,
    subject_id: str,
    history_topk: int,
    detail_max_chunks: int,
    chunk_size: int,
    overlap: int,
) -> List[Dict[str, Any]]:
    sources = []
    details_file = data_dir / "details" / f"{subject_id}_details.jsonl"
    details = read_jsonl(details_file)
    for item in details:
        reason = clean_html(item.get("reason", "") or "")
        if reason and len(reason) >= 10:
            sources.append(
                {
                    "source_type": "reason",
                    "source_id": f"reason_{subject_id}",
                    "text": reason,
                }
            )
        detail = item.get("detail", "") or item.get("detail_html", "") or ""
        detail = clean_html(detail)
        if detail and len(detail) >= 80:
            chunks = split_into_chunks(detail, chunk_size=chunk_size, overlap=overlap)
            chunks = chunks[:detail_max_chunks]
            for i, ck in enumerate(chunks):
                sources.append(
                    {
                        "source_type": "detail",
                        "source_id": f"detail_{subject_id}_{i}",
                        "text": ck,
                    }
                )

    history_file = data_dir / "history" / f"{subject_id}_history.jsonl"
    history = read_jsonl(history_file)

    def sort_key(x):
        return str(x.get("createTime") or x.get("source_updated_at") or x.get("rankDate") or "")

    history_sorted = sorted(history, key=sort_key, reverse=True) if history else []
    picked = 0
    for it in history_sorted:
        desc = clean_html(it.get("description", "") or "")
        if not desc or len(desc) < DEFAULT_MIN_HISTORY_LEN:
            continue
        sources.append(
            {
                "source_type": "history",
                "source_id": f"hist_{it.get('subjectRankId', '') or sha256(desc)[:8]}",
                "text": desc,
            }
        )
        picked += 1
        if picked >= history_topk:
            break
    return sources


# ---------- 噪声过滤 ----------
def is_noisy_term(term: str) -> bool:
    if re.fullmatch(r"\d+(\.\d+)?", term):
        return True
    if term.endswith(("亿元", "万美元", "万元", "年度", "季度")):
        return True
    noise = {
        "公司", "市场", "行业", "增长", "下降", "预计", "表示", "指出",
        "报道", "日讯", "公告", "相关", "发布", "推进", "规划", "建设",
        "落地", "实施", "提升", "保持", "持续"
    }
    if term in noise:
        return True
    return False


def filter_and_attach_source(
    cands: List[Dict[str, Any]], source_type: str, source_id: str, content: str
) -> List[Dict[str, Any]]:
    out = []
    for c in cands:
        term = str(c.get("term", "")).strip()
        if len(term) < MIN_TERM_LEN or is_noisy_term(term):
            continue
        conf = float(c.get("confidence", 0) or 0)
        if conf < MIN_CONF_EXTRACT:
            continue
        spans = c.get("spans") or {}
        span_text = str(spans.get("text", "")).strip()
        if not span_text or span_text not in content:
            if term in content:
                span_text = term
            else:
                continue
        out.append(
            {
                "term": term,
                "kind": str(c.get("kind", "anchor")),
                "polarity": str(c.get("polarity", "positive")),
                "strength": str(c.get("strength", "should")),
                "confidence": conf,
                "source_type": source_type,
                "source_id": source_id,
                "span_text": span_text,
            }
        )
    return out


def dedup_candidates(cands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    best = {}
    for c in cands:
        key = (c["term"], c["polarity"], c["strength"], c["kind"])
        if key not in best or c["confidence"] > best[key]["confidence"]:
            best[key] = c
    return list(best.values())


# ---------- Extractor ----------
def llm_extract_candidates(
    llm: LlamaServer,
    content: str,
    n_predict: int,
    retries: int = 2,
    subject_id: str = ""
) -> List[Dict[str, Any]]:
    prompt = EXTRACTOR_PROMPT.format(content=content)
    for attempt in range(retries + 1):
        out = ""
        try:
            temp = 0.2 if attempt == 1 else None
            out = llm.run(prompt, n_predict=n_predict, temp=temp)
            block = extract_json_block(out) or out
            data = safe_json_loads(block)
            if isinstance(data, list):
                if len(data) < EXTRACT_MIN_COUNT and attempt < retries:
                    continue
                return [x for x in data if isinstance(x, dict)]
            return []
        except Exception as e:
            debug_dir = DEBUG_DIR / subject_id
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / f"extract_raw_{sha256(content)[:8]}_attempt{attempt}.txt"
            debug_file.write_text(out or f"[no stdout]\n{repr(e)}", encoding="utf-8")
            if attempt == retries:
                raise
            time.sleep(0.6)
    return []


# ---------- Normalizer ----------
def llm_normalize_gate(
    llm: LlamaServer,
    subject_id: str,
    candidates: List[Dict[str, Any]],
    n_predict: int,
    retries: int = 2,
) -> Optional[Dict[str, Any]]:
    candidates_sorted = sorted(candidates, key=lambda x: x.get("confidence", 0), reverse=True)[:150]
    prompt = NORMALIZER_PROMPT.format(candidates=json.dumps(candidates_sorted, ensure_ascii=False))

    for attempt in range(retries + 1):
        out = ""
        try:
            out = llm.run(prompt, n_predict=n_predict)
            print(f"[DEBUG] Normalizer raw output: {out[:500]}...")  # 打印前500字符
            block = extract_json_block(out) or out
            data = safe_json_loads(block)
            if isinstance(data, dict):
                data["subject_id"] = int(subject_id) if str(subject_id).isdigit() else subject_id
                return data
            return None
        except Exception as e:
            debug_dir = DEBUG_DIR / subject_id
            debug_dir.mkdir(parents=True, exist_ok=True)
            debug_file = debug_dir / f"norm_raw_attempt{attempt}.txt"
            debug_file.write_text(out or f"[no stdout]\n{repr(e)}", encoding="utf-8")
            if attempt == retries:
                raise
            time.sleep(0.8)
    
    if isinstance(data, dict):
        # 确保必要字段存在，避免后续 KeyError
        data.setdefault("must", [])
        data.setdefault("not", [])
        data.setdefault("should", [])
        data.setdefault("evidence_refs", [])
        data["subject_id"] = int(subject_id) if str(subject_id).isdigit() else subject_id
        return data

    return None


# ---------- Gate 校验与后处理 ----------
def validate_gate(gate: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons = []
    must = gate.get("must") or []
    if not isinstance(must, list) or len(must) == 0:
        reasons.append("NO_MUST")
    else:
        types = [m.get("type") for m in must if isinstance(m, dict)]
        if not any(t in ("anchor", "process") for t in types):
            reasons.append("MUST_TOO_GENERIC")
        entity_count = sum(1 for t in types if t == "entity")
        if len(types) > 0 and entity_count / len(types) > 0.4:
            reasons.append("MUST_ENTITY_HEAVY")
        good = sum(1 for m in must if isinstance(m, dict) and isinstance(m.get("terms"), list) and m["terms"])
        if good == 0:
            reasons.append("MUST_EMPTY")

    ev = gate.get("evidence_refs") or []
    if not isinstance(ev, list) or len(ev) == 0:
        reasons.append("NO_EVIDENCE_REFS")
    else:
        all_terms = set()
        for m in must:
            all_terms.update(m.get("terms", []))
        for n in gate.get("not", []):
            all_terms.update(n.get("terms", []))
        for s in gate.get("should", []):
            all_terms.update(s.get("terms", []))
        for e in ev:
            if e.get("term") not in all_terms:
                reasons.append("EVIDENCE_TERM_MISMATCH")
                break
            if not e.get("source_type") or not e.get("source_id") or not e.get("span_text"):
                reasons.append("EVIDENCE_INCOMPLETE")
                break

    return (len(reasons) == 0, reasons)


def post_process_gate(gate: Dict[str, Any], subject_id: str) -> Dict[str, Any]:
    gate["gate_version"] = gate.get("gate_version", "v1")
    should = gate.get("should") or []
    if isinstance(should, list):
        for s in should:
            if isinstance(s, dict) and "boost" not in s:
                s["boost"] = 0.2
    gate["meta"] = {
        "generated_at": now_iso(),
        "pipeline": "llm_gate_final_v6_server",
    }
    return gate


# ---------- 单个题材处理（加入进度打印）----------
def process_one_subject(
    llm: LlamaServer,
    data_dir: Path,
    subject_id: str,
    out_dir: Path,
    max_calls: int,
    history_topk: int,
    detail_max_chunks: int,
    chunk_size: int,
    overlap: int,
    sleep: float,
) -> Dict[str, Any]:
    calls = 0
    sources = load_subject_sources(
        data_dir, subject_id, history_topk, detail_max_chunks, chunk_size, overlap
    )
    if not sources:
        return {"ok": False, "reason": "NO_SOURCES", "calls": 0, "candidates": 0, "out_path": None}

    candidates = []
    for src in sources:
        if calls >= max_calls - 1:
            break
        print(f"[{subject_id}] extracting from {src['source_type']} {src['source_id']}...")
        raw = llm_extract_candidates(llm, src["text"], n_predict=DEFAULT_N_PREDICT_EXTRACT, retries=2, subject_id=subject_id)
        calls += 1
        print(f"[{subject_id}] -> {len(raw)} raw candidates")
        time.sleep(sleep)
        cleaned = filter_and_attach_source(raw, src["source_type"], src["source_id"], src["text"])
        candidates.extend(cleaned)

    if not candidates:
        return {"ok": False, "reason": "NO_CANDIDATES", "calls": calls, "candidates": 0, "out_path": None}

    candidates = dedup_candidates(candidates)
    print(f"[{subject_id}] after dedup: {len(candidates)} candidates")

    gate = llm_normalize_gate(llm, subject_id, candidates, n_predict=DEFAULT_N_PREDICT_NORM, retries=2)
    calls += 1
    time.sleep(sleep)

    if not gate:
        return {"ok": False, "reason": "NORMALIZER_FAILED", "calls": calls, "candidates": len(candidates), "out_path": None}

    gate = post_process_gate(gate, subject_id)
    ok, problems = validate_gate(gate)
    if not ok:
        gate["risk_flags"] = problems

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{subject_id}_gate_v1.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(gate, f, ensure_ascii=False, indent=2)

    print(f"[OK] wrote: {out_path}")
    return {"ok": ok, "reason": "OK" if ok else ",".join(problems), "calls": calls, "candidates": len(candidates), "out_path": str(out_path)}


# ---------- 主函数 ----------
def scan_subject_ids(data_dir: Path) -> List[str]:
    ids = set()
    history_dir = data_dir / "history"
    details_dir = data_dir / "details"
    if history_dir.exists():
        for f in history_dir.glob("*_history.jsonl"):
            ids.add(f.stem.replace("_history", ""))
    if details_dir.exists():
        for f in details_dir.glob("*_details.jsonl"):
            ids.add(f.stem.replace("_details", ""))
    return sorted(ids)


def main():
    ap = argparse.ArgumentParser(description="LLM Gate Builder (final v6 server-based)")
    ap.add_argument("--data-dir", default="theme_data_complete", help="数据目录")
    ap.add_argument("--out-dir", default="subject_gates_out", help="输出目录")
    ap.add_argument("--subject", help="单个 subject_id")
    ap.add_argument("--batch", action="store_true", help="批量跑全部 subject")
    ap.add_argument("--limit", type=int, default=0, help="批量限制数量")
    ap.add_argument("--ids-file", type=str, default="", help="从文件读取 subject_id 列表，每行一个")
    ap.add_argument("--llama-url", default=DEFAULT_LLAMA_URL, help="llama-server 基础 URL（默认 http://127.0.0.1:8080）")
    ap.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS_PER_SUBJECT)
    ap.add_argument("--history-topk", type=int, default=DEFAULT_HISTORY_TOPK)
    ap.add_argument("--detail-max-chunks", type=int, default=DEFAULT_DETAIL_MAX_CHUNKS)
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    ap.add_argument("--overlap", type=int, default=DEFAULT_CHUNK_OVERLAP)
    ap.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_BETWEEN_CALLS)

    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)

    if not data_dir.exists():
        raise SystemExit(f"data dir not found: {data_dir}")

    # 初始化自适应客户端
    llm = LlamaServer(base_url=args.llama_url, debug=False)  # 改为 True 可看详细日志

    if args.subject:
        subject_ids = [args.subject]
    elif args.ids_file:
        p = Path(args.ids_file)
        if not p.exists():
            raise SystemExit(f"ids file not found: {p}")
        subject_ids = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    elif args.batch:
        subject_ids = scan_subject_ids(data_dir)
        if args.limit > 0:
            subject_ids = subject_ids[: args.limit]
    else:
        raise SystemExit("请指定 --subject 或 --ids-file 或 --batch")

    print(f"subjects: {len(subject_ids)}")
    print(f"llama-server URL: {args.llama_url}")

    stats = {"total": len(subject_ids), "ok": 0, "fail": 0, "fails": {}, "avg_calls": 0, "avg_candidates": 0}
    total_calls, total_candidates = 0, 0

    last_fail_subject = None
    last_fail_reason = None

    for sid in tqdm(subject_ids):
        try:
            r = process_one_subject(
                llm=llm,
                data_dir=data_dir,
                subject_id=str(sid),
                out_dir=out_dir,
                max_calls=args.max_calls,
                history_topk=args.history_topk,
                detail_max_chunks=args.detail_max_chunks,
                chunk_size=args.chunk_size,
                overlap=args.overlap,
                sleep=args.sleep,
            )
            total_calls += r["calls"]
            total_candidates += r["candidates"]
            if r["ok"]:
                stats["ok"] += 1
            else:
                stats["fail"] += 1
                stats["fails"][r["reason"]] = stats["fails"].get(r["reason"], 0) + 1
                last_fail_subject = sid
                last_fail_reason = r["reason"]
        except Exception as e:
            stats["fail"] += 1
            reason = f"EX:{type(e).__name__}"
            stats["fails"][reason] = stats["fails"].get(reason, 0) + 1
            last_fail_subject = sid
            last_fail_reason = reason
        time.sleep(0.15)

    stats["avg_calls"] = round(total_calls / max(1, stats["total"]), 2)
    stats["avg_candidates"] = round(total_candidates / max(1, stats["total"]), 2)

    print("\n==== SUMMARY ====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))

    if last_fail_subject is not None:
        print(f"\n⚠️  Last failed subject: {last_fail_subject} (reason: {last_fail_reason})")
        print(f"   Debug directory: {DEBUG_DIR / last_fail_subject}")
    else:
        print("\n✅ All subjects succeeded!")


if __name__ == "__main__":
    main()