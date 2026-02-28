from __future__ import annotations

import json
import os
import time
import threading
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from llama_cpp import Llama

from database_service.scripts.phase3_semantic_vs_llm_benchmark import QwenReviewer, _hits_cluster


REPO_ROOT = Path("/Users/admin/Desktop/ai_theme_app")
MISMATCH_IDS_FILE = REPO_ROOT / "tmp/phase3_mismatch_event_ids.txt"
EVENTS_FILE = REPO_ROOT / "evaluate_service/data/raw/ai_processed_events.json"
AB_REPORT_FILE = REPO_ROOT / "tmp/phase3_semantic_vs_llm_mismatch13_ab_clean.json"
OUT_REPORT_FILE = REPO_ROOT / "tmp/phase3_llm_binary_judge_mismatch_report.json"
PRECISION_MATRIX_REPORT_FILE = REPO_ROOT / "tmp/phase3_llm_precision_matrix_report.json"

# GGUF模型路径 - 用于Prompt/Forced-Choice测试
GGUF_MODEL_PATH = REPO_ROOT / "model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"
# 原Transformers模型路径 - 用于精度矩阵测试
TRANSFORMERS_MODEL_PATH = REPO_ROOT / ".qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775"

_REVIEWER_CACHE = None


async def get_cached_reviewer():
    global _REVIEWER_CACHE
    if _REVIEWER_CACHE is None:
        print("🔄 创建新的Reviewer实例...")
        _REVIEWER_CACHE = await QwenReviewer.build()
        print("✅ Reviewer实例创建完成")
    return _REVIEWER_CACHE


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _read_ids(path: Path) -> List[str]:
    if not path.exists():
        return []
    ids: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s:
            ids.append(s)
    return ids


def _event_text(event: Dict[str, Any]) -> str:
    ai = event.get("ai_analysis") or {}
    parts = [
        str(event.get("title") or ""),
        str(event.get("content") or ""),
        str(ai.get("core_concept") or ""),
    ]
    return " ".join(p for p in parts if p).strip()


def _get_prompt_model_path() -> Path | None:
    print(f"\n🔍 检查Prompt/Forced模型路径...")
    print(f"  GGUF模型路径: {GGUF_MODEL_PATH}")
    print(f"  GGUF模型存在: {GGUF_MODEL_PATH.exists()}")
    if GGUF_MODEL_PATH.exists():
        print(f"✅ 找到GGUF模型: {GGUF_MODEL_PATH}")
        return GGUF_MODEL_PATH
    print(f"⚠️ GGUF模型不存在，回退Transformers模型: {TRANSFORMERS_MODEL_PATH}")
    if TRANSFORMERS_MODEL_PATH.exists():
        return TRANSFORMERS_MODEL_PATH
    return None


