"""
Phase3 A/B benchmark on real 76 dataset:
- Mode A: semantic_only (baseline test_new_architecture_with_dataset)
- Mode B: semantic_plus_llm (semantic result + local Qwen reviewer reroute)

Outputs:
1) baseline vs ground-truth
2) semantic+llm vs ground-truth
3) A/B delta table
4) DB creation stats (new categories / new themes)

Usage:
  /opt/miniconda3/envs/theme_matcher_env/bin/python \
    /Users/admin/Desktop/ai_theme_app/database_service/scripts/phase3_semantic_vs_llm_benchmark.py \
    --sample-size 76 \
    --out /Users/admin/Desktop/ai_theme_app/tmp/phase3_semantic_vs_llm_76_ab.json
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
SERVICE_DIR = os.path.dirname(CURRENT_DIR)
PROJECT_ROOT = os.path.dirname(SERVICE_DIR)
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, SERVICE_DIR)

from database_service.scripts.phase2_update_mapping_audit import _is_mapping_accurate
from database_service.scripts.test_theme_processor import RealIntegrationTester
from database_service.streams.gateway_integration import get_gateway
from database_service.streams.handlers.theme_processor import DecisionType, ThemeProcessor


EQUIVALENT_TOPIC_CLUSTERS = [
    {"spacex", "太空军事", "导弹预警卫星", "星链", "商业航天", "卫星", "航天"},
    {"核聚变", "可控核聚变", "聚变能", "聚变"},
    {"对日", "中日", "靖国神社", "两用物项", "外交军事紧张"},
    {"光刻胶", "半导体", "电子化学品"},
    {"海洋经济", "海工", "海洋"},
    {"稀土", "永磁", "稀土永磁"},
    {"ai/ar眼镜", "ai眼镜", "ar眼镜", "智能眼镜"},
]


def _text_tokens(text: str) -> set[str]:
    raw = str(text or "").strip().lower()
    if not raw:
        return set()
    return {
        raw,
        raw.replace(" ", ""),
        raw.replace("相关新闻", ""),
        raw.replace("概念", ""),
    }


def _hits_cluster(left: str, right: str) -> bool:
    lt = _text_tokens(left)
    rt = _text_tokens(right)
    if not lt or not rt:
        return False

    for cluster in EQUIVALENT_TOPIC_CLUSTERS:
        cset = {str(x).strip().lower() for x in cluster if str(x).strip()}
        left_hit = any(any(c in s for c in cset) for s in lt)
        right_hit = any(any(c in s for c in cset) for s in rt)
        if left_hit and right_hit:
            return True
    return False


def _resolve_local_qwen_model_path() -> Optional[str]:
    candidates = [
        os.getenv("PHASE3_LOCAL_QWEN_MODEL_PATH", "").strip(),
        "/Users/admin/Desktop/ai_theme_app/models/Qwen2.5-0.5B-Instruct",
        "/Users/admin/Desktop/ai_theme_app/modles/Qwen2.5-0.5B-Instruct",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return path

    snapshot_root = Path(
        "/Users/admin/Desktop/ai_theme_app/.qwen_cache/models--Qwen--Qwen2.5-0.5B-Instruct/snapshots"
    )
    if snapshot_root.exists():
        snapshots = sorted(snapshot_root.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for snapshot in snapshots:
            if (snapshot / "config.json").exists():
                return str(snapshot)
    return None


def _build_mapping_rows(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for d in result.get("decision_details", []) or []:
        if not isinstance(d, dict):
            continue
        if d.get("action") != "update_theme":
            continue
        row = {
            "event_id": d.get("event_id"),
            "event_title": d.get("event_title"),
            "event_core_concept": d.get("event_core_concept"),
            "matched_theme_id": d.get("best_theme_id"),
            "matched_theme_name": d.get("best_theme_name"),
            "match_confidence": d.get("best_theme_confidence"),
            "guardrail_overlap_count": d.get("guardrail_overlap_count", 0),
            "algorithm_used": d.get("algorithm_used"),
            "match_reason": d.get("match_reason"),
        }
        row["accuracy_rule_passed"] = _is_mapping_accurate(row)
        rows.append(row)
    return rows


def _load_ground_truth() -> Dict[str, Dict[str, Any]]:
    ai_path = Path(PROJECT_ROOT) / "evaluate_service/data/raw/ai_processed_events.json"
    gt_path = Path(PROJECT_ROOT) / "evaluate_service/data/raw/validation_dataset.json"

    ai_events = json.loads(ai_path.read_text(encoding="utf-8"))
    gt_events = json.loads(gt_path.read_text(encoding="utf-8"))

    gt_by_content: Dict[str, Dict[str, Any]] = {}
    for item in gt_events:
        content = str(item.get("content") or "").strip()
        if content:
            gt_by_content[content] = item

    event_gt: Dict[str, Dict[str, Any]] = {}
    for ev in ai_events:
        event_id = str(ev.get("event_id") or "").strip()
        content = str(ev.get("content") or "").strip()
        if not event_id or not content:
            continue
        gt_item = gt_by_content.get(content)
        if not gt_item:
            continue
        event_gt[event_id] = {
            "ground_truth_theme_group": gt_item.get("theme"),
            "ground_truth_themes": gt_item.get("ground_truth_themes") or [],
            "ground_truth_title": gt_item.get("title"),
        }
    return event_gt


def _passes_ground_truth(theme_name: str, gt_themes: List[str], gt_group: str) -> bool:
    if not theme_name:
        return False
    theme_name = str(theme_name)

    for gt in gt_themes or []:
        gt = str(gt or "").strip()
        if not gt:
            continue
        if gt in theme_name or theme_name in gt:
            return True
        if _hits_cluster(gt, theme_name):
            return True

    if gt_group:
        gt_group = str(gt_group)
        if gt_group in theme_name or theme_name in gt_group:
            return True
        if _hits_cluster(gt_group, theme_name):
            return True

    return False


async def _query_table_columns(conn, table_name: str) -> List[str]:
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        ORDER BY ordinal_position
        """,
        table_name,
    )
    return [str(r["column_name"]) for r in rows]


