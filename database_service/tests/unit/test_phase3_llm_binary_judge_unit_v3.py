"""Phase3 LLM-only binary judge unit test on known mismatch events."""

from __future__ import annotations

import json
import os
import time
import threading
from pathlib import Path
from typing import Any, Dict, List

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

# GGUF模型路径 - 用于Prompt测试
GGUF_MODEL_PATH = REPO_ROOT / "model_service/models/qwen2.5/qwen2.5-1.5b-instruct-q5_k_m.gguf"
# 原Transformers模型路径 - 用于精度矩阵测试
TRANSFORMERS_MODEL_PATH = REPO_ROOT / ".qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots/7ae557604adf67be50417f59c2c2f167def9a775"

# 全局缓存 reviewer 实例，避免重复创建数据库连接
_REVIEWER_CACHE = None

async def get_cached_reviewer():
    """获取缓存的reviewer实例，只创建一次数据库连接"""
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
    """获取用于Prompt测试的GGUF模型路径"""
    print(f"\n🔍 检查Prompt模型路径...")
    print(f"  GGUF模型路径: {GGUF_MODEL_PATH}")
    print(f"  GGUF模型存在: {GGUF_MODEL_PATH.exists()}")
    
    if GGUF_MODEL_PATH.exists():
        print(f"✅ 找到GGUF模型: {GGUF_MODEL_PATH}")
        return GGUF_MODEL_PATH
    
    # 如果没有GGUF模型，回退到Transformers模型
    print(f"⚠️ GGUF模型不存在，使用Transformers模型: {TRANSFORMERS_MODEL_PATH}")
    if TRANSFORMERS_MODEL_PATH.exists():
        return TRANSFORMERS_MODEL_PATH
    
    return None


def _get_transformers_model_path() -> Path | None:
    """获取用于精度矩阵测试的Transformers模型路径"""
    print(f"\n🔍 检查Transformers模型路径...")
    print(f"  Transformers模型路径: {TRANSFORMERS_MODEL_PATH}")
    print(f"  Transformers模型存在: {TRANSFORMERS_MODEL_PATH.exists()}")
    
    if TRANSFORMERS_MODEL_PATH.exists():
        print(f"✅ 找到Transformers模型: {TRANSFORMERS_MODEL_PATH}")
        return TRANSFORMERS_MODEL_PATH
    
    # 检查缓存目录
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
        gt_passed = bool(row.get("ground_truth_passed"))
        if gt_passed:
            continue
        gt_themes = row.get("ground_truth_themes") or []
        gt_name = str(gt_themes[0] if gt_themes else row.get("ground_truth_theme_group") or "").strip()
        wrong_name = wrong_by_event.get(eid, "").strip()
        if gt_name and wrong_name:
            out[eid] = {"gt_theme": gt_name, "wrong_theme": wrong_name}
    return out