def _get_transformers_model_path() -> Path | None:
    print(f"\n🔍 检查Transformers模型路径...")
    print(f"  Transformers模型路径: {TRANSFORMERS_MODEL_PATH}")
    print(f"  Transformers模型存在: {TRANSFORMERS_MODEL_PATH.exists()}")
    if TRANSFORMERS_MODEL_PATH.exists():
        print(f"✅ 找到Transformers模型: {TRANSFORMERS_MODEL_PATH}")
        return TRANSFORMERS_MODEL_PATH

    snapshot_root = REPO_ROOT / ".qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots"
    if snapshot_root.exists():
        snaps = sorted(snapshot_root.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
        for s in snaps:
            if (s / "config.json").exists():
                print(f"✅ 找到缓存模型: {s}")
                return s
    return None


def _build_wrong_vs_gt_map(ab_report: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    sem = ab_report.get("semantic_only") or {}
    mappings = sem.get("update_theme_mappings") or []
    gt_rows = sem.get("ground_truth_comparison") or []

    wrong_by_event: Dict[str, str] = {}
    for row in mappings:
        eid = str(row.get("event_id") or "")
        if not eid:
            continue
        wrong_by_event[eid] = str(row.get("matched_theme_name") or "").strip()

    out: Dict[str, Dict[str, str]] = {}
    for row in gt_rows:
        eid = str(row.get("event_id") or "")
        if not eid:
            continue
        if bool(row.get("ground_truth_passed")):
            continue

        gt_themes = row.get("ground_truth_themes") or []
        gt_name = str(gt_themes[0] if gt_themes else row.get("ground_truth_theme_group") or "").strip()
        wrong_name = wrong_by_event.get(eid, "").strip()
        if gt_name and wrong_name:
            out[eid] = {"gt_theme": gt_name, "wrong_theme": wrong_name}
    return out


# =========================
# Prompt Yes/No Judge (严格解析)
# =========================

class LocalQwenYesNoJudge:
    """支持 GGUF / HF 的 yes/no judge（严格只接受 '是' 或 '否'）"""

    _instances = {}
    _lock = threading.Lock()

    def __new__(cls, model_path: Path):
        key = str(model_path)
        with cls._lock:
            if key not in cls._instances:
                inst = super().__new__(cls)
                inst._initialized = False
                cls._instances[key] = inst
            return cls._instances[key]

    def __init__(self, model_path: Path):
        if getattr(self, "_initialized", False):
            return

        self.model_path = str(model_path)
        self.is_gguf = str(model_path).endswith(".gguf")

        print(f"\n📦 加载Prompt模型: {model_path}")
        print(f"📦 模型格式: {'GGUF' if self.is_gguf else 'HuggingFace'}")
        start = time.time()

        if self.is_gguf:
            self.llm = Llama(
                model_path=str(model_path),
                n_ctx=2048,
                n_threads=8,
                n_gpu_layers=-1 if torch.cuda.is_available() else 0,
                verbose=False,
                temperature=0.0,
                top_p=0.95,
                top_k=40,
            )
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.tokenizer = AutoTokenizer.from_pretrained(
                str(model_path),
                trust_remote_code=True,
                use_fast=True,
            )
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token

            kwargs = dict(trust_remote_code=True, low_cpu_mem_usage=True)
            if torch.cuda.is_available():
                kwargs["torch_dtype"] = torch.float16
                self.device = torch.device("cuda")
            else:
                kwargs["torch_dtype"] = torch.float32
                self.device = torch.device("cpu")

            self.model = AutoModelForCausalLM.from_pretrained(str(model_path), **kwargs)
            self.model.to(self.device)
            self.model.eval()

        print(f"✅ Prompt模型加载完成，耗时: {time.time() - start:.2f}s, device={self.device}")
        self._initialized = True

    def _generate_text(self, prompt: str, max_new_tokens: int = 2) -> str:
        if self.is_gguf:
            resp = self.llm(
                prompt,
                max_tokens=max_new_tokens,
                stop=["\n"],
                echo=False,
                temperature=0.0,
            )
            return resp["choices"][0]["text"].strip()
        else:
            inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
            with torch.no_grad():
                outputs = self.model.generate(
                    **inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=self.tokenizer.pad_token_id,
                )
            gen_ids = outputs[0][inputs["input_ids"].shape[1]:]
            return self.tokenizer.decode(gen_ids, skip_special_tokens=True).strip()

    def judge_yes_no(self, event_text: str, theme_name: str, theme_keywords: str = "") -> Dict[str, Any]:
        prompt = f"""你是金融题材严格裁判。判断事件是否属于该题材。
规则：
- 必须同一产业链/技术主线且有直接证据才判是。
- 泛化相关一律判否。
- 拿不准判否。
要求：只输出一个汉字：是 或 否。不要输出其他任何字符。

事件：{event_text[:260]}
题材：{theme_name}
关键词：{theme_keywords}

输出："""
        raw = self._generate_text(prompt, max_new_tokens=2)
        ans = raw.strip()

        if ans == "是":
            return {"is_yes": True, "invalid": False, "raw_output": raw}
        if ans == "否":
            return {"is_yes": False, "invalid": False, "raw_output": raw}
        return {"is_yes": False, "invalid": True, "raw_output": raw}


# =========================
# Forced-Choice Judge (二选一)
# =========================

class ForcedChoiceJudge:
    """强制二选一：只输出 A 或 B（支持随机打乱）"""

    def __init__(self, yesno_judge: LocalQwenYesNoJudge):
        # 复用已加载模型（GGUF/HF），避免重复加载
        self.j = yesno_judge

    def judge_ab(self, event_text: str, theme_a: str, theme_b: str) -> Dict[str, Any]:
        # 随机翻转，防止模型偏 A
        flip = random.random() < 0.5
        if flip:
            A, B = theme_b, theme_a
            correct = "B"  # 原 theme_a 是正确，翻转后落在 B
        else:
            A, B = theme_a, theme_b
            correct = "A"

        prompt = f"""你是金融题材裁判。
下面给出事件与两个候选题材，请选择更匹配的一个。

规则：
- 只能输出一个字母：A 或 B
- 不要解释，不要输出其他字符

事件：{event_text[:280]}

A. {A}
B. {B}

输出："""

        # 这里用同一个底层 generate（GGUF/HF），只让它生成 1 token
        raw = self.j._generate_text(prompt, max_new_tokens=1).strip()

        if raw == "A":
            choice = "A"
            invalid = False
        elif raw == "B":
            choice = "B"
            invalid = False
        else:
            choice = None
            invalid = True

        return {
            "choice": choice,
            "invalid": invalid,
            "raw_output": raw,
            "flip": flip,
            "correct_choice": correct,
            "is_correct": (choice == correct) if not invalid else False,
            "A": A,
            "B": B,
        }


# =========================
# Theme index helpers
# =========================

def _build_theme_name_index(reviewer: QwenReviewer) -> Dict[str, List[Dict[str, Any]]]:
    idx: Dict[str, List[Dict[str, Any]]] = {}
    seen = set()
    for container in [reviewer.theme_by_code or {}, reviewer.theme_by_id or {}]:
        for obj in container.values():
            if not isinstance(obj, dict):
                continue
            key = (str(obj.get("id") or ""), str(obj.get("code") or ""), str(obj.get("name") or ""))
            if key in seen:
                continue
            seen.add(key)
            name = str(obj.get("name") or "").strip().lower()
            if not name:
                continue
            idx.setdefault(name, []).append(obj)
    return idx


def _resolve_theme_context(theme_name: str, idx: Dict[str, List[Dict[str, Any]]]) -> Dict[str, Any]:
    target = str(theme_name or "").strip()
    if not target:
        return {"name": "", "keywords": []}
    key = target.lower()
    if key in idx and idx[key]:
        return idx[key][0]
    # fallback：只做 containment 查找用于拿 keywords（不用于判定等价）
    for name, objs in idx.items():
        if key in name or name in key:
            return objs[0]
    return {"name": target, "keywords": [target]}


# =========================
# name_match (精度矩阵用) —— 收紧，禁止 substring
# =========================

def _name_match(a: str, b: str) -> bool:
    aa = str(a or "").strip()
    bb = str(b or "").strip()
    if not aa or not bb:
        return False
    if aa == bb:
        return True
    return _hits_cluster(aa, bb)


# =========================
# TEST 1: Binary + Forced-Choice
# =========================

@pytest.mark.asyncio
async def test_phase3_llm_binary_yes_no_on_mismatch_events():
    print("\n" + "=" * 60)
    print("🧪 Test1: LLM Binary + Forced-Choice on mismatch events")
    print("=" * 60)

    if not EVENTS_FILE.exists():
        pytest.skip(f"events dataset not found: {EVENTS_FILE}")
    if not AB_REPORT_FILE.exists():
        pytest.skip(f"ab report not found: {AB_REPORT_FILE}")

    mismatch_ids = set(_read_ids(MISMATCH_IDS_FILE))
    ab_report = _load_json(AB_REPORT_FILE)
    wrong_gt_map = _build_wrong_vs_gt_map(ab_report)
    target_ids = [eid for eid in wrong_gt_map.keys() if not mismatch_ids or eid in mismatch_ids]
    if not target_ids:
        pytest.skip("no mismatched events found")

    data = _load_json(EVENTS_FILE)
    events = data if isinstance(data, list) else data.get("events", [])
    event_by_id = {str(e.get("event_id") or ""): e for e in events if isinstance(e, dict)}

    prompt_model_path = _get_prompt_model_path()
    if prompt_model_path is None:
        pytest.fail("No model found for prompt judge")
    os.environ["PHASE3_LOCAL_QWEN_MODEL_PATH"] = str(prompt_model_path)

    reviewer = await get_cached_reviewer()
    if not reviewer.enabled:
        pytest.skip("QwenReviewer is disabled")

    theme_name_index = _build_theme_name_index(reviewer)

    enable_prompt_judge = os.getenv("PHASE3_ENABLE_PROMPT_JUDGE", "0").strip() == "1"
    prompt_judge: Optional[LocalQwenYesNoJudge] = None
    forced_judge: Optional[ForcedChoiceJudge] = None
    prompt_unavailable_reason = ""

    if enable_prompt_judge:
        try:
            prompt_judge = LocalQwenYesNoJudge(prompt_model_path)
            forced_judge = ForcedChoiceJudge(prompt_judge)
        except Exception as exc:
            prompt_unavailable_reason = str(exc)
            prompt_judge = None
            forced_judge = None
    else:
        prompt_unavailable_reason = "disabled_by_env"

    rows: List[Dict[str, Any]] = []

    # embedding metrics（仅记录，不建议作为 gate）
    emb_gt_yes = emb_wrong_no = emb_pair_pass = 0

    # prompt yes/no metrics（严格解析 + invalid 统计）
    prm_gt_yes = prm_wrong_no = prm_pair_pass = 0
    prm_invalid_rows = 0

    # forced-choice metrics（核心）
    fc_total = fc_correct = fc_invalid = 0

    for idx, eid in enumerate(target_ids, 1):
        event = event_by_id.get(eid)
        if not event:
            continue

        pair = wrong_gt_map[eid]
        gt_theme = pair["gt_theme"]
        wrong_theme = pair["wrong_theme"]

        event_text = _event_text(event)
        if not event_text:
            continue

        # --- Embedding binary judge (原逻辑保留) ---
        candidates = [gt_theme, wrong_theme, "核聚变", "卫星制造"]
        uniq_candidates = list(dict.fromkeys([c for c in candidates if c]))
        judge_map = reviewer._judge_event_themes_binary(event_text, uniq_candidates)
        emb_gt_is_yes = bool(judge_map.get(gt_theme, False))
        emb_wrong_is_no = not bool(judge_map.get(wrong_theme, False))
        if emb_gt_is_yes:
            emb_gt_yes += 1
        if emb_wrong_is_no:
            emb_wrong_no += 1
        if emb_gt_is_yes and emb_wrong_is_no:
            emb_pair_pass += 1

        # --- Prompt yes/no + Forced choice ---
        prm_gt_is_yes = False
        prm_wrong_is_no = False
        prm_pair_pass_flag = False
        prm_invalid = False
        prm_raw = {}

        fc_res = None

        if prompt_judge is not None:
            gt_ctx = _resolve_theme_context(gt_theme, theme_name_index)
            wrong_ctx = _resolve_theme_context(wrong_theme, theme_name_index)

            gt_kws = ", ".join([str(x).strip() for x in (gt_ctx.get("keywords") or []) if str(x).strip()][:5])
            wrong_kws = ", ".join([str(x).strip() for x in (wrong_ctx.get("keywords") or []) if str(x).strip()][:5])

            gt_res = prompt_judge.judge_yes_no(event_text, gt_theme, gt_kws)
            wrong_res = prompt_judge.judge_yes_no(event_text, wrong_theme, wrong_kws)

            prm_invalid = bool(gt_res["invalid"] or wrong_res["invalid"])
            if prm_invalid:
                prm_invalid_rows += 1

            gt_yes = bool(gt_res["is_yes"])
            wrong_yes = bool(wrong_res["is_yes"])

            prm_gt_is_yes = gt_yes
            prm_wrong_is_no = (not wrong_yes)
            prm_pair_pass_flag = gt_yes and (not wrong_yes)

            if prm_gt_is_yes:
                prm_gt_yes += 1
            if prm_wrong_is_no:
                prm_wrong_no += 1
            if prm_pair_pass_flag:
                prm_pair_pass += 1

            prm_raw = {
                "gt_raw": gt_res.get("raw_output", ""),
                "wrong_raw": wrong_res.get("raw_output", ""),
                "invalid": prm_invalid,
            }

            # Forced-choice（核心评估）
            if forced_judge is not None:
                fc_res = forced_judge.judge_ab(event_text, gt_theme, wrong_theme)
                fc_total += 1
                if fc_res["invalid"]:
                    fc_invalid += 1
                elif fc_res["is_correct"]:
                    fc_correct += 1

        rows.append(
            {
                "index": idx,
                "event_id": eid,
                "event_title": str(event.get("title") or ""),
                "gt_theme": gt_theme,
                "wrong_theme": wrong_theme,
                "embedding_judge_map": judge_map,
                "embedding_pair_pass": bool(emb_gt_is_yes and emb_wrong_is_no),

                "prompt_enabled": enable_prompt_judge,
                "prompt_gt_is_yes": prm_gt_is_yes,
                "prompt_wrong_is_no": prm_wrong_is_no,
                "prompt_pair_pass": prm_pair_pass_flag,
                "prompt_raw_output": json.dumps(prm_raw, ensure_ascii=False),

                "forced_choice": fc_res,  # 直接记录详细信息便于 debug
            }
        )

    total = len(rows)
    assert total > 0, "no valid mismatch rows processed"

    report = {
        "prompt_model_path": str(prompt_model_path),
        "total_rows": total,
        "embedding_metrics": {
            "gt_yes_count": emb_gt_yes,
            "wrong_no_count": emb_wrong_no,
            "pair_pass_count": emb_pair_pass,
            "gt_yes_rate": round(emb_gt_yes / total, 4),
            "wrong_no_rate": round(emb_wrong_no / total, 4),
            "pairwise_accuracy": round(emb_pair_pass / total, 4),
        },
        "prompt_metrics": {
            "enabled_by_env": enable_prompt_judge,
            "available": prompt_judge is not None,
            "unavailable_reason": prompt_unavailable_reason,
            "gt_yes_count": prm_gt_yes,
            "wrong_no_count": prm_wrong_no,
            "pair_pass_count": prm_pair_pass,
            "invalid_rows": prm_invalid_rows,
            "gt_yes_rate": round(prm_gt_yes / total, 4) if prompt_judge is not None else None,
            "wrong_no_rate": round(prm_wrong_no / total, 4) if prompt_judge is not None else None,
            "pairwise_accuracy": round(prm_pair_pass / total, 4) if prompt_judge is not None else None,
            "invalid_rate": round(prm_invalid_rows / total, 4) if prompt_judge is not None else None,
        },
        "forced_choice_metrics": {
            "available": forced_judge is not None,
            "total": fc_total,
            "correct": fc_correct,
            "invalid": fc_invalid,
            "accuracy": round(fc_correct / fc_total, 4) if fc_total else None,
            "invalid_rate": round(fc_invalid / fc_total, 4) if fc_total else None,
        },
        "rows": rows,
    }

    OUT_REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 报告已保存: {OUT_REPORT_FILE}")

    # 可选门禁：强制二选一 accuracy（默认不 gate）
    min_fc_acc = float(os.getenv("PHASE3_FORCED_CHOICE_MIN_ACC", "0.0"))
    if forced_judge is not None and fc_total:
        assert report["forced_choice_metrics"]["accuracy"] >= min_fc_acc


# =========================
# TEST 2: Precision Matrix（保持，但 name_match 收紧）
# =========================

@pytest.mark.asyncio
async def test_phase3_local_qwen_precision_matrix_on_mismatch_events():
    print("\n" + "=" * 60)
    print("🧪 Test2: Precision Matrix (Transformers model)")
    print("=" * 60)

    if not EVENTS_FILE.exists() or not AB_REPORT_FILE.exists():
        pytest.skip("required dataset/report missing")

    mismatch_ids = set(_read_ids(MISMATCH_IDS_FILE))
    ab_report = _load_json(AB_REPORT_FILE)
    wrong_gt_map = _build_wrong_vs_gt_map(ab_report)
    target_ids = [eid for eid in wrong_gt_map.keys() if not mismatch_ids or eid in mismatch_ids]
    if not target_ids:
        pytest.skip("no mismatched events found")

    data = _load_json(EVENTS_FILE)
    events = data if isinstance(data, list) else data.get("events", [])
    event_by_id = {str(e.get("event_id") or ""): e for e in events if isinstance(e, dict)}

    transformers_model_path = _get_transformers_model_path()
    if transformers_model_path is None:
        pytest.fail("No Transformers model found for precision matrix test")

    os.environ["PHASE3_LOCAL_QWEN_MODEL_PATH"] = str(transformers_model_path)

    reviewer = await get_cached_reviewer()
    if not reviewer.enabled:
        pytest.skip("QwenReviewer unavailable")

    from theme_service.matchers.local_qwen_matcher import create_medium_qwen_matcher, create_tiny_qwen_matcher

    factories = {
        "tiny": create_tiny_qwen_matcher,
        "medium": create_medium_qwen_matcher,
    }
    precisions = ["low", "normal", "high"]

    matrix: Dict[str, Dict[str, Any]] = {}
    details: List[Dict[str, Any]] = []

    for f_name, factory in factories.items():
        cfg = {"use_cache": True, "model_name": str(transformers_model_path), "match_threshold": 0.3, "max_results": 20}
        matcher = factory(cfg)

        theme_dicts = list({id(v): v for v in (reviewer.theme_by_code or {}).values()}.values())
        matcher.initialize(theme_dicts)

        for precision in precisions:
            total = gt_recall = wrong_suppression = pair_pass = 0

            for eid in target_ids:
                event = event_by_id.get(eid)
                if not event:
                    continue
                pair = wrong_gt_map[eid]
                gt_name = pair["gt_theme"]
                wrong_name = pair["wrong_theme"]

                res = matcher.match(event, precision=precision)
                ranked = [str(r.theme_name or "").strip() for r in res]

                gt_rank = next((i for i, n in enumerate(ranked) if _name_match(gt_name, n)), None)
                wrong_rank = next((i for i, n in enumerate(ranked) if _name_match(wrong_name, n)), None)

                total += 1
                gt_hit = gt_rank is not None
                # 这里仍是“相对排序”口径；如果你要线上口径，应改为 hit@k
                wrong_supp = wrong_rank is None or (gt_rank is not None and gt_rank < wrong_rank)
                passed = gt_hit and wrong_supp

                if gt_hit:
                    gt_recall += 1
                if wrong_supp:
                    wrong_suppression += 1
                if passed:
                    pair_pass += 1

                details.append(
                    {
                        "factory": f_name,
                        "precision": precision,
                        "event_id": eid,
                        "gt_theme": gt_name,
                        "wrong_theme": wrong_name,
                        "gt_rank": gt_rank,
                        "wrong_rank": wrong_rank,
                        "top5": ranked[:5],
                        "pass": passed,
                    }
                )

            key = f"{f_name}:{precision}"
            matrix[key] = {
                "total": total,
                "gt_recall": round(gt_recall / total, 4) if total else 0.0,
                "wrong_suppression": round(wrong_suppression / total, 4) if total else 0.0,
                "pairwise_accuracy": round(pair_pass / total, 4) if total else 0.0,
            }

    report = {"transformers_model_path": str(transformers_model_path), "matrix": matrix, "details": details}
    PRECISION_MATRIX_REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 精度矩阵报告已保存: {PRECISION_MATRIX_REPORT_FILE}")

    assert matrix, "precision matrix report is empty"