async def _snapshot_db_state() -> Dict[str, Any]:
    gw = await get_gateway(enable_retry=False)
    base = gw.base_gateway
    client = base._client

    async with client.pool.acquire() as conn:
        theme_rows = await conn.fetch("SELECT code FROM theme_master WHERE code IS NOT NULL")
        theme_codes = {str(r["code"]) for r in theme_rows if r.get("code")}

        category_columns = await _query_table_columns(conn, "financial_categories")
        code_col = "category_code" if "category_code" in category_columns else "code"

        category_rows = await conn.fetch(f"SELECT {code_col} AS code FROM financial_categories")
        category_codes = {str(r["code"]) for r in category_rows if r.get("code")}

    return {
        "theme_codes": theme_codes,
        "category_codes": category_codes,
        "category_code_column": code_col,
    }


async def _cleanup_new_records(new_theme_codes: set[str], new_category_codes: set[str], category_code_column: str) -> Dict[str, int]:
    if not new_theme_codes and not new_category_codes:
        return {"deleted_themes": 0, "deleted_categories": 0}

    gw = await get_gateway(enable_retry=False)
    base = gw.base_gateway
    client = base._client

    deleted_themes = 0
    deleted_categories = 0

    async with client.pool.acquire() as conn:
        if new_theme_codes:
            theme_code_list = list(new_theme_codes)
            await conn.execute(
                """
                DELETE FROM event_theme_map
                WHERE theme_id IN (
                    SELECT id FROM theme_master WHERE code = ANY($1::text[])
                )
                """,
                theme_code_list,
            )
            resp = await conn.execute(
                "DELETE FROM theme_master WHERE code = ANY($1::text[])",
                theme_code_list,
            )
            deleted_themes = int(str(resp).split()[-1]) if str(resp).split() else 0

        if new_category_codes:
            category_code_list = list(new_category_codes)
            resp = await conn.execute(
                f"DELETE FROM financial_categories WHERE ({category_code_column})::text = ANY($1::text[])",
                category_code_list,
            )
            deleted_categories = int(str(resp).split()[-1]) if str(resp).split() else 0

    return {
        "deleted_themes": deleted_themes,
        "deleted_categories": deleted_categories,
    }