class LocalQwenYesNoJudge:
    """支持多种格式的Qwen模型判断器 - 用于Prompt测试"""
    
    _instances = {}  # 类级别缓存，避免重复加载
    _lock = threading.Lock()

    def __new__(cls, model_path: Path):
        """单例模式，确保相同模型路径只加载一次"""
        key = str(model_path)
        with cls._lock:
            if key not in cls._instances:
                instance = super().__new__(cls)
                instance._initialized = False
                cls._instances[key] = instance
            return cls._instances[key]

    def __init__(self, model_path: Path):
        if getattr(self, '_initialized', False):
            return
            
        self.model_path = str(model_path)
        self.is_gguf = str(model_path).endswith('.gguf')
        
        print(f"\n📦 加载Prompt模型: {model_path}")
        print(f"📦 模型格式: {'GGUF' if self.is_gguf else 'HuggingFace'}")
        start_time = time.time()
        
        if self.is_gguf:
            self._init_gguf_model(model_path)
        else:
            self._init_hf_model(model_path)
        
        load_time = time.time() - start_time
        print(f"✅ Prompt模型加载完成，耗时: {load_time:.2f}秒")
        self._initialized = True
    
    def _init_gguf_model(self, model_path: Path):
        """初始化GGUF模型"""
        try:
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
            print(f"  🖥️  使用设备: {self.device}")
        except Exception as e:
            print(f"❌ GGUF模型加载失败: {e}")
            raise
    
    def _init_hf_model(self, model_path: Path):
        """初始化HuggingFace模型"""
        self.tokenizer = AutoTokenizer.from_pretrained(
            str(model_path), 
            trust_remote_code=True,
            use_fast=True
        )
        
        if self.tokenizer.pad_token is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        
        model_kwargs = {
            "trust_remote_code": True,
            "low_cpu_mem_usage": True,
        }
        
        if torch.cuda.is_available():
            model_kwargs["torch_dtype"] = torch.float16
            self.device = torch.device("cuda")
        else:
            model_kwargs["torch_dtype"] = torch.float32
            self.device = torch.device("cpu")
        
        self.model = AutoModelForCausalLM.from_pretrained(
            str(model_path),
            **model_kwargs
        )
        self.model.to(self.device)
        self.model.eval()
        
        if self.device.type == "cuda":
            self.model = self.model.half()
            torch.cuda.empty_cache()
        
        print(f"  🖥️  使用设备: {self.device}")

    def _generate_text(self, prompt: str, max_new_tokens: int = 8) -> str:
        """生成文本"""
        if self.is_gguf:
            response = self.llm(
                prompt,
                max_tokens=max_new_tokens,
                stop=["\n", "。"],
                echo=False,
                temperature=0.0,
            )
            return response["choices"][0]["text"].strip()
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

    def judge_single_theme(self, event_text: str, theme: Dict[str, Any]) -> Dict[str, Any]:
        """判断单个题材"""
        name = str(theme.get("name") or "").strip()
        kws = ", ".join([str(x).strip() for x in (theme.get("keywords") or []) if str(x).strip()][:5])
        
        prompt = f"""判断事件是否属于该题材。只输出"是"或"否"。

事件：{event_text[:200]}
题材：{name}
关键词：{kws}

输出："""
        
        text = self._generate_text(prompt, max_new_tokens=8)
        text = text.strip()
        
        if "是" in text and "否" not in text:
            decision = True
        else:
            decision = False
            
        return {"is_yes": decision, "raw_output": text}


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
        return {"name": "", "description": "", "level1_category": "", "level2_category": "", "keywords": []}
    key = target.lower()
    if key in idx and idx[key]:
        return idx[key][0]

    for name, objs in idx.items():
        if key in name or name in key:
            return objs[0]
    return {"name": target, "description": "", "level1_category": "", "level2_category": "", "keywords": [target]}


def _name_match(a: str, b: str) -> bool:
    aa = str(a or "").strip()
    bb = str(b or "").strip()
    if not aa or not bb:
        return False
    if aa in bb or bb in aa:
        return True
    return _hits_cluster(aa, bb)


def _fuse_two_step_decision(
    reviewer: QwenReviewer,
    event_data: Dict[str, Any],
    gt_theme_ctx: Dict[str, Any],
    wrong_theme_ctx: Dict[str, Any],
    gt_yes: bool,
    wrong_yes: bool,
) -> tuple[str, Dict[str, Any]]:
    event_terms = reviewer._event_terms(event_data)
    gt_terms = reviewer._theme_terms(gt_theme_ctx)
    wrong_terms = reviewer._theme_terms(wrong_theme_ctx)
    gt_overlap = reviewer._has_term_overlap(event_terms, gt_terms)
    wrong_overlap = reviewer._has_term_overlap(event_terms, wrong_terms)

    if gt_yes and not wrong_yes:
        base = "A"
    elif wrong_yes and not gt_yes:
        base = "B"
    elif not gt_yes and not wrong_yes:
        base = "NONE"
    else:
        base = "BOTH"

    choice = base
    if base == "B":
        if not wrong_overlap:
            choice = "NONE"
    elif base == "NONE":
        if gt_overlap and not wrong_overlap:
            choice = "A"
    elif base == "BOTH":
        if gt_overlap and not wrong_overlap:
            choice = "A"
        elif wrong_overlap and not gt_overlap:
            choice = "B"
        else:
            choice = "NONE"

    return choice, {
        "base_choice": base,
        "gt_overlap": gt_overlap,
        "wrong_overlap": wrong_overlap,
    }


