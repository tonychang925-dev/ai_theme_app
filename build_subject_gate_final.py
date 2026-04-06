#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_subject_gate_final_v3.py

基于语义角色判定的题材门禁生成器（ontology 双类型版）
- 四步架构：本体生成 → 术语角色判定 → 核心锚点判定（以题材名称为首要语义约束） → 门禁生成
- 不新增额外分类步骤，直接复用 ontology 生成：
    - semantic_type：开放语义类型（如文化娱乐事件、产业链/供应链、政策法规等）
    - strategy_type：封闭策略类型（industry_chain / policy_driven / event_driven）
- strategy_type 真正参与：
    - core anchor 判定
    - gate 生成
    - soft repair 数量裁剪
    - hard fail 动态阈值
- 术语角色判定和核心锚点判定均采用分批处理，防止候选过多导致 JSON 错误
- 知识文本分层混合采样，保证证据面均衡
- must 语义归并（仅从输入中选择，不改写），should/not 数量硬约束
- 核心锚点判定要求数量控制在 2~6 条，提升 must 精炼度
- 以语义判定为主，辅以少量格式/噪音门禁
- 支持批处理、缓存、断点续传
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from tqdm import tqdm
import dataclasses


# ==================== 配置 ====================
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_TEMP = 0.1
DEFAULT_MAX_TOKENS_ONTOLOGY = 4000
DEFAULT_MAX_TOKENS_ROLE = 4000
DEFAULT_MAX_TOKENS_GATE = 4000
DEFAULT_MAX_TOKENS_EXTRACT = 2000
DEFAULT_MAX_TOKENS_EVENT_PHRASE = 1500
DEFAULT_MAX_TOKENS_MERGE = 1000
DEFAULT_SLEEP = 0.05
DEFAULT_MAX_RETRIES = 3

DEBUG_DIR = Path("llm_debug")

GENERIC_TERMS = {"其它", "其他", "概念", "相关", "综合", "服务", "产业链", "设备更新", "相关概念"}

BANNED_EXACT = {
    "股价", "涨跌幅", "资金流入", "成交额", "估值", "据报道", "据悉", "预计", "可能",
    "资本开支", "IPO", "同比增长", "环比增长", "创新高", "大涨", "利好", "消息称",
    "业内人士表示", "财联社", "科创板日报", "中国银河证券"
}

BANNED_PATTERN = [
    r"20\d{2}年",
    r"\d+(\.\d+)?%",
    r"\d+(\.\d+)?(亿|万)?美元",
    r"\d+nm",
    r"iPhone\s*\d+",
    r"A\d+\s*制程",
    r"\d+月\d+日",
    r"涨超\d+%",
]

SHOULD_BANNED_PATTERN = BANNED_PATTERN + [
    r"媒体[：:]?\s*",
    r"来源[：:]?\s*",
    r"日讯",
    r"报道",
]

NOT_BANNED_PATTERN = [
    r"媒体[：:]?\s*",
    r"来源[：:]?\s*",
    r"日讯",
    r"报道",
]

STRATEGY_CONFIG = {
    "industry_chain": {
        "must_min": 1,
        "should_min": 0,
        "not_min": 0,
        "must_max": 6,
        "should_max": 12,
        "not_max": 8,
        "label": "产业/供应链类",
    },
    "policy_driven": {
        "must_min": 1,
        "should_min": 0,
        "not_min": 0,
        "must_max": 5,
        "should_max": 10,
        "not_max": 6,
        "label": "政策驱动类",
    },
    "event_driven": {
        "must_min": 1,
        "should_min": 1,
        "not_min": 0,
        "must_max": 4,
        "should_max": 8,
        "not_max": 4,
        "label": "事件驱动类",
    },
}
# ==============================================


# ==================== 缓存辅助函数 ====================
def compute_input_hash(*args) -> str:
    h = hashlib.md5()
    for arg in args:
        if isinstance(arg, (list, dict)):
            h.update(json.dumps(arg, sort_keys=True).encode("utf-8"))
        elif isinstance(arg, str):
            h.update(arg.encode("utf-8"))
        elif isinstance(arg, bytes):
            h.update(arg)
        elif arg is not None:
            h.update(str(arg).encode("utf-8"))
    return h.hexdigest()[:16]


def get_cache_path(cache_dir: Path, subject_id: str, step: str, input_hash: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{subject_id}_{step}_{input_hash}.json"


def load_cache(cache_path: Path) -> Optional[Any]:
    if cache_path.exists():
        try:
            with cache_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("result")
        except Exception:
            pass
    return None


def save_cache(cache_path: Path, result: Any) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("w", encoding="utf-8") as f:
        json.dump({"result": result}, f, ensure_ascii=False, indent=2)


# ==============================================

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


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
                obj = json.loads(line)
                if isinstance(obj, dict):
                    out.append(obj)
            except json.JSONDecodeError:
                continue
    return out


def has_real_text(block: Dict) -> bool:
    text = block.get("text", "")
    return bool(text and not text.startswith(("[HEADING]", "[IMAGE]", "[IMAGE_ONLY]")))


def ensure_preprocessed(data_dir: Path, subject_id: str, force_rebuild: bool = False) -> bool:
    core_path = data_dir / "knowledge_core" / f"{subject_id}_knowledge_core.jsonl"
    related_path = data_dir / "knowledge_related" / f"{subject_id}_knowledge_related.jsonl"
    signal_path = data_dir / "knowledge_signal" / f"{subject_id}_knowledge_signal.jsonl"

    if not force_rebuild and (core_path.exists() or related_path.exists() or signal_path.exists()):
        return True

    details_file = data_dir / "details" / f"{subject_id}_details.jsonl"
    if not details_file.exists():
        print(f"  [预处理] 原始 details 文件不存在: {details_file}")
        return False

    script_path = Path(__file__).parent / "build_subject_blocks_from_details_v4.py"
    if not script_path.exists():
        print(f"  [预处理] 预处理脚本不存在: {script_path}")
        return False

    print("  预处理文件缺失或强制重建，正在调用 v4 脚本生成...")
    try:
        cmd = [
            sys.executable,
            str(script_path),
            "--data-dir", str(data_dir),
            "--subject", subject_id,
            "--mode", "all",
        ]
        if force_rebuild:
            cmd.append("--force-refresh")

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
        )
        print("  预处理完成")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  预处理失败: {e.stderr}")
        return False


def has_knowledge_sources(data_dir: Path, subject_id: str) -> Tuple[bool, int, bool, bool, bool]:
    core_path = data_dir / "knowledge_core" / f"{subject_id}_knowledge_core.jsonl"
    related_path = data_dir / "knowledge_related" / f"{subject_id}_knowledge_related.jsonl"
    children_file = data_dir / "children" / f"{subject_id}_children.jsonl"

    has_core = core_path.exists() and any(has_real_text(b) for b in read_jsonl(core_path))
    has_related = related_path.exists() and any(has_real_text(b) for b in read_jsonl(related_path))
    has_children = children_file.exists() and children_file.stat().st_size > 0

    knowledge_count = sum([has_core, has_related, has_children])
    return (knowledge_count > 0, knowledge_count, has_core, has_related, has_children)


def get_strategy_label(strategy_type: str) -> str:
    return STRATEGY_CONFIG.get(strategy_type, {}).get("label", strategy_type)