@dataclass
class QwenReviewer:
    enabled: bool
    matcher: Any = None
    theme_by_code: Dict[str, Dict[str, Any]] = None
    theme_by_id: Dict[str, Dict[str, Any]] = None
    vector_cache: Dict[str, Any] = None
    llama_bin: Optional[str] = None
    llama_model_path: Optional[str] = None
    judge_cache: Dict[str, Dict[str, bool]] = None
    redis_client: Any = None
    redis_prefix: str = "db:"
    redis_ttl_seconds: int = 86400
    event_vec_cache: Dict[str, Any] = None
    pair_score_cache: Dict[str, float] = None

    @classmethod
    async def build(cls) -> "QwenReviewer":
        try:
            from theme_service.matchers.local_qwen_matcher import create_medium_qwen_matcher
        except Exception as exc:
            print(f"⚠️ LLM审查器不可用，降级为禁用: {exc}")
            return cls(enabled=False)

        model_path = _resolve_local_qwen_model_path()
        if not model_path:
            print("⚠️ 未找到本地Qwen模型，降级为禁用")
            return cls(enabled=False)

        print(f"🧠 初始化本地Qwen复核模型: {model_path}")
        t0 = time.time()

        print("   [LLM-INIT 1/4] 获取网关与题材数据...")
        gw = await get_gateway(enable_retry=False)
        themes = await gw.base_gateway.get_all_active_themes(limit=5000)
        print(f"   [LLM-INIT 1/4] 完成，题材数: {len(themes)}，耗时 {time.time()-t0:.2f}s")

        theme_dicts: List[Dict[str, Any]] = []
        theme_by_code: Dict[str, Dict[str, Any]] = {}
        theme_by_id: Dict[str, Dict[str, Any]] = {}
        print("   [LLM-INIT 2/4] 组装题材文本特征...")
        for t in themes:
            tags_obj = getattr(t, "tags", None)
            if isinstance(tags_obj, dict):
                kws = list(tags_obj.get("keywords", []) or [])
            elif tags_obj is not None and hasattr(tags_obj, "keywords"):
                kws = list(getattr(tags_obj, "keywords", []) or [])
            else:
                kws = []
            theme_dicts.append(
                {
                    "id": str(getattr(t, "id", "") or ""),
                    "code": str(getattr(t, "code", "") or ""),
                    "name": str(getattr(t, "name", "") or ""),
                    "description": str(getattr(t, "description", "") or ""),
                    "keywords": kws,
                    "level1_category": str(getattr(t, "level1_category", "") or ""),
                    "level2_category": str(getattr(t, "level2_category", "") or ""),
                    "level3_category": str(getattr(t, "level3_category", "") or ""),
                }
            )
            if theme_dicts[-1]["code"]:
                theme_by_code[theme_dicts[-1]["code"]] = theme_dicts[-1]
            if theme_dicts[-1]["id"]:
                theme_by_id[theme_dicts[-1]["id"]] = theme_dicts[-1]
        print(f"   [LLM-INIT 2/4] 完成，耗时 {time.time()-t0:.2f}s")

        cfg = {"use_cache": True, "match_threshold": 0.3, "max_results": 5, "model_name": model_path}
        print("   [LLM-INIT 3/4] 创建并初始化本地Qwen匹配器（可能较慢）...")
        matcher = create_medium_qwen_matcher(cfg)
        matcher.initialize(theme_dicts)
        print(f"   [LLM-INIT 3/4] 完成，耗时 {time.time()-t0:.2f}s")

        print(f"   [LLM-INIT 4/4] LLM审查器就绪，题材向量数: {len(theme_dicts)}，总耗时 {time.time()-t0:.2f}s")
        print("   [LLM-JUDGE] 使用本地0.5B嵌入二分类裁判（无gguf/无llama-cli）")
        redis_client = cls._prepare_redis_client()
        redis_prefix = os.getenv("PHASE3_LLM_REDIS_PREFIX", "db:")
        redis_ttl = int(os.getenv("PHASE3_LLM_REDIS_TTL_SECONDS", "86400"))
        if redis_client is not None:
            print(f"   [LLM-CACHE] Redis缓存已启用: prefix={redis_prefix}, ttl={redis_ttl}s")
        else:
            print("   [LLM-CACHE] Redis缓存未启用（仅内存缓存）")
        return cls(
            enabled=True,
            matcher=matcher,
            theme_by_code=theme_by_code,
            theme_by_id=theme_by_id,
            vector_cache={},
            judge_cache={},
            redis_client=redis_client,
            redis_prefix=redis_prefix,
            redis_ttl_seconds=redis_ttl,
            event_vec_cache={},
            pair_score_cache={},
        )

    @staticmethod
    def _prepare_redis_client():
        redis_url = str(os.getenv("REDIS_URL", "")).strip()
        if not redis_url:
            return None
        try:
            import redis

            client = redis.Redis.from_url(
                redis_url,
                decode_responses=False,
                socket_timeout=0.2,
                socket_connect_timeout=0.2,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _redis_key(self, namespace: str, digest: str) -> str:
        prefix = self.redis_prefix if self.redis_prefix.endswith(":") else f"{self.redis_prefix}:"
        return f"{prefix}{namespace}:{digest}"

    def _sha(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def _redis_get_json(self, key: str) -> Optional[Any]:
        if self.redis_client is None:
            return None
        try:
            raw = self.redis_client.get(key)
            if not raw:
                return None
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8", errors="ignore")
            return json.loads(raw)
        except Exception:
            return None

    def _redis_set_json(self, key: str, value: Any):
        if self.redis_client is None:
            return
        try:
            payload = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.redis_client.setex(key, int(self.redis_ttl_seconds), payload)
        except Exception:
            return

    def _get_or_encode_event_embedding(self, event_text: str):
        et = str(event_text or "").strip()
        if not et:
            return None

        digest = self._sha(et)
        if self.event_vec_cache is not None and digest in self.event_vec_cache:
            return self.event_vec_cache[digest]
        key = self._redis_key("phase3_event_embedding", digest)
        cached = self._redis_get_json(key)
        if isinstance(cached, list) and cached:
            try:
                import numpy as np

                vec = np.asarray(cached, dtype=np.float32)
                if self.event_vec_cache is not None:
                    self.event_vec_cache[digest] = vec
                return vec
            except Exception:
                pass

        vec = self.matcher._encode_single_direct(et)
        if vec is not None:
            try:
                self._redis_set_json(key, vec.tolist())
            except Exception:
                pass
            if self.event_vec_cache is not None:
                self.event_vec_cache[digest] = vec
        return vec

    def _resolve_theme_obj(self, theme_id_or_code: str, fallback_name: str = "") -> Dict[str, Any]:
        k = str(theme_id_or_code or "").strip()
        if not k:
            return {"id": "", "code": "", "name": fallback_name, "keywords": [fallback_name]}
        if self.theme_by_code and k in self.theme_by_code:
            return self.theme_by_code[k]
        if self.theme_by_id and k in self.theme_by_id:
            return self.theme_by_id[k]
        # 有些候选只有name，没有完整字段
        return {"id": k, "code": k, "name": fallback_name or k, "keywords": [fallback_name or k]}

    def _candidate_score(self, event_text: str, candidate_theme: Dict[str, Any], event_vec=None) -> float:
        # 使用同一个Qwen嵌入空间做“候选集内重排”，不做全库重检索
        if event_vec is None:
            event_vec = self._get_or_encode_event_embedding(event_text)
        if event_vec is None:
            return 0.0

        event_hash = self._sha(str(event_text or "").strip())
        code = str(candidate_theme.get("code") or "")
        tid = str(candidate_theme.get("id") or "")
        key = code or tid or candidate_theme.get("name", "")
        pair_key = f"{event_hash}|{key}" if event_hash and key else ""
        if pair_key and self.pair_score_cache is not None and pair_key in self.pair_score_cache:
            return float(self.pair_score_cache[pair_key])
        if pair_key:
            cached_score = self._redis_get_json(self._redis_key("phase3_pair_score", self._sha(pair_key)))
            if isinstance(cached_score, (int, float)):
                score = float(cached_score)
                if self.pair_score_cache is not None:
                    self.pair_score_cache[pair_key] = score
                return score

        theme_vec = None
        if key and key in self.vector_cache:
            theme_vec = self.vector_cache[key]
        elif code and code in self.matcher.theme_vectors:
            theme_vec = self.matcher.theme_vectors[code]
            self.vector_cache[key] = theme_vec
        else:
            t_text = self.matcher._build_theme_embedding_text(candidate_theme)
            theme_vec = self.matcher._encode_single_direct(t_text)
            if theme_vec is not None and key:
                self.vector_cache[key] = theme_vec

        if theme_vec is None:
            return 0.0
        sim_arr = self.matcher._batch_similarity(event_vec, [theme_vec])
        score = float(sim_arr[0]) if len(sim_arr) else 0.0
        if pair_key:
            if self.pair_score_cache is not None:
                self.pair_score_cache[pair_key] = score
            self._redis_set_json(self._redis_key("phase3_pair_score", self._sha(pair_key)), score)
        return score

    def _same_l1_l2(self, left: Dict[str, Any], right: Dict[str, Any]) -> bool:
        l1a = str(left.get("level1_category") or "").strip()
        l2a = str(left.get("level2_category") or "").strip()
        l1b = str(right.get("level1_category") or "").strip()
        l2b = str(right.get("level2_category") or "").strip()
        return bool(l1a and l2a and l1a == l1b and l2a == l2b)

    def _event_terms(self, event_data: Dict[str, Any]) -> List[str]:
        ai = event_data.get("ai_analysis") or {}
        kws = ai.get("keywords") or []
        terms = []
        for v in [
            event_data.get("title"),
            event_data.get("content"),
            ai.get("core_concept"),
            *kws,
        ]:
            s = str(v or "").strip()
            if s:
                terms.append(s.lower())
        return terms

    def _theme_terms(self, theme_obj: Dict[str, Any]) -> List[str]:
        kws = theme_obj.get("keywords") or []
        terms = []
        for v in [
            theme_obj.get("name"),
            theme_obj.get("description"),
            theme_obj.get("level1_category"),
            theme_obj.get("level2_category"),
            *kws,
        ]:
            s = str(v or "").strip()
            if s:
                terms.append(s.lower())
        return terms

    def _has_term_overlap(self, event_terms: List[str], theme_terms: List[str]) -> bool:
        for e in event_terms:
            for t in theme_terms:
                if not e or not t:
                    continue
                if e in t or t in e:
                    return True
        return False

    def _judge_event_themes_binary(self, event_text: str, theme_names: List[str], timeout: int = 90) -> Dict[str, bool]:
        if not event_text.strip() or not theme_names:
            return {}

        local_key = f"{event_text}||{'|'.join(theme_names)}"
        if self.judge_cache is not None and local_key in self.judge_cache:
            return self.judge_cache[local_key]

        redis_key = self._redis_key("phase3_llm_judge", self._sha(local_key))
        cached = self._redis_get_json(redis_key)
        if isinstance(cached, dict) and cached:
            if self.judge_cache is not None:
                self.judge_cache[local_key] = cached
            return cached

        parsed: Dict[str, bool] = {}
        event_vec = self._get_or_encode_event_embedding(event_text)
        if event_vec is None:
            return parsed
        yes_threshold = float(os.getenv("PHASE3_LLM_BINARY_YES", "0.70"))
        high_conf_yes = float(os.getenv("PHASE3_LLM_BINARY_HIGH", "0.78"))
        for name in theme_names:
            name = str(name or "").strip()
            if not name:
                parsed[name] = False
                continue
            # 复用本地0.5B嵌入空间做pairwise判别：事件 vs 单题材
            theme_obj = self._resolve_theme_obj("", name)
            s = self._candidate_score(event_text, theme_obj, event_vec=event_vec)
            # 高分直接是，普通阈值要求再保守一点
            parsed[name] = bool(s >= high_conf_yes or s >= yes_threshold)

        if parsed:
            if self.judge_cache is not None:
                self.judge_cache[local_key] = parsed
            self._redis_set_json(redis_key, parsed)
        return parsed

    def close(self):
        return

    def review_update_decision(
        self,
        event_data: Dict[str, Any],
        decision: Dict[str, Any],
        match_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not self.enabled or self.matcher is None:
            return {"verdict": "accept", "enabled": False, "reason": "reviewer_disabled", "adopted": True}

        current_theme_id = str((decision.get("theme_data") or {}).get("id") or "")
        current_theme_name = str((decision.get("theme_data") or {}).get("name") or "")
        themes = (match_result or {}).get("themes") or []
        if not isinstance(themes, list) or not themes:
            return {
                "verdict": "uncertain",
                "enabled": True,
                "reason": "llm_abstain_no_semantic_candidates",
                "adopted": False,
            }

        topk = themes[:10]
        event_text = " ".join(
            [
                str(event_data.get("title") or ""),
                str(event_data.get("content") or ""),
                str((event_data.get("ai_analysis") or {}).get("core_concept") or ""),
            ]
        ).strip()
        if not event_text:
            return {"verdict": "uncertain", "enabled": True, "reason": "llm_abstain_empty_event", "adopted": False}
        event_vec = self._get_or_encode_event_embedding(event_text)
        if event_vec is None:
            return {"verdict": "uncertain", "enabled": True, "reason": "llm_abstain_event_encode_fail", "adopted": False}
        event_terms = self._event_terms(event_data)

        scored = []
        for c in topk:
            cid = str((c or {}).get("theme_id") or (c or {}).get("id") or "")
            cname = str((c or {}).get("theme_name") or (c or {}).get("name") or "")
            theme_obj = self._resolve_theme_obj(cid, cname)
            s = self._candidate_score(event_text, theme_obj, event_vec=event_vec)
            theme_terms = self._theme_terms(theme_obj)
            overlap_ok = self._has_term_overlap(event_terms, theme_terms)
            scored.append(
                {
                    "theme_id": cid or str(theme_obj.get("code") or theme_obj.get("id") or ""),
                    "theme_name": cname or str(theme_obj.get("name") or ""),
                    "qwen_score": s,
                    "semantic_score": float((c or {}).get("confidence") or 0.0),
                    "overlap_ok": overlap_ok,
                }
            )

        scored.sort(key=lambda x: x["qwen_score"], reverse=True)
        # 一对一硬门禁：只有“相似度达标+术语有重叠”的候选才可进入最终选择
        pass_threshold = float(os.getenv("PHASE3_LLM_PAIR_PASS", "0.74"))
        passed = [x for x in scored if x["qwen_score"] >= pass_threshold and x["overlap_ok"]]
        best = passed[0] if passed else scored[0]
        current = next(
            (x for x in scored if x["theme_id"] == current_theme_id or x["theme_name"] == current_theme_name),
            None,
        )
        if current is None:
            # 当前结果不在候选池，放行并标记异常
            return {
                "verdict": "uncertain",
                "enabled": True,
                "reason": "llm_abstain_current_not_in_candidates",
                "adopted": False,
                "llm_best": best,
            }

        # 全部候选都未通过一对一门禁 -> 直接否决update（避免完全不相关误匹配）
        if not passed:
            return {
                "verdict": "reject",
                "enabled": True,
                "adopted": False,
                "reason": "llm_reject_no_pairwise_pass",
                "current": current,
                "best": best,
                "pair_pass_threshold": pass_threshold,
                "top3": scored[:3],
            }

        current_obj = self._resolve_theme_obj(current.get("theme_id") or "", current.get("theme_name") or "")
        best_obj = self._resolve_theme_obj(best.get("theme_id") or "", best.get("theme_name") or "")
        same_l1_l2 = self._same_l1_l2(current_obj, best_obj)

        # 先做“逐候选是/否裁判”，避免明显跨域误切换（如AI智能体 -> 卫星制造）
        judge_map = self._judge_event_themes_binary(
            event_text,
            [str(current.get("theme_name") or ""), str(best.get("theme_name") or "")],
        )
        current_ok = judge_map.get(str(current.get("theme_name") or ""), None)
        best_ok = judge_map.get(str(best.get("theme_name") or ""), None)

        # 三段硬门控：高相似=已有题材，低相似=新题材，临界区=人工审核
        # 可通过环境变量调参
        t_low = float(os.getenv("PHASE3_LLM_SIM_LOW", "0.60"))
        t_high = float(os.getenv("PHASE3_LLM_SIM_HIGH", "0.74"))
        switch_margin = float(os.getenv("PHASE3_LLM_SWITCH_MARGIN", "0.05"))
        gap = float(best["qwen_score"] - current["qwen_score"])

        should_switch = (
            best["theme_id"] != current["theme_id"]
            and best["qwen_score"] >= t_high
            and gap >= switch_margin
            and same_l1_l2
        )

        # 裁判优先：明确“当前否、最佳是”才允许后续切换；明确“当前是、最佳否”禁止切换
        if current_ok is True and best_ok is False:
            should_switch = False
        elif current_ok is False and best_ok is True:
            # only keep switch candidate in same category path
            should_switch = should_switch and same_l1_l2
        elif current_ok is False and best_ok is False:
            return {
                "verdict": "reject",
                "enabled": True,
                "adopted": False,
                "reason": "llm_judge_both_negative",
                "should_switch": False,
                "current": current,
                "best": best,
                "same_l1_l2": same_l1_l2,
                "judge_current": current_ok,
                "judge_best": best_ok,
                "top3": scored[:3],
            }

        if best["qwen_score"] >= t_high:
            verdict = "accept"
            reason = "llm_accept_high_similarity"
        elif best["qwen_score"] <= t_low:
            verdict = "reject"
            reason = "llm_reject_low_similarity"
        else:
            verdict = "uncertain"
            reason = "llm_uncertain_boundary_manual_review"

        return {
            "verdict": verdict,
            "enabled": True,
            "adopted": verdict == "accept",
            "reason": reason,
            "should_switch": should_switch,
            "current": current,
            "best": best,
            "score_gap": round(gap, 4),
            "same_l1_l2": same_l1_l2,
            "judge_current": current_ok,
            "judge_best": best_ok,
            "sim_low": t_low,
            "sim_high": t_high,
            "pair_pass_threshold": pass_threshold,
            "top3": scored[:3],
        }


async def _run_once(
    sample_size: int,
    mode: str,
    event_gt: Dict[str, Dict[str, Any]],
    event_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    print("\n" + "=" * 90)
    print(f"🚀 开始模式: {mode}, sample_size={sample_size}")
    print("=" * 90)

    before = await _snapshot_db_state()
    reviewer: Optional[QwenReviewer] = None

    original_build_decision = ThemeProcessor._build_decision

    if mode == "semantic_plus_llm":
        reviewer = await QwenReviewer.build()

        def _patched_build_decision(self, decision_type: str, **kwargs):
            decision = original_build_decision(self, decision_type, **kwargs)
            if not isinstance(decision, dict):
                return decision
            if decision.get("action") != "update_theme":
                return decision

            review_meta = reviewer.review_update_decision(
                kwargs.get("event_data") or {},
                decision,
                kwargs.get("match_result") or {},
            )
            verdict = str(review_meta.get("verdict") or "uncertain")
            if verdict == "accept":
                if review_meta.get("should_switch"):
                    best = review_meta.get("best") or {}
                    td = decision.get("theme_data") or {}
                    td["id"] = best.get("theme_id") or td.get("id")
                    td["name"] = best.get("theme_name") or td.get("name")
                    decision["theme_data"] = td
                decision["llm_review"] = review_meta
                return decision

            if verdict == "reject":
                rerouted = original_build_decision(
                    self,
                    DecisionType.NO_MATCH_AFTER_FALLBACK,
                    **kwargs,
                )
                if isinstance(rerouted, dict):
                    rerouted["llm_review"] = {
                        **review_meta,
                        "rerouted_from": "update_theme",
                        "rerouted_to": rerouted.get("action"),
                    }
                    base_reason = str(rerouted.get("reason") or "")
                    rerouted["reason"] = (base_reason + "|llm_reject_low_similarity").strip("|")
                return rerouted

            # uncertain -> 人工审核路径（统一发pending）
            decision["action"] = "publish_clustering"
            decision["operations"] = ["publish_to_pending"]
            decision["llm_review"] = {
                **review_meta,
                "rerouted_from": "update_theme",
                "rerouted_to": "publish_clustering",
                "manual_review_required": True,
            }
            base_reason = str(decision.get("reason") or "")
            decision["reason"] = (base_reason + "|llm_uncertain_manual_review").strip("|")
            return decision

        ThemeProcessor._build_decision = _patched_build_decision

    tester = RealIntegrationTester()
    target_event_ids = {str(x).strip() for x in (event_ids or []) if str(x).strip()}
    if target_event_ids:
        original_load_dataset = tester.load_test_dataset

        async def _load_and_filter_dataset():
            payload = await original_load_dataset()
            if not isinstance(payload, dict):
                return payload
            events = payload.get("events") or []
            filtered = [
                e for e in events
                if str(e.get("event_id") or e.get("id") or "").strip() in target_event_ids
            ]
            payload["events"] = filtered
            print(
                f"🎯 定向事件过滤生效: {len(filtered)}/{len(events)} "
                f"(target_ids={len(target_event_ids)})"
            )
            return payload

        tester.load_test_dataset = _load_and_filter_dataset
    setup_ok = await tester.setup()
    if not setup_ok:
        ThemeProcessor._build_decision = original_build_decision
        return {
            "mode": mode,
            "sample_size": sample_size,
            "success": False,
            "error": "setup_failed",
        }

    try:
        result = await tester.test_new_architecture_with_dataset(
            sample_size=sample_size,
            return_details=True,
        )
    finally:
        await tester.cleanup()
        ThemeProcessor._build_decision = original_build_decision
        if reviewer is not None:
            reviewer.close()

    after = await _snapshot_db_state()

    new_theme_codes = sorted(after["theme_codes"] - before["theme_codes"])
    new_category_codes = sorted(after["category_codes"] - before["category_codes"])

    rows = _build_mapping_rows(result if isinstance(result, dict) else {})

    gt_total = 0
    gt_hit = 0
    gt_details = []
    for row in rows:
        event_id = str(row.get("event_id") or "")
        gt = event_gt.get(event_id)
        if not gt:
            continue

        gt_total += 1
        matched_theme = str(row.get("matched_theme_name") or "")
        hit = _passes_ground_truth(
            matched_theme,
            gt.get("ground_truth_themes") or [],
            str(gt.get("ground_truth_theme_group") or ""),
        )
        if hit:
            gt_hit += 1

        gt_details.append(
            {
                "event_id": event_id,
                "event_title": row.get("event_title"),
                "matched_theme_name": matched_theme,
                "ground_truth_themes": gt.get("ground_truth_themes") or [],
                "ground_truth_theme_group": gt.get("ground_truth_theme_group"),
                "ground_truth_passed": hit,
                "accuracy_rule_passed": row.get("accuracy_rule_passed"),
            }
        )

    update_count = len(rows)
    accurate_count = sum(1 for r in rows if r.get("accuracy_rule_passed"))
    accuracy_rule = (accurate_count / update_count) if update_count else 0.0
    gt_accuracy = (gt_hit / gt_total) if gt_total else 0.0

    create_details = (result or {}).get("create_new_theme_details", []) if isinstance(result, dict) else []
    create_count = len(create_details or [])
    concept_hierarchy_count = sum(1 for d in create_details if (d or {}).get("categories_to_create_count", 0) > 0)

    return {
        "mode": mode,
        "sample_size": sample_size,
        "success": bool(isinstance(result, dict) and result.get("success", False)),
        "summary": {
            "decision_total": len((result or {}).get("decision_details", []) if isinstance(result, dict) else []),
            "update_theme_decisions": update_count,
            "create_new_theme_decisions": create_count,
            "concept_hierarchy_created_count": concept_hierarchy_count,
            "accuracy_rule": round(accuracy_rule, 4),
            "accuracy_rule_passed_count": accurate_count,
            "ground_truth_covered": gt_total,
            "ground_truth_hit_count": gt_hit,
            "ground_truth_accuracy": round(gt_accuracy, 4),
            "db_new_theme_count": len(new_theme_codes),
            "db_new_category_count": len(new_category_codes),
        },
        "db_delta": {
            "new_theme_codes": new_theme_codes,
            "new_category_codes": new_category_codes,
            "category_code_column": after["category_code_column"],
        },
        "stream_stats": (result or {}).get("stream_stats", {}) if isinstance(result, dict) else {},
        "t03_validation": (result or {}).get("t03_validation", {}) if isinstance(result, dict) else {},
        "t04_validation": (result or {}).get("t04_validation", {}) if isinstance(result, dict) else {},
        "update_theme_mappings": rows,
        "ground_truth_comparison": gt_details,
    }


def _build_ab_summary(semantic_result: Dict[str, Any], llm_result: Dict[str, Any]) -> Dict[str, Any]:
    s = semantic_result.get("summary", {})
    l = llm_result.get("summary", {})

    def _num(d: Dict[str, Any], k: str) -> float:
        try:
            return float(d.get(k, 0) or 0)
        except Exception:
            return 0.0

    return {
        "ground_truth_accuracy": {
            "semantic_only": _num(s, "ground_truth_accuracy"),
            "semantic_plus_llm": _num(l, "ground_truth_accuracy"),
            "delta": round(_num(l, "ground_truth_accuracy") - _num(s, "ground_truth_accuracy"), 4),
        },
        "accuracy_rule": {
            "semantic_only": _num(s, "accuracy_rule"),
            "semantic_plus_llm": _num(l, "accuracy_rule"),
            "delta": round(_num(l, "accuracy_rule") - _num(s, "accuracy_rule"), 4),
        },
        "db_new_theme_count": {
            "semantic_only": int(_num(s, "db_new_theme_count")),
            "semantic_plus_llm": int(_num(l, "db_new_theme_count")),
            "delta": int(_num(l, "db_new_theme_count") - _num(s, "db_new_theme_count")),
        },
        "db_new_category_count": {
            "semantic_only": int(_num(s, "db_new_category_count")),
            "semantic_plus_llm": int(_num(l, "db_new_category_count")),
            "delta": int(_num(l, "db_new_category_count") - _num(s, "db_new_category_count")),
        },
        "create_new_theme_decisions": {
            "semantic_only": int(_num(s, "create_new_theme_decisions")),
            "semantic_plus_llm": int(_num(l, "create_new_theme_decisions")),
            "delta": int(_num(l, "create_new_theme_decisions") - _num(s, "create_new_theme_decisions")),
        },
        "update_theme_decisions": {
            "semantic_only": int(_num(s, "update_theme_decisions")),
            "semantic_plus_llm": int(_num(l, "update_theme_decisions")),
            "delta": int(_num(l, "update_theme_decisions") - _num(s, "update_theme_decisions")),
        },
    }


async def _main_async(
    sample_size: int,
    out: str,
    auto_cleanup_between_runs: bool,
    mode: str,
    baseline_report: Optional[str],
    event_ids: Optional[List[str]] = None,
) -> None:
    event_gt = _load_ground_truth()
    print(f"📚 标准集映射加载完成: {len(event_gt)} 条 event_id 可对齐")

    semantic_result: Optional[Dict[str, Any]] = None
    llm_result: Optional[Dict[str, Any]] = None
    cleanup_result = {"deleted_themes": 0, "deleted_categories": 0}

    if mode in {"ab", "semantic_only"}:
        semantic_result = await _run_once(sample_size, "semantic_only", event_gt, event_ids=event_ids)

    if mode == "ab":
        if auto_cleanup_between_runs and semantic_result:
            print("\n🧹 执行模式间清理（删除语义模式新增分类/题材）...")
            cleanup_result = await _cleanup_new_records(
                set((semantic_result.get("db_delta") or {}).get("new_theme_codes", [])),
                set((semantic_result.get("db_delta") or {}).get("new_category_codes", [])),
                (semantic_result.get("db_delta") or {}).get("category_code_column", "category_code"),
            )
            print(f"   清理完成: {cleanup_result}")
        llm_result = await _run_once(sample_size, "semantic_plus_llm", event_gt, event_ids=event_ids)

    if mode == "semantic_plus_llm":
        llm_result = await _run_once(sample_size, "semantic_plus_llm", event_gt, event_ids=event_ids)
        if baseline_report:
            base_path = Path(baseline_report)
            if base_path.exists():
                baseline_payload = json.loads(base_path.read_text(encoding="utf-8"))
                # 兼容两种结构：整包或单次语义输出
                semantic_result = baseline_payload.get("semantic_only") or baseline_payload

    ab = _build_ab_summary(semantic_result or {}, llm_result or {}) if semantic_result and llm_result else {}

    payload = {
        "generated_at": datetime.now().isoformat(),
        "sample_size": sample_size,
        "mode": f"phase3_semantic_vs_llm_{mode}",
        "ground_truth_source": "evaluate_service/data/raw/validation_dataset.json",
        "events_source": "evaluate_service/data/raw/ai_processed_events.json",
        "auto_cleanup_between_runs": auto_cleanup_between_runs,
        "cleanup_between_runs_result": cleanup_result,
        "semantic_only": semantic_result,
        "semantic_plus_llm": llm_result,
        "ab_comparison": ab,
        "baseline_report": baseline_report,
    }

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if ab:
        print("\n" + "=" * 90)
        print("📊 A/B 对比摘要")
        print("=" * 90)
        for metric, values in ab.items():
            print(
                f"{metric}: semantic={values['semantic_only']} | "
                f"semantic+llm={values['semantic_plus_llm']} | delta={values['delta']}"
            )

    print(f"\n报告输出: {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample-size", type=int, default=76)
    parser.add_argument(
        "--out",
        type=str,
        default="tmp/phase3_semantic_vs_llm_benchmark.ab76.json",
    )
    parser.add_argument(
        "--no-auto-clean-between-runs",
        action="store_true",
        help="Disable cleanup between semantic run and semantic+llm run",
    )
    parser.add_argument(
        "--mode",
        choices=["ab", "semantic_only", "semantic_plus_llm"],
        default="ab",
        help="ab=两轮连跑；semantic_only=仅第一轮；semantic_plus_llm=仅第二轮",
    )
    parser.add_argument(
        "--baseline-report",
        type=str,
        default="",
        help="mode=semantic_plus_llm 时可传第一轮报告用于自动生成A/B对比",
    )
    parser.add_argument(
        "--event-ids-file",
        type=str,
        default="",
        help="仅测试指定event_id（每行一个）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    event_ids: List[str] = []
    if str(args.event_ids_file or "").strip():
        p = Path(args.event_ids_file).expanduser()
        if p.exists():
            lines = [x.strip() for x in p.read_text(encoding="utf-8").splitlines()]
            event_ids = [x for x in lines if x]
            print(f"📌 载入定向事件ID: {len(event_ids)} 条 ({p})")
        else:
            print(f"⚠️ event_ids_file不存在，忽略: {p}")
    asyncio.run(
        _main_async(
            sample_size=max(1, int(args.sample_size)),
            out=args.out,
            auto_cleanup_between_runs=not bool(args.no_auto_clean_between_runs),
            mode=args.mode,
            baseline_report=(args.baseline_report or "").strip() or None,
            event_ids=event_ids,
        )
    )


if __name__ == "__main__":
    main()