@pytest.mark.asyncio
async def test_phase3_llm_binary_yes_no_on_mismatch_events():
    """LLM-only binary judge on mismatch events"""
    print("\n" + "="*60)
    print("🧪 开始测试1: LLM二元判断")
    print("="*60)
    
    env_value = os.getenv("PHASE3_ENABLE_PROMPT_JUDGE", "未设置")
    print(f"📊 PHASE3_ENABLE_PROMPT_JUDGE = '{env_value}'")
    
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

    print(f"✅ 找到 {len(target_ids)} 个目标事件")

    data = _load_json(EVENTS_FILE)
    events = data if isinstance(data, list) else data.get("events", [])
    event_by_id = {str(e.get("event_id") or ""): e for e in events if isinstance(e, dict)}

    # 获取Prompt模型路径（优先使用GGUF）
    prompt_model_path = _get_prompt_model_path()
    if prompt_model_path is None:
        pytest.fail("No model found for prompt judge")
    
    os.environ["PHASE3_LOCAL_QWEN_MODEL_PATH"] = str(prompt_model_path)

    reviewer = await get_cached_reviewer()
    
    if not reviewer.enabled:
        pytest.skip("QwenReviewer is disabled")
    
    theme_name_index = _build_theme_name_index(reviewer)
    
    prompt_judge = None
    prompt_unavailable_reason = ""
    enable_prompt_judge = os.getenv("PHASE3_ENABLE_PROMPT_JUDGE", "0").strip() == "1"
    
    if enable_prompt_judge:
        print("🚀 初始化Prompt模型...")
        try:
            prompt_judge = LocalQwenYesNoJudge(prompt_model_path)
            print("✅ Prompt模型初始化成功")
        except Exception as exc:
            prompt_unavailable_reason = str(exc)
            print(f"❌ Prompt模型加载失败: {exc}")
    else:
        prompt_unavailable_reason = "disabled"

    rows = []
    emb_gt_yes = 0
    emb_wrong_no = 0
    prm_gt_yes = 0
    prm_wrong_no = 0

    for idx, eid in enumerate(target_ids, 1):
        event = event_by_id.get(eid)
        if not event:
            continue
        pair = wrong_gt_map[eid]
        gt_theme = pair["gt_theme"]
        wrong_theme = pair["wrong_theme"]
        
        candidates = [gt_theme, wrong_theme, "核聚变", "卫星制造"]
        uniq_candidates = list(dict.fromkeys([c for c in candidates if c]))
        if len(uniq_candidates) < 2:
            continue

        event_text = _event_text(event)
        if not event_text:
            continue

        judge_map = reviewer._judge_event_themes_binary(event_text, uniq_candidates)
        emb_gt_is_yes = bool(judge_map.get(gt_theme, False))
        emb_wrong_is_no = not bool(judge_map.get(wrong_theme, False))
        
        if emb_gt_is_yes:
            emb_gt_yes += 1
        if emb_wrong_is_no:
            emb_wrong_no += 1

        prm_gt_is_yes = False
        prm_wrong_is_no = False
        prompt_raw = ""
        prompt_choice = ""
        
        if prompt_judge is not None:
            gt_theme_ctx = _resolve_theme_context(gt_theme, theme_name_index)
            wrong_theme_ctx = _resolve_theme_context(wrong_theme, theme_name_index)
            
            gt_res = prompt_judge.judge_single_theme(event_text, gt_theme_ctx)
            wrong_res = prompt_judge.judge_single_theme(event_text, wrong_theme_ctx)
            
            gt_yes = bool(gt_res.get("is_yes"))
            wrong_yes = bool(wrong_res.get("is_yes"))
            
            prompt_choice, fusion_meta = _fuse_two_step_decision(
                reviewer=reviewer,
                event_data=event,
                gt_theme_ctx=gt_theme_ctx,
                wrong_theme_ctx=wrong_theme_ctx,
                gt_yes=gt_yes,
                wrong_yes=wrong_yes,
            )
            
            prompt_raw = json.dumps(
                {
                    "gt_raw": gt_res.get("raw_output", ""),
                    "wrong_raw": wrong_res.get("raw_output", ""),
                    "fusion_meta": fusion_meta,
                },
                ensure_ascii=False,
            )
            prm_gt_is_yes = gt_yes
            prm_wrong_is_no = not wrong_yes
            if prm_gt_is_yes:
                prm_gt_yes += 1
            if prm_wrong_is_no:
                prm_wrong_no += 1

        rows.append(
            {
                "index": idx,
                "event_id": eid,
                "event_title": str(event.get("title") or ""),
                "gt_theme": gt_theme,
                "wrong_theme": wrong_theme,
                "embedding_judge_map": judge_map,
                "embedding_gt_is_yes": emb_gt_is_yes,
                "embedding_wrong_is_no": emb_wrong_is_no,
                "embedding_pair_pass": bool(emb_gt_is_yes and emb_wrong_is_no),
                "prompt_gt_is_yes": prm_gt_is_yes,
                "prompt_wrong_is_no": prm_wrong_is_no,
                "prompt_pair_pass": bool(prm_gt_is_yes and prm_wrong_is_no),
                "prompt_choice": prompt_choice,
                "prompt_raw_output": prompt_raw,
            }
        )

    total = len(rows)
    assert total > 0, "no valid mismatch rows processed"

    emb_pair_pass = sum(1 for r in rows if r["embedding_pair_pass"])
    prm_pair_pass = sum(1 for r in rows if r["prompt_pair_pass"])
    
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
            "gt_yes_rate": round(prm_gt_yes / total, 4) if prompt_judge is not None else None,
            "wrong_no_rate": round(prm_wrong_no / total, 4) if prompt_judge is not None else None,
            "pairwise_accuracy": round(prm_pair_pass / total, 4) if prompt_judge is not None else None,
        },
        "rows": rows,
    }
    
    OUT_REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 报告已保存: {OUT_REPORT_FILE}")