def build_strategy_guidance(strategy_type: str) -> str:
    if strategy_type == "industry_chain":
        return (
            "当前题材策略类型：industry_chain（产业/供应链类）。\n"
            "判定重点：优先识别能够稳定指向产业对象、技术对象、材料对象、关键环节、设备或产品的术语。\n"
            "primary_anchor 应尽量覆盖核心产业对象/技术对象/关键环节；not 应具备一定边界排除能力。"
        )
    if strategy_type == "policy_driven":
        return (
            "当前题材策略类型：policy_driven（政策驱动类）。\n"
            "判定重点：优先识别政策主体、政策动作、政策对象、执行措施、试点范围、监管措施等术语。\n"
            "primary_anchor 应优先覆盖政策动作与政策对象；not 可以为空，不要为了凑数强行生成。"
        )
    return (
        "当前题材策略类型：event_driven（事件驱动类）。\n"
        "判定重点：优先识别时间窗口、事件对象、核心数据口径、直接催化对象等术语。\n"
        "primary_anchor 通常覆盖时间窗口与事件对象/核心数据口径；not 可以为空，不要为了凑数强行生成。"
    )


# -------------------- LLM Client --------------------
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
        debug_tag: str = "deepseek",
        subject_id: str = "unknown",
        max_retries: int = 3,
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

        debug_dir = DEBUG_DIR / str(subject_id)
        debug_dir.mkdir(parents=True, exist_ok=True)

        backoff = 1.2
        last_err = None

        for attempt in range(max_retries + 1):
            try:
                r = self.sess.post(url, headers=headers, json=payload, timeout=(10, 600))
                if r.status_code == 429 or r.status_code >= 500:
                    time.sleep(backoff)
                    backoff = min(backoff * 1.8, 12.0)
                    continue
                r.raise_for_status()
                data = r.json()

                (debug_dir / f"{debug_tag}_raw_attempt{attempt}.json").write_text(
                    json.dumps(data, ensure_ascii=False, indent=2)[:200000], encoding="utf-8"
                )

                content = data["choices"][0]["message"]["content"]
                if not content.strip():
                    raise RuntimeError("Empty content")

                try:
                    obj = json.loads(content)
                except json.JSONDecodeError:
                    block = self._extract_json_block_loose(content)
                    if block:
                        obj = json.loads(block)
                    else:
                        raise

                if isinstance(obj, list):
                    obj = {"items": obj}
                if not isinstance(obj, dict):
                    raise RuntimeError(f"Not a dict: {content[:200]}")
                return obj

            except Exception as e:
                last_err = e
                if "r" in locals() and hasattr(r, "status_code") and r.status_code == 400:
                    error_body = r.text[:500]
                    print(f"\n[ERROR] DeepSeek 400 Response: {error_body}\n")
                    (debug_dir / f"{debug_tag}_400_error.txt").write_text(r.text, encoding="utf-8")
                (debug_dir / f"{debug_tag}_exception_attempt{attempt}.txt").write_text(repr(e), encoding="utf-8")

                if attempt < max_retries:
                    time.sleep(backoff)
                    backoff = min(backoff * 1.6, 12.0)
                    continue
                break

        raise RuntimeError(f"Failed after retries: {repr(last_err)}")


# -------------------- 事件短术语抽取 --------------------
EVENT_PHRASE_EXTRACT_SYSTEM = """你是一个事件短术语抽取器。你必须输出合法的 JSON 对象。

给定若干事件文本，请只抽取可用于题材门禁的“短术语”，用于 should/not 候选。
要求：
1. 只输出连续短语，不要整句，不要解释。
2. 每条尽量 2~12 个字。
3. 优先抽取：事件名称、措施名称、组织/党派/主体、政策动作、关键争议点。
4. 对于档期/节庆/消费窗口类事件，优先抽取时间窗口、上映/定档/预售/排片/票房/客流/销量等数据口径相关短术语。
5. 不要输出日期、金额、百分比、媒体来源。
6. 不要发明术语，必须来自原文。

输出格式：
{
  "items": [
    {"term": "术语1"},
    {"term": "术语2"}
  ]
}
"""


def extract_event_phrases(
    ds: DeepSeekClient,
    events: List[Dict[str, Any]],
    subject_id: str,
    max_events: int = 5,
) -> List[str]:
    if not events:
        return []

    sorted_events = get_sorted_events(events)[:max_events]
    event_texts = []
    for e in sorted_events:
        txt = str(e.get("text", "") or "").strip()
        title = str(e.get("title", "") or "").strip()
        if title and title not in txt:
            event_texts.append(f"{title}\n{txt}".strip())
        elif txt:
            event_texts.append(txt)
        elif title:
            event_texts.append(title)

    if not event_texts:
        return []

    prompt = f"""事件文本：
{json.dumps(event_texts, ensure_ascii=False, indent=2)}

请抽取适合作为题材门禁候选的事件短术语。"""

    messages = [
        {"role": "system", "content": EVENT_PHRASE_EXTRACT_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    try:
        resp = ds.run_json_object(
            messages,
            max_tokens=DEFAULT_MAX_TOKENS_EVENT_PHRASE,
            temperature=0.1,
            debug_tag="event_phrase_extract",
            subject_id=subject_id,
        )
    except Exception as e:
        print(f"  [事件短术语抽取] 失败: {e}")
        return []

    out = []
    seen = set()
    for item in resp.get("items", []):
        if not isinstance(item, dict):
            continue
        term = str(item.get("term", "") or "").strip()
        if not term or term in seen:
            continue
        if len(term) > 16:
            continue
        seen.add(term)
        out.append(term)
    return out


# -------------------- 知识术语抽取 --------------------
EXTRACT_TERMS_SYSTEM = """你是一个题材关键术语抽取器。你必须输出合法的 JSON 对象。
给定题材名称和若干知识文本，从中抽取能够代表该题材核心对象的关键术语。
要求：
1. 抽取的术语应为原文中的连续短语，长度不超过5个汉字或英文单词组合。
2. 优先抽取具体品类、材料、技术、措施、公司、产品、政策名称等实体类术语。
3. 若题材属于事件驱动类，也可抽取时间窗口、事件对象、关键数据口径、发行/上映/预售/排片/票房/客流等直接描述事件交易主轴的短术语。
4. 不要抽取描述性长句、解释性内容或抽象概念。
5. 术语应具有稳定性和辨识度。

输出格式：
{
  "terms": ["术语1", "术语2", ...]
}
"""


def extract_knowledge_terms(
    ds: DeepSeekClient,
    subject_name: str,
    knowledge_texts: List[str],
    subject_id: str
) -> List[str]:
    if not knowledge_texts:
        return []
    sample = "\n\n".join(knowledge_texts[:3])
    prompt = f"题材名称：{subject_name}\n\n知识文本：\n{sample}\n\n请从中抽取关键术语。"
    messages = [
        {"role": "system", "content": EXTRACT_TERMS_SYSTEM},
        {"role": "user", "content": prompt}
    ]
    try:
        resp = ds.run_json_object(
            messages,
            max_tokens=DEFAULT_MAX_TOKENS_EXTRACT,
            temperature=0.1,
            debug_tag="extract_terms",
            subject_id=subject_id
        )
        terms = resp.get("terms", [])
        if isinstance(terms, list):
            seen = set()
            cleaned = []
            for t in terms:
                t = str(t).strip()
                if t and t not in seen and len(t) <= 20:
                    seen.add(t)
                    cleaned.append(t)
            return cleaned
        return []
    except Exception as e:
        print(f"  [术语抽取] 失败: {e}")
        return []


# -------------------- 本体生成提示词（修改版） --------------------
ONTOLOGY_SYSTEM = """你是一个题材本体生成器。你必须输出合法的 JSON 对象。

根据提供的题材知识块文本和已知子类词条，完成以下任务：

1. 判断该题材的语义类型 semantic_type。
   semantic_type 是对题材内容本身的语义描述，可以灵活表达，例如：
   - 政策法规
   - 国际突发地缘政治事件
   - 产业链/供应链
   - 技术突破
   - 供需变化
   - 公司事件
   - 文化娱乐事件
   - 节庆消费事件
   但不限于这些，请根据实际内容判断。

2. 同时判断该题材在“题材匹配与门禁生成”中应采用的策略类型 strategy_type。
   strategy_type 只能是以下三类之一：
   - industry_chain：产业/供应链类
   - policy_driven：政策驱动类
   - event_driven：事件驱动类

   三类定义：
   - industry_chain：
     题材核心是较稳定的产业结构、技术链条、材料/设备/产品/环节、上下游关系、应用链条。
   - policy_driven：
     题材核心是政策主体、政策动作、政策对象、试点/规划/监管/补贴/限制等政策变化带来的主题强化。
   - event_driven：
     题材核心是具体事件、时间窗口、节庆档期、展会大会、文娱体育事件、消费窗口、发布会、突发事件等。

   注意：
   - semantic_type 和 strategy_type 不是一回事。
   - semantic_type 可以更细、更自由；
   - strategy_type 必须严格限制在三类中，用于后续匹配策略路由。
   - 你必须根据题材的真实语义主轴来判断 strategy_type，不要机械依赖个别词语。

3. 根据题材的语义结构，自行选择最合适的维度（字段名）来组织题材的核心语义。每个维度是一个术语列表，维度名由你根据题材特点命名。
   - 例如，对于产业链题材，维度可能包括 "核心环节"、"关键公司"、"上游材料"、"下游应用"、"驱动因素" 等。
   - 对于政策题材，维度可能包括 "政策名称"、"发布机构"、"涉及领域"、"影响主体"、"关键条款" 等。
   - 对于事件题材，维度可能包括 "事件名称"、"时间窗口"、"参与主体"、"关键指标"、"催化对象" 等。

4. 所有术语必须源自提供的知识块文本或已知子类词条，不得编造。术语应为原文中的连续短语，避免长句或解释性内容。

输出格式：
{
  "concept": "题材的核心概念（简短名称）",
  "semantic_type": "题材语义类型",
  "strategy_type": "industry_chain|policy_driven|event_driven",
  "dimensions": {
    "维度名1": ["术语1", "术语2", ...],
    "维度名2": ["术语1", "术语2", ...]
  }
}

请确保：
1. dimensions 的结构能清晰反映题材本质；
2. 维度名具有解释性；
3. semantic_type 与 strategy_type 语义一致但层级不同；
4. strategy_type 必须严格三选一。
"""


# -------------------- 术语角色判定提示词 --------------------
TERM_ROLE_JUDGE_SYSTEM = """你是一个题材门禁术语角色判定器。你必须输出合法的 JSON 对象。

给定：
1. 题材概念 concept
2. 题材语义类型 semantic_type（仅作参考，不要过度依赖）
3. 题材策略类型 strategy_type（仅作参考，不要机械依赖）
4. 题材本体 dimensions
5. 原始知识证据文本
6. 近期事件摘要
7. 候选术语列表

请对每个候选术语判定它在题材门禁中的角色，只能输出以下之一：
- anchor_term：可作为题材识别中的稳定命中点，可进入 must
- descriptive_term：描述作用、特征、关系、影响、逻辑的术语，不宜单独作为题材锚点，只能进入 should
- event_term：来自事件或短期变化的术语，只能进入 should/not
- meta_label：维度名、类型名、概念标签、组织框架词，禁止进入 gate
- drop：噪音、不稳定、过泛或无效术语

判定原则（通用）：
1. anchor_term 必须是能脱离上下文依然稳定指向题材核心对象的术语，如具体措施、具体品类、关键环节、技术名、材料名、设备名、政策名、产业对象名。
2. descriptive_term 是对对象的性质、作用、价值、特点、影响、关系的描述，不应作为 must。
3. meta_label 包括 dimensions 的键名、semantic_type、strategy_type、concept、抽象分类标签。
4. 不要发明术语，必须基于给定候选术语和证据判断。

输出格式：
{
  "items": [
    {
      "term": "术语",
      "role": "anchor_term|descriptive_term|event_term|meta_label|drop",
      "confidence": 0.0,
      "reason": "..."
    }
  ]
}
"""


# -------------------- 核心锚点判定提示词 --------------------
GATE_CORE_JUDGE_SYSTEM = """你是一个题材核心 gate 判定器。你必须输出合法的 JSON 对象。

给定：
1. 题材名称（分析师手工命名，首要语义约束）：这是对题材最核心、最稳定的定义。
2. 题材概念 concept（由模型从详情中抽象，辅助参考）
3. 题材语义类型 semantic_type
4. 题材策略类型 strategy_type
5. 题材本体 dimensions
6. 原始知识证据文本
7. 已被判定为 anchor_term 的术语列表

你的任务：
对每个 anchor_term 判断它在“当前题材最终门禁”中的地位，只能输出以下之一：
- primary_anchor：最符合题材名称所定义的核心语义，最适合作为当前题材最终 gate 的核心锚点，可进入 must
- secondary_anchor：与题材相关，但与题材名称定义的核心语义不够直接吻合，更适合作为辅助识别信息，只能进入 should

判定原则：
1. 题材名称是首要判断依据。你必须优先判断该术语是否直接贴合题材名称所表达的核心对象、核心范围或核心含义。
2. 题材名称是分析师手工命名的，具有最高优先级，不应被详情中的局部材料或知识稀释。
3. 题材名称是首要约束，但应基于题材名称的真实语义去理解，不要只做字面匹配；若某术语虽不与题材名称逐字一致，但明显直接对应题材名称的核心含义，仍可判为 primary_anchor。
4. primary_anchor 的标准不是“是否重要”，而是“是否最符合题材名称定义，并最适合作为最终门禁中的 must”。
5. 如果某术语虽然在知识上重要，但与题材名称的核心定义不够直接一致，则应判为 secondary_anchor。
6. primary_anchor 应尽量少而精，数量控制在 2~6 条，保持最终 gate 的强区分度和精炼度。不要把大量相关术语都判为 primary_anchor。
7. 若策略类型为 industry_chain，primary_anchor 优先选择能稳定指向产业对象、技术对象、材料对象、关键环节的术语。
8. 若策略类型为 policy_driven，primary_anchor 优先选择政策动作、政策主体、政策对象、执行措施等术语。
9. 若策略类型为 event_driven，primary_anchor 优先选择时间窗口、事件对象、核心数据口径、直接催化对象等术语。
10. 不同策略类型下，primary_anchor 的“适合作为 must”的标准不同，应按策略类型判断。
11. 不要发明新术语，只对给定 anchor_term 做判定。

输出格式：
{
  "items": [
    {
      "term": "术语",
      "anchor_level": "primary_anchor|secondary_anchor",
      "confidence": 0.0,
      "reason": "..."
    }
  ]
}
"""


# -------------------- must 归并提示词 --------------------
MERGE_MUST_SYSTEM = """你是一个术语归并器。你必须输出合法的 JSON 对象。

给定一个题材名称和若干候选术语，请进行语义归并，输出精简后的术语列表。

要求：
1. 删除重复、近义、语义高度重合的术语。
2. 如果多个术语表达的是同一核心含义，只能从输入术语中选择保留项，不允许改写、不允许缩写、不允许生成新的表达。
3. 归并后的术语列表应尽量保持题材核心 gate 的清晰性与区分度。
4. 不要发明新术语，只能原样返回输入列表中的术语。

输出格式：
{"terms": ["术语1", "术语2", ...]}
"""


# -------------------- 门禁生成提示词 --------------------
GATE_SYSTEM = """你是一个题材门禁规则生成器。你必须输出合法的 JSON 对象。

你将收到：
1. 题材本体
2. 题材策略类型 strategy_type
3. 已做过核心判定的术语池：
   - primary_anchor：最符合题材名称的核心锚点
   - secondary_anchor：高度相关但应进入 should 的次级锚点
   - descriptive_term：描述性术语
   - event_term：事件术语

输出格式：
{
  "must": ["术语1", "术语2", ...],
  "should": ["术语1", "术语2", ...],
  "not": ["术语1", "术语2", ...],
  "evidence_refs": [
    {"term": "术语1", "source": "primary_anchor", "source_id": "primary_anchor", "span_text": "术语1"}
  ]
}

严格规则：
1. must 只能从 primary_anchor 列表中逐字逐项拷贝选择，禁止改写、禁止缩写、禁止同义替换。
2. should 只能从 secondary_anchor、descriptive_term、event_term 中选择。
3. not 只能从 event_term 中优先选择那些容易造成误判、但明显不属于当前题材主线的词；如果不合适，可以为空。
4. 不得把维度名、semantic_type、strategy_type、concept、抽象标签、组织框架词放进任何字段。
5. evidence_refs 只为 must 提供证据，且 source/source_id 固定写 primary_anchor；其中 term 和 span_text 必须与 must 中术语完全一致。
6. primary_anchor 必须优先覆盖题材当前最核心的对象、措施、抓手。
7. secondary_anchor 虽然相关，但如果更偏背景依赖、配套领域、相关产业，不应进入 must。
8. 若策略类型为 industry_chain：
   - must 通常应覆盖核心产业对象/技术对象/关键环节；
   - not 应尽量提供，体现边界排除能力。
9. 若策略类型为 policy_driven：
   - must 通常覆盖政策动作与政策对象；
   - not 可以为空，不要为了凑数强行生成。
10. 若策略类型为 event_driven：
   - must 通常覆盖时间窗口与事件对象/核心数据口径；
   - not 可以为空，不要为了凑数强行生成；
   - should 不要堆太多泛类型标签。
"""


# -------------------- 辅助函数 --------------------
def chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def sample_knowledge_texts(core_blocks, related_blocks, signal_blocks, all_blocks=None, max_total=12):
    texts = []
    texts.extend([blk["text"] for blk in core_blocks if has_real_text(blk)][:8])
    texts.extend([blk["text"] for blk in related_blocks if has_real_text(blk)][:6])
    texts.extend([blk["text"] for blk in signal_blocks if has_real_text(blk)][:4])

    unique = []
    seen = set()
    for t in texts:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    if all_blocks and len(unique) < max_total:
        for blk in all_blocks:
            t = blk.get("text", "")
            if not t or t in seen:
                continue
            if not has_real_text(blk):
                continue
            seen.add(t)
            unique.append(t)
            if len(unique) >= max_total:
                break

    return unique[:max_total]


# -------------------- 数据模型 --------------------
@dataclasses.dataclass
class SubjectDetail:
    subject_id: str
    name: str
    reason: str
    detail_html: str
    source_id: str
    source_type: Optional[int] = None


# -------------------- 查找题材详情记录 --------------------
def find_subject_detail_record(data_dir: Path, subject_id: str) -> SubjectDetail:
    subject_id_str = str(subject_id)
    candidates: List[Path] = []

    for ext in (".jsonl", ".json"):
        for p in data_dir.rglob(f"*{subject_id_str}*{ext}"):
            if "detail" in p.name.lower() or "subject" in p.name.lower():
                candidates.append(p)

    if not candidates:
        for ext in (".jsonl", ".json"):
            for p in data_dir.rglob(f"*{subject_id_str}*{ext}"):
                candidates.append(p)

    candidates.sort(key=lambda x: (len(x.name), x.stat().st_size if x.exists() else 10**18))

    print(f"  找到 {len(candidates)} 个包含 ID {subject_id_str} 的候选文件")

    def parse_type(val: Any) -> Optional[int]:
        try:
            if val is None or val == "":
                return None
            return int(val)
        except Exception:
            return None

    def record_from_obj(obj: dict, sid: str) -> Optional[SubjectDetail]:
        id_fields = ["subjectId", "subject_id", "bizKey", "biz_key", "id", "ID", "subjectID"]
        _sid = None
        for field in id_fields:
            val = obj.get(field)
            if val is not None:
                _sid = str(val)
                break
        if _sid != sid:
            return None

        name = obj.get("name") or obj.get("subjectName") or obj.get("subject_name") or sid
        reason = obj.get("reason") or ""
        detail_html = obj.get("detail") or obj.get("detail_html") or obj.get("content") or ""
        source_id = obj.get("source_id") or obj.get("sourceId") or f"detail_{sid}_0"
        source_type = parse_type(obj.get("type"))

        if detail_html:
            return SubjectDetail(
                subject_id=sid,
                name=str(name),
                reason=str(reason),
                detail_html=str(detail_html),
                source_id=str(source_id),
                source_type=source_type,
            )
        return None

    def iter_candidate_objs(obj: dict) -> List[dict]:
        out = [obj]
        if isinstance(obj.get("data"), dict):
            out.append(obj["data"])
        return out

    for p in candidates[:50]:
        try:
            rows = read_jsonl(p)
        except Exception as e:
            print(f"    解析文件 {p} 失败: {e}")
            continue

        for obj in rows:
            if not isinstance(obj, dict):
                continue
            for candidate in iter_candidate_objs(obj):
                rec = record_from_obj(candidate, subject_id_str)
                if rec:
                    print(f"    成功从 {p} 找到题材记录，名称：{rec.name}")
                    return rec

    print("  未在候选文件中找到，开始全目录扫描（最多500个文件）...")
    scanned = 0
    for p in data_dir.rglob("*.jsonl"):
        scanned += 1
        if scanned > 500:
            break
        try:
            rows = read_jsonl(p)
        except Exception:
            continue

        for obj in rows:
            if not isinstance(obj, dict):
                continue
            for candidate in iter_candidate_objs(obj):
                rec = record_from_obj(candidate, subject_id_str)
                if rec and rec.detail_html:
                    print(f"    成功从 {p} 找到题材记录，名称：{rec.name}")
                    return rec

    raise FileNotFoundError(
        f"\n无法找到 subject_id={subject_id_str} 的详情 HTML。\n"
        f"已扫描 {len(candidates)} 个候选文件和至少 {scanned} 个全局文件。"
    )


# -------------------- 本体生成 --------------------
def generate_ontology(
    ds: DeepSeekClient,
    knowledge_texts: List[str],
    children_terms: List[str],
    subject_id: str,
    cache_dir: Path,
    force_refresh: bool
) -> Dict:
    print("  [本体生成] 开始...")
    sample_texts = []
    for t in knowledge_texts:
        if 50 < len(t) < 2000:
            sample_texts.append(t)
        if len(sample_texts) >= 5:
            break
    if not sample_texts:
        sample_texts = knowledge_texts[:5]

    combined_text = "\n\n".join(sample_texts)
    children_hint = f"已知子类词条：{', '.join(children_terms[:30])}" if children_terms else "无已知子类词条"

    input_hash = compute_input_hash(combined_text, children_terms)
    cache_path = get_cache_path(cache_dir, subject_id, "ontology", input_hash)

    if not force_refresh:
        cached = load_cache(cache_path)
        if cached is not None:
            print("  [本体生成] 使用缓存")
            ontology = cached
            ontology.setdefault("concept", "")
            if "semantic_type" not in ontology:
                ontology["semantic_type"] = ontology.get("type", "未知")
            ontology.setdefault("strategy_type", "industry_chain")
            ontology.setdefault("dimensions", {})
            return ontology

    prompt = f"""题材知识文本：
{combined_text}

{children_hint}

请根据以上信息生成题材本体。"""

    messages = [
        {"role": "system", "content": ONTOLOGY_SYSTEM},
        {"role": "user", "content": prompt}
    ]

    t0 = time.time()
    try:
        ontology = ds.run_json_object(
            messages,
            max_tokens=DEFAULT_MAX_TOKENS_ONTOLOGY,
            temperature=0.1,
            debug_tag="ontology",
            subject_id=subject_id
        )
        ontology.setdefault("concept", "")
        if "semantic_type" not in ontology:
            ontology["semantic_type"] = ontology.get("type", "未知")
        ontology.setdefault("strategy_type", "industry_chain")
        if ontology["strategy_type"] not in STRATEGY_CONFIG:
            ontology["strategy_type"] = "industry_chain"
        ontology.setdefault("dimensions", {})
        print(
            f"  [本体生成] 完成，semantic_type：{ontology['semantic_type']}，"
            f"strategy_type：{ontology['strategy_type']}，维度数：{len(ontology['dimensions'])}，"
            f"耗时 {time.time()-t0:.1f}s"
        )
        save_cache(cache_path, ontology)
        return ontology
    except Exception as e:
        print(f"  [本体生成] 失败：{e}")
        raise


# -------------------- 候选术语展开 --------------------
def generate_term_candidates(
    ontology: Dict,
    children_terms: List[str],
    event_phrases: List[str],
    knowledge_terms: List[str],
) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []

    concept = str(ontology.get("concept", "") or "").strip()
    semantic_type = str(ontology.get("semantic_type", ontology.get("type", "")) or "").strip()
    strategy_type = str(ontology.get("strategy_type", "") or "").strip()
    dimensions = ontology.get("dimensions", {}) or {}

    if concept:
        candidates.append({"term": concept, "candidate_source": "concept"})
    if semantic_type:
        candidates.append({"term": semantic_type, "candidate_source": "semantic_type"})
    if strategy_type:
        candidates.append({"term": strategy_type, "candidate_source": "strategy_type"})

    if isinstance(dimensions, dict):
        for dim_name, terms in dimensions.items():
            dim_name = str(dim_name or "").strip()
            if dim_name:
                candidates.append({"term": dim_name, "candidate_source": "dimension_name"})
            if isinstance(terms, list):
                for t in terms:
                    t = str(t or "").strip()
                    if t:
                        candidates.append({"term": t, "candidate_source": f"dimension_value:{dim_name}"})

    for t in children_terms[:20]:
        t = str(t or "").strip()
        if t:
            candidates.append({"term": t, "candidate_source": "children"})

    for t in event_phrases[:30]:
        t = str(t or "").strip()
        if t:
            candidates.append({"term": t, "candidate_source": "event_phrase"})

    for t in knowledge_terms[:30]:
        t = str(t or "").strip()
        if t:
            candidates.append({"term": t, "candidate_source": "knowledge_extracted"})

    out = []
    seen = set()
    for c in candidates:
        term = c["term"]
        if not term or term in seen:
            continue
        seen.add(term)
        out.append(c)
    return out


# -------------------- 术语角色判定 --------------------
def judge_gate_terms(
    ds: DeepSeekClient,
    ontology: Dict,
    knowledge_texts: List[str],
    children_terms: List[str],
    event_summary: str,
    event_phrases: List[str],
    knowledge_terms: List[str],
    subject_id: str,
) -> Dict[str, List[Dict[str, Any]]]:
    print("  [术语角色判定] 开始...")

    candidates = generate_term_candidates(ontology, children_terms, event_phrases, knowledge_terms)

    MAX_CANDIDATES = 80
    if len(candidates) > MAX_CANDIDATES:
        print(f"  [术语角色判定] 候选术语过多: {len(candidates)}，截断为前 {MAX_CANDIDATES} 个")
        candidates = candidates[:MAX_CANDIDATES]

    evidence_text = "\n\n".join(knowledge_texts[:6])

    grouped = {
        "anchor_term": [],
        "descriptive_term": [],
        "event_term": [],
        "meta_label": [],
        "drop": [],
    }

    batches = chunk_list(candidates, 20)
    total_batches = len(batches)
    t0 = time.time()
    seen_terms = set()

    for idx, batch in enumerate(batches, 1):
        prompt = f"""题材本体：
{json.dumps(ontology, ensure_ascii=False, indent=2)}

原始知识证据：
{evidence_text or "无"}

近期事件摘要：
{event_summary or "无"}

事件短术语（部分）：
{json.dumps(event_phrases[:20], ensure_ascii=False, indent=2)}

知识短术语（部分）：
{json.dumps(knowledge_terms[:20], ensure_ascii=False, indent=2)}

候选术语（第 {idx}/{total_batches} 批）：
{json.dumps(batch, ensure_ascii=False, indent=2)}

请逐条判定每个候选术语在题材门禁中的角色。"""

        messages = [
            {"role": "system", "content": TERM_ROLE_JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            resp = ds.run_json_object(
                messages,
                max_tokens=DEFAULT_MAX_TOKENS_ROLE,
                temperature=0.1,
                debug_tag=f"term_role_judge_batch_{idx}",
                subject_id=subject_id,
            )
        except Exception as e:
            print(f"  [术语角色判定] 第 {idx} 批失败: {e}")
            continue

        raw_items = resp.get("items", [])
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term", "") or "").strip()
            role = str(item.get("role", "") or "").strip()
            reason = str(item.get("reason", "") or "").strip()[:300]
            try:
                conf = float(item.get("confidence", 0.0))
            except Exception:
                conf = 0.0

            if not term or role not in grouped:
                continue
            if term in seen_terms:
                continue

            seen_terms.add(term)
            grouped[role].append({
                "term": term,
                "role": role,
                "confidence": max(0.0, min(1.0, conf)),
                "reason": reason,
            })

    elapsed = time.time() - t0
    print(
        f"  [术语角色判定] 完成，anchor={len(grouped['anchor_term'])}, "
        f"desc={len(grouped['descriptive_term'])}, event={len(grouped['event_term'])}, "
        f"meta={len(grouped['meta_label'])}, drop={len(grouped['drop'])}，耗时 {elapsed:.1f}s"
    )

    print("  [术语角色判定详情]")
    for role, items in grouped.items():
        if items:
            terms = [x["term"] for x in items]
            print(f"    {role}: {terms}")

    return grouped


# -------------------- 核心锚点判定 --------------------
def judge_gate_core_anchors(
    ds: DeepSeekClient,
    subject_name: str,
    ontology: Dict[str, Any],
    knowledge_texts: List[str],
    anchor_terms: List[str],
    subject_id: str,
    cache_dir: Path,
    force_refresh: bool,
) -> Dict[str, List[Dict[str, Any]]]:
    print("  [核心锚点判定] 开始...")

    if not anchor_terms:
        return {"primary_anchor": [], "secondary_anchor": []}

    strategy_type = ontology.get("strategy_type", "industry_chain")
    semantic_type = ontology.get("semantic_type", ontology.get("type", "未知"))

    input_hash = compute_input_hash(subject_name, ontology, knowledge_texts, anchor_terms)
    cache_path = get_cache_path(cache_dir, subject_id, "core_anchor", input_hash)

    if not force_refresh:
        cached = load_cache(cache_path)
        if cached is not None:
            print("  [核心锚点判定] 使用缓存")
            return cached

    evidence_text = "\n\n".join(knowledge_texts[:6])
    strategy_guidance = build_strategy_guidance(strategy_type)

    grouped = {
        "primary_anchor": [],
        "secondary_anchor": [],
    }

    batches = chunk_list(anchor_terms, 12)
    total_batches = len(batches)
    t0 = time.time()
    seen_terms = set()

    for idx, batch in enumerate(batches, 1):
        prompt = f"""题材名称（分析师手工命名，首要语义约束）：
{subject_name}

题材语义类型 semantic_type：
{semantic_type}

题材策略类型 strategy_type：
{strategy_type}（{get_strategy_label(strategy_type)}）

策略说明：
{strategy_guidance}

题材本体：
{json.dumps(ontology, ensure_ascii=False, indent=2)}

原始知识证据：
{evidence_text or "无"}

anchor_term 列表（第 {idx}/{total_batches} 批）：
{json.dumps(batch, ensure_ascii=False, indent=2)}

请逐条判断这些 anchor_term 中，哪些最符合题材名称所定义的核心语义，并最适合作为当前题材最终门禁（gate）的核心 must 锚点；哪些虽然相关，但更适合作为 should。"""

        messages = [
            {"role": "system", "content": GATE_CORE_JUDGE_SYSTEM},
            {"role": "user", "content": prompt},
        ]

        try:
            resp = ds.run_json_object(
                messages,
                max_tokens=DEFAULT_MAX_TOKENS_ROLE,
                temperature=0.1,
                debug_tag=f"gate_core_judge_batch_{idx}",
                subject_id=subject_id,
            )
        except Exception as e:
            print(f"  [核心锚点判定] 第 {idx} 批失败: {e}")
            continue

        raw_items = resp.get("items", [])
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            term = str(item.get("term", "") or "").strip()
            level = str(item.get("anchor_level", "") or "").strip()
            reason = str(item.get("reason", "") or "").strip()[:300]
            try:
                conf = float(item.get("confidence", 0.0))
            except Exception:
                conf = 0.0

            if not term or level not in grouped:
                continue
            if term in seen_terms:
                continue

            seen_terms.add(term)
            grouped[level].append({
                "term": term,
                "anchor_level": level,
                "confidence": max(0.0, min(1.0, conf)),
                "reason": reason,
            })

    elapsed = time.time() - t0
    print(
        f"  [核心锚点判定] 完成，primary={len(grouped['primary_anchor'])}, "
        f"secondary={len(grouped['secondary_anchor'])}，耗时 {elapsed:.1f}s"
    )
    print("  [核心锚点判定详情]")
    for level, items in grouped.items():
        if items:
            terms = [x["term"] for x in items]
            print(f"    {level}: {terms}")

    save_cache(cache_path, grouped)
    return grouped


# -------------------- must 归并 --------------------
def merge_must_terms(
    ds: DeepSeekClient,
    subject_name: str,
    must_terms: List[str],
    subject_id: str,
    cache_dir: Path,
    force_refresh: bool,
    min_keep: int = 2,
    max_keep: int = 6,
) -> List[str]:
    if len(must_terms) <= min_keep:
        return must_terms[:max_keep]

    input_hash = compute_input_hash(subject_name, must_terms, min_keep, max_keep)
    cache_path = get_cache_path(cache_dir, subject_id, "merge_must", input_hash)

    if not force_refresh:
        cached = load_cache(cache_path)
        if cached is not None:
            print("  [must归并] 使用缓存")
            return cached

    prompt = f"""题材名称：{subject_name}

候选术语：
{json.dumps(must_terms, ensure_ascii=False, indent=2)}

请对这些候选术语做语义归并，并返回精简后的术语列表。"""

    messages = [
        {"role": "system", "content": MERGE_MUST_SYSTEM},
        {"role": "user", "content": prompt}
    ]

    try:
        resp = ds.run_json_object(
            messages,
            max_tokens=DEFAULT_MAX_TOKENS_MERGE,
            temperature=0.1,
            debug_tag="merge_must",
            subject_id=subject_id,
        )

        merged = resp.get("terms", [])
        if not isinstance(merged, list):
            merged = []

        input_set = set(must_terms)
        cleaned = []
        seen = set()
        for t in merged:
            t = str(t).strip()
            if not t or t in seen:
                continue
            if t not in input_set:
                continue
            seen.add(t)
            cleaned.append(t)

        cleaned = cleaned[:max_keep]

        if len(cleaned) < min_keep:
            fallback = []
            for t in must_terms:
                if t not in fallback:
                    fallback.append(t)
                if len(fallback) >= min_keep:
                    break
            cleaned = fallback[:max_keep]

        save_cache(cache_path, cleaned)
        return cleaned

    except Exception as e:
        print(f"  [must归并] 失败: {e}")
        return must_terms[:max_keep]


# -------------------- 门禁生成 --------------------
def generate_gate_from_ontology(
    ds: DeepSeekClient,
    ontology: Dict,
    judged_terms: Dict[str, List[Dict[str, Any]]],
    anchor_levels: Dict[str, List[Dict[str, Any]]],
    event_summary: str,
    subject_id: str,
) -> Dict:
    print("  [门禁生成] 开始...")

    strategy_type = ontology.get("strategy_type", "industry_chain")
    strategy_guidance = build_strategy_guidance(strategy_type)

    primary_anchor_terms = [x["term"] for x in anchor_levels.get("primary_anchor", [])]
    secondary_anchor_terms = [x["term"] for x in anchor_levels.get("secondary_anchor", [])]
    descriptive_terms = [x["term"] for x in judged_terms.get("descriptive_term", [])]
    event_terms = [x["term"] for x in judged_terms.get("event_term", [])]

    full_prompt = f"""题材策略类型：
{strategy_type}（{get_strategy_label(strategy_type)}）

策略说明：
{strategy_guidance}

题材本体：
{json.dumps(ontology, ensure_ascii=False, indent=2)}

已完成核心判定的术语池：
- primary_anchor（仅这些术语允许进入 must）：
{json.dumps(primary_anchor_terms, ensure_ascii=False, indent=2)}

- secondary_anchor（这些术语高度相关，但只能进入 should，不得进入 must）：
{json.dumps(secondary_anchor_terms, ensure_ascii=False, indent=2)}

- descriptive_term（仅这些术语允许进入 should）：
{json.dumps(descriptive_terms, ensure_ascii=False, indent=2)}

- event_term（仅这些术语允许进入 should/not，不得进入 must）：
{json.dumps(event_terms, ensure_ascii=False, indent=2)}

近期事件摘要（仅用于辅助 should/not）：
{event_summary or '无可用事件'}

请生成最终 gate，严格遵守规则。"""

    messages = [
        {"role": "system", "content": GATE_SYSTEM},
        {"role": "user", "content": full_prompt}
    ]

    t0 = time.time()
    gate = ds.run_json_object(
        messages,
        max_tokens=DEFAULT_MAX_TOKENS_GATE,
        temperature=0.1,
        debug_tag="gate",
        subject_id=subject_id
    )
    gate.setdefault("must", [])
    gate.setdefault("should", [])
    gate.setdefault("not", [])
    gate.setdefault("evidence_refs", [])
    print(f"  [门禁生成] 完成，must: {len(gate['must'])} 条，耗时 {time.time()-t0:.1f}s")
    return gate


# -------------------- 清洗函数 --------------------
def dedup_keep_order(items: List[str]) -> List[str]:
    out = []
    seen = set()
    for x in items:
        if not x or x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def clean_should(items: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for t in items:
        if not t or t in seen:
            continue
        if t in BANNED_EXACT:
            continue
        skip = False
        for pat in SHOULD_BANNED_PATTERN:
            if re.search(pat, t, re.I):
                skip = True
                break
        if skip:
            continue
        seen.add(t)
        cleaned.append(t)
    return cleaned


def clean_not(items: List[str]) -> List[str]:
    cleaned = []
    seen = set()
    for t in items:
        if not t or t in seen:
            continue
        skip = False
        for pat in NOT_BANNED_PATTERN:
            if re.search(pat, t, re.I):
                skip = True
                break
        if skip:
            continue
        seen.add(t)
        cleaned.append(t)
    return cleaned


# -------------------- 后处理修复 --------------------
def soft_repair(
    ds: DeepSeekClient,
    subject_name: str,
    gate: Dict,
    anchor_levels: Dict[str, List[Dict[str, Any]]],
    ontology: Dict[str, Any],
    subject_id: str,
    cache_dir: Path,
    force_refresh: bool,
) -> Dict:
    must = gate.get("must", [])
    should = gate.get("should", [])
    not_list = gate.get("not", [])
    evidence = gate.get("evidence_refs", [])

    print(f"  [修复前] must: {len(must)} 条, should: {len(should)} 条, not: {len(not_list)} 条")

    strategy_type = ontology.get("strategy_type", "industry_chain")
    cfg = STRATEGY_CONFIG.get(strategy_type, STRATEGY_CONFIG["industry_chain"])

    primary_anchor_set = {x["term"] for x in anchor_levels.get("primary_anchor", [])}
    must = [t for t in must if t in primary_anchor_set]
    raw_must_candidates = must[:]

    min_keep = 2 if cfg["must_min"] <= 2 else 3
    max_keep = cfg["must_max"]

    must = merge_must_terms(
        ds=ds,
        subject_name=subject_name,
        must_terms=must,
        subject_id=subject_id,
        cache_dir=cache_dir,
        force_refresh=force_refresh,
        min_keep=min_keep,
        max_keep=max_keep,
    )

    MAX_MUST_LEN = 16
    must = [t for t in must if len(t) <= MAX_MUST_LEN]

    if len(must) < cfg["must_min"]:
        for t in raw_must_candidates:
            if len(t) <= MAX_MUST_LEN and t not in must:
                must.append(t)
            if len(must) >= cfg["must_min"]:
                break

    must = must[:cfg["must_max"]]

    ev_terms = set(must)
    new_evidence = []
    for e in evidence:
        if e.get("term") in ev_terms:
            new_evidence.append({
                "term": e.get("term"),
                "source": "primary_anchor",
                "source_id": "primary_anchor",
                "span_text": e.get("term"),
            })
    gate["evidence_refs"] = new_evidence

    should = clean_should(should)
    not_list = clean_not(not_list)

    MAX_TERM_LEN = 16
    should = [t for t in should if len(t) <= MAX_TERM_LEN]
    not_list = [t for t in not_list if len(t) <= MAX_TERM_LEN]

    should = dedup_keep_order(should)[:cfg["should_max"]]
    not_list = dedup_keep_order(not_list)[:cfg["not_max"]]

    gate["must"] = must
    gate["should"] = should
    gate["not"] = not_list

    print(f"  [修复后] must: {len(must)} 条, should: {len(should)} 条, not: {len(not_list)} 条")
    return gate


# -------------------- 硬失败 --------------------
def is_banned_term(term: str) -> bool:
    if term in BANNED_EXACT:
        return True
    for pat in BANNED_PATTERN:
        if re.search(pat, term, re.I):
            return True
    return False


def hard_fail(
    gate: Dict,
    anchor_levels: Dict[str, List[Dict[str, Any]]],
    ontology: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, List[str]]:
    reasons: List[str] = []

    must = gate.get("must", []) or []
    should = gate.get("should", []) or []
    not_list = gate.get("not", []) or []
    evidence = gate.get("evidence_refs", []) or []

    strategy_type = (ontology or {}).get("strategy_type", "industry_chain")
    cfg = STRATEGY_CONFIG.get(strategy_type, STRATEGY_CONFIG["industry_chain"])

    for t in must:
        if is_banned_term(t):
            reasons.append(f"MUST_CONTAINS_BANNED_TERM:{t}")
            break

    must_set = set(must)
    ev_terms = {e.get("term") for e in evidence if isinstance(e, dict)}
    missing = must_set - ev_terms
    if missing:
        reasons.append(f"MISSING_EVIDENCE:{','.join(list(missing)[:5])}")

    primary_anchor_set = {x["term"] for x in anchor_levels.get("primary_anchor", [])}
    illegal_must = [t for t in must if t not in primary_anchor_set]
    if illegal_must:
        reasons.append("MUST_NOT_FROM_PRIMARY:" + ",".join(illegal_must[:5]))

    if len(must) < cfg["must_min"]:
        reasons.append(f"MUST_TOO_FEW<{cfg['must_min']}>")

    if len(should) < cfg["should_min"]:
        reasons.append(f"SHOULD_TOO_FEW<{cfg['should_min']}>")

    if len(not_list) < cfg["not_min"]:
        reasons.append(f"NOT_TOO_FEW<{cfg['not_min']}>")

    if reasons:
        print(f"  [硬失败] {', '.join(reasons)}")
    else:
        print("  [硬失败] 通过")

    return len(reasons) == 0, reasons


# -------------------- children 加载 --------------------
def load_children_terms(data_dir: Path, subject_id: str) -> List[str]:
    children_file = data_dir / "children" / f"{subject_id}_children.jsonl"
    if not children_file.exists():
        return []

    terms = []
    with children_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    name = data.get("name", "") or data.get("childName", "")
                elif isinstance(data, list) and len(data) >= 2:
                    name = data[1]
                else:
                    continue
                if name and name.strip():
                    terms.append(name.strip())
            except json.JSONDecodeError:
                continue
    return terms


# -------------------- 事件排序 --------------------
def extract_event_date(e: Dict) -> str:
    title = e.get("title", "") or ""
    m = re.search(r"(\d{4}-\d{2}-\d{2})", title)
    if m:
        return m.group(1)
    return e.get("created_at", "") or ""


def get_sorted_events(events: List[Dict]) -> List[Dict]:
    if not events:
        return []
    return sorted(events, key=extract_event_date, reverse=True)


# -------------------- 主流程 --------------------
def process_subject(
    ds: DeepSeekClient,
    data_dir: Path,
    subject_id: str,
    out_dir: Path,
    force_rebuild: bool = False
) -> Dict:

    print(f"\n=== 处理题材 {subject_id} ===")

    cache_dir = data_dir / "gate_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        subj = find_subject_detail_record(data_dir, subject_id)
    except FileNotFoundError as e:
        print(f"  [FAIL] {e}")
        return {
            "ok": False,
            "reason": "SUBJECT_NOT_FOUND",
            "subject_id": subject_id
        }

    subject_name = subj.name
    print(f"  题材名称: {subject_name}")
    print(f"  原始 source_type: {subj.source_type}")

    # ------------------------------------------------
    # Step1: 预处理
    # ------------------------------------------------
    if not ensure_preprocessed(data_dir, subject_id, force_rebuild):
        return {
            "ok": False,
            "reason": "PREPROCESS_FAILED_OR_NO_SOURCES",
            "subject_id": subject_id
        }

    # ------------------------------------------------
    # Step2: 检查知识源
    # ------------------------------------------------
    has_knowledge, knowledge_count, has_core, has_related, has_children = has_knowledge_sources(data_dir, subject_id)

    # strict fallback 检测
    strict_path = data_dir / "knowledge_blocks_strict" / f"{subject_id}_knowledge_strict.jsonl"
    has_strict = strict_path.exists() and strict_path.stat().st_size > 0

    if not has_knowledge and has_strict:
        print("  [fallback] 使用 strict_knowledge 作为知识源")
        has_knowledge = True
        has_core = True
        knowledge_count = 1

    if not has_knowledge:
        print("  [FAIL] 缺乏知识源（无 children 且无 core/related/strict），无法生成正式 gate")
        return {
            "ok": False,
            "reason": "INSUFFICIENT_KNOWLEDGE",
            "subject_id": subject_id
        }

    # ------------------------------------------------
    # Step3: 质量等级
    # ------------------------------------------------
    if has_core and has_related:
        quality = "strong"
    elif has_core or has_related:
        quality = "medium"
    else:
        quality = "weak"

    print(f"  知识源计数: {knowledge_count}, 质量等级: {quality} (core={has_core}, related={has_related})")

    # ------------------------------------------------
    # Step4: 读取知识块
    # ------------------------------------------------
    core_blocks = read_jsonl(data_dir / "knowledge_core" / f"{subject_id}_knowledge_core.jsonl")
    related_blocks = read_jsonl(data_dir / "knowledge_related" / f"{subject_id}_knowledge_related.jsonl")
    signal_blocks = read_jsonl(data_dir / "knowledge_signal" / f"{subject_id}_knowledge_signal.jsonl")
    strict_blocks = read_jsonl(data_dir / "knowledge_blocks_strict" / f"{subject_id}_knowledge_strict.jsonl")

    events = read_jsonl(data_dir / "event_feed" / f"{subject_id}_events.jsonl")
    children_terms = load_children_terms(data_dir, subject_id)

    # strict fallback
    if not core_blocks and not related_blocks and strict_blocks:
        core_blocks = strict_blocks
        print(f"  [fallback] strict_knowledge → core_blocks ({len(core_blocks)}条)")

    print(
        f"  加载: core={len(core_blocks)}条, related={len(related_blocks)}条, "
        f"signal={len(signal_blocks)}条, events={len(events)}条, children={len(children_terms)}条"
    )

    # ------------------------------------------------
    # Step5: 知识文本抽样
    # ------------------------------------------------
    all_blocks = read_jsonl(data_dir / "knowledge_all" / f"{subject_id}_knowledge_all.jsonl")

    knowledge_texts = sample_knowledge_texts(
        core_blocks,
        related_blocks,
        signal_blocks,
        all_blocks,
        max_total=12
    )

    # ------------------------------------------------
    # Step6: 事件处理
    # ------------------------------------------------
    sorted_events = get_sorted_events(events)
    recent_events = sorted_events[:5]

    event_summary = "\n".join([
        e.get("title", e.get("text", ""))
        for e in recent_events
    ])

    event_phrases = extract_event_phrases(
        ds=ds,
        events=events,
        subject_id=subject_id,
        max_events=5,
    )

    # ------------------------------------------------
    # Step7: ontology
    # ------------------------------------------------
    ontology = generate_ontology(
        ds=ds,
        knowledge_texts=knowledge_texts,
        children_terms=children_terms,
        subject_id=subject_id,
        cache_dir=cache_dir,
        force_refresh=force_rebuild
    )

    semantic_type = ontology.get("semantic_type", ontology.get("type", "未知"))

    strategy_type = ontology.get("strategy_type", "industry_chain")

    if strategy_type not in STRATEGY_CONFIG:
        strategy_type = "industry_chain"
        ontology["strategy_type"] = strategy_type

    print(f"  semantic_type: {semantic_type}")
    print(f"  strategy_type: {strategy_type} ({get_strategy_label(strategy_type)})")

    # ------------------------------------------------
    # Step8: 知识词抽取
    # ------------------------------------------------
    knowledge_terms = extract_knowledge_terms(
        ds=ds,
        subject_name=subject_name,
        knowledge_texts=knowledge_texts,
        subject_id=subject_id,
    )

    judged_terms = judge_gate_terms(
        ds=ds,
        ontology=ontology,
        knowledge_texts=knowledge_texts,
        children_terms=children_terms,
        event_summary=event_summary,
        event_phrases=event_phrases,
        knowledge_terms=knowledge_terms,
        subject_id=subject_id,
    )

    # ------------------------------------------------
    # Step9: anchor
    # ------------------------------------------------
    anchor_terms = [x["term"] for x in judged_terms.get("anchor_term", [])]

    anchor_levels = judge_gate_core_anchors(
        ds=ds,
        subject_name=subject_name,
        ontology=ontology,
        knowledge_texts=knowledge_texts,
        anchor_terms=anchor_terms,
        subject_id=subject_id,
        cache_dir=cache_dir,
        force_refresh=force_rebuild,
    )

    # ------------------------------------------------
    # Step10: gate生成
    # ------------------------------------------------
    gate = generate_gate_from_ontology(
        ds=ds,
        ontology=ontology,
        judged_terms=judged_terms,
        anchor_levels=anchor_levels,
        event_summary=event_summary,
        subject_id=subject_id,
    )

    gate = soft_repair(
        ds=ds,
        subject_name=subject_name,
        gate=gate,
        anchor_levels=anchor_levels,
        ontology=ontology,
        subject_id=subject_id,
        cache_dir=cache_dir,
        force_refresh=force_rebuild,
    )

    ok, problems = hard_fail(
        gate=gate,
        anchor_levels=anchor_levels,
        ontology=ontology,
    )

    if not ok:
        return {
            "ok": False,
            "reason": "HARD_FAIL:" + "|".join(problems),
            "subject_id": subject_id,
            "quality": quality,
            "semantic_type": semantic_type,
            "strategy_type": strategy_type,
        }

    # ------------------------------------------------
    # Step11: 保存
    # ------------------------------------------------
    gate["subject_id"] = subject_id
    gate["quality"] = quality
    gate["generated_at"] = now_iso()
    gate["semantic_type"] = semantic_type
    gate["strategy_type"] = strategy_type
    gate["source_type"] = subj.source_type

    out_dir.mkdir(parents=True, exist_ok=True)

    out_path = out_dir / f"{subject_id}_gate.json"

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(gate, f, ensure_ascii=False, indent=2)

    print(f"[OK] 已生成 {out_path} (quality={quality}, strategy_type={strategy_type})")

    return {
        "ok": True,
        "reason": "OK",
        "subject_id": subject_id,
        "quality": quality,
        "semantic_type": semantic_type,
        "strategy_type": strategy_type,
    }

# -------------------- main --------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", type=str, help="单题材ID（调试用）")
    ap.add_argument("--list-file", type=str, help="题材列表文件路径 (full_theme_list.jsonl)")
    ap.add_argument("--data-dir", default="theme_data_complete", help="数据目录")
    ap.add_argument("--out-dir", default="subject_gates", help="输出目录")
    ap.add_argument("--deepseek-api-key", default="", help="API Key")
    ap.add_argument("--limit", type=int, default=0, help="限制处理数量（仅与 --list-file 一起使用）")
    ap.add_argument("--force-rebuild", action="store_true", help="强制重新生成预处理文件，并忽略门禁缓存和断点")
    args = ap.parse_args()

    if not args.subject and not args.list_file:
        raise SystemExit("请指定 --subject 或 --list-file")

    api_key = args.deepseek_api_key.strip() or os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("请提供 DeepSeek API Key")

    data_dir = Path(args.data_dir)
    out_dir = Path(args.out_dir)
    processed_dir = out_dir / ".processed"
    processed_dir.mkdir(parents=True, exist_ok=True)

    ds = DeepSeekClient(api_key=api_key)

    if args.subject:
        result = process_subject(ds, data_dir, args.subject, out_dir, args.force_rebuild)
        print("\n==== RESULT ====")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    list_path = Path(args.list_file)
    if not list_path.exists():
        raise SystemExit(f"题材列表文件不存在: {list_path}")

    subject_ids = []
    with list_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                sid = obj.get("subjectId") or obj.get("subject_id") or obj.get("bizKey")
                if sid:
                    subject_ids.append(str(sid))
            except json.JSONDecodeError:
                continue

    if args.limit > 0:
        subject_ids = subject_ids[:args.limit]

    print(f"题材总数: {len(subject_ids)}")

    stats = {"total": len(subject_ids), "ok": 0, "fail": 0, "skipped": 0, "fails": {}}

    for sid in tqdm(subject_ids, desc="处理题材"):
        processed_flag = processed_dir / f"{sid}.processed"
        if not args.force_rebuild and processed_flag.exists():
            stats["skipped"] += 1
            continue

        try:
            r = process_subject(ds, data_dir, sid, out_dir, args.force_rebuild)
            if r["ok"]:
                processed_flag.touch()
                stats["ok"] += 1
            else:
                stats["fail"] += 1
                reason = r["reason"]
                stats["fails"][reason] = stats["fails"].get(reason, 0) + 1
        except Exception as e:
            stats["fail"] += 1
            reason = f"EX:{type(e).__name__}"
            stats["fails"][reason] = stats["fails"].get(reason, 0) + 1
            print(f"\n[ERROR] subject={sid} -> {repr(e)}")
        time.sleep(DEFAULT_SLEEP)

    print("\n==== SUMMARY ====")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()