@pytest.mark.asyncio
async def test_phase3_local_qwen_precision_matrix_on_mismatch_events():
    """精度矩阵测试 - 使用Transformers格式模型"""
    print("\n" + "="*60)
    print("🧪 开始测试2: 精度矩阵测试")
    print("="*60)
    
    if not EVENTS_FILE.exists() or not AB_REPORT_FILE.exists():
        pytest.skip("required dataset/report missing")

    mismatch_ids = set(_read_ids(MISMATCH_IDS_FILE))
    ab_report = _load_json(AB_REPORT_FILE)
    wrong_gt_map = _build_wrong_vs_gt_map(ab_report)
    target_ids = [eid for eid in wrong_gt_map.keys() if not mismatch_ids or eid in mismatch_ids]
    if not target_ids:
        pytest.skip("no mismatched events found")

    print(f"✅ 找到 {len(target_ids)} 个目标事件")

    data = _load_json(EVENTS_FILE)
    events = data if isinstance(data, list) else data.get("events", [])
    event_by_id = {str(e.get("event_id") or ""): e for e in events if isinstance(e, dict)}

    # 获取Transformers模型路径（用于精度矩阵测试）
    transformers_model_path = _get_transformers_model_path()
    if transformers_model_path is None:
        pytest.fail("No Transformers model found for precision matrix test")

    os.environ["PHASE3_LOCAL_QWEN_MODEL_PATH"] = str(transformers_model_path)
    
    reviewer = await get_cached_reviewer()
    
    if not reviewer.enabled:
        pytest.skip("QwenReviewer unavailable")
    
    theme_name_index = _build_theme_name_index(reviewer)

    from theme_service.matchers.local_qwen_matcher import create_medium_qwen_matcher, create_tiny_qwen_matcher

    factories = {
        "tiny": create_tiny_qwen_matcher,
        "medium": create_medium_qwen_matcher,
    }
    precisions = ["low", "normal", "high"]

    matrix = {}
    details = []

    for f_name, factory in factories.items():
        print(f"\n🔧 测试 {f_name} matcher...")
        cfg = {
            "use_cache": True, 
            "model_name": str(transformers_model_path),  # 使用Transformers模型路径
            "match_threshold": 0.3, 
            "max_results": 20
        }
        matcher = factory(cfg)
        theme_dicts = list({id(v): v for v in (reviewer.theme_by_code or {}).values()}.values())
        matcher.initialize(theme_dicts)

        for precision in precisions:
            print(f"  📊 精度: {precision}")
            total = 0
            gt_recall = 0
            wrong_suppression = 0
            pair_pass = 0

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
            print(f"    综合准确率: {matrix[key]['pairwise_accuracy']:.2%}")

    report = {
        "transformers_model_path": str(transformers_model_path),
        "matrix": matrix,
        "details": details,
    }
    
    PRECISION_MATRIX_REPORT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n💾 精度矩阵报告已保存: {PRECISION_MATRIX_REPORT_FILE}")

    assert matrix, "precision matrix report is empty"