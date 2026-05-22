#!/usr/bin/env python3
"""
分级相似度注入测试：精确验证 Qwen 1.5B 去重判定能力。

构造隔离的 (原始, 变体) title 对，每对专属一个 bucket，
确保相似度精确落入目标区间，强制触发对应判定路径。

5 级 × 10 对 = 50 对，期望路径：
  L0: ~1.00  → high_similarity 自动去重
  L1: ~0.90  → high_similarity 自动去重
  L2: ~0.78  → 灰区 → Qwen 判定为 same
  L3: ~0.65  → 灰区 → Qwen 判定为 same
  L4: ~0.40  → low_similarity 自动保留

用法:
  conda run -n theme_matcher_env python test_dedup_injection.py --per-level 10
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CN_TZ = timezone(timedelta(hours=8))
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

logger = logging.getLogger("dedup_inject")


# ── helpers ────────────────────────────────────────────────────────────

def _pick(row: dict, *keys: str) -> Any:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return None


def _sim_trim(text: str, target_ratio: float) -> str:
    """精确截断文本到目标长度比，保证 SequenceMatcher 相似度接近 target。

    策略：保留完整前缀，截断正文，匹配长度比 vs 实际字符匹配的差异。
    公式：len(truncated) / len(full) ≈ target_ratio
    SequenceMatcher 在纯截断场景下近似于长度比（差异 < 0.03）。
    """
    if not text or len(text) < 10:
        return text

    prefix = ""
    body = text
    m = re.match(r'(ZTAG\d{4}\s+)', text)
    if m:
        prefix = m.group(1)
        body = text[m.end():]

    full_len = len(prefix) + len(body)
    # 计算截断后总长以匹配目标长度比
    target_len = max(len(prefix) + 3, int(full_len * target_ratio))
    keep_body = max(3, target_len - len(prefix))
    truncated = prefix + body[:keep_body]

    # 微调：如果实际 sim 与目标偏差 > 0.03，做小范围修正
    sim = difflib.SequenceMatcher(None, text, truncated).ratio()
    for _ in range(10):
        if abs(sim - target_ratio) <= 0.03:
            break
        if sim > target_ratio and keep_body > 3:
            keep_body = max(3, keep_body - 1)
        elif sim < target_ratio and keep_body < len(body):
            keep_body = min(len(body), keep_body + 1)
        truncated = prefix + body[:keep_body]
        sim = difflib.SequenceMatcher(None, text, truncated).ratio()

    return truncated


def _approx_sim(a: str, b: str) -> float:
    """快速计算两段文本的相似度。"""
    return difflib.SequenceMatcher(None, a, b).ratio()


# ── variant generators ─────────────────────────────────────────────────

def _unique_tag(i: int) -> str:
    """生成唯一的前缀标签，确保每个注入对落入独立 bucket。"""
    return f"ZTAG{i:04d}"


def gen_L0_identical(seed_title: str, seed_content: str, i: int) -> dict:
    """完全相同。"""
    tag = _unique_tag(i)
    return {
        "title": f"{tag} {seed_title}",  # 加 tag 保证独立 bucket
        "content": seed_content,
        "source_channel": "injected_test",
        "_inject_level": "L0",
        "_inject_id": f"L0_{i}",
        "_pair_tag": tag,
        "_target_sim": 1.0,
    }

def gen_L1_tweak(seed_title: str, seed_content: str, i: int) -> dict:
    """标题 ~0.90 相似。"""
    tag = _unique_tag(i)
    new_title = _sim_trim(f"{tag} {seed_title}", 0.90)
    return {
        "title": new_title,
        "content": seed_content,
        "source_channel": "injected_test",
        "_inject_level": "L1",
        "_inject_id": f"L1_{i}",
        "_pair_tag": tag,
        "_target_sim": 0.90,
    }

def gen_L2_rephrase(seed_title: str, seed_content: str, i: int) -> dict:
    """标题 ~0.78, 内容 ~0.82 — 灰区, 期望 Qwen 判定为 same。"""
    tag = _unique_tag(i)
    new_title = _sim_trim(f"{tag} {seed_title}", 0.78)
    new_content = _sim_trim(seed_content, 0.82)
    return {
        "title": new_title,
        "content": new_content,
        "source_channel": "injected_test",
        "_inject_level": "L2",
        "_inject_id": f"L2_{i}",
        "_pair_tag": tag,
        "_target_sim": 0.78,
    }

def gen_L3_65pct(seed_title: str, seed_content: str, i: int) -> dict:
    """标题 ~0.65, 内容 ~0.68 — 灰区下沿, 期望 Qwen 判定为 same。"""
    tag = _unique_tag(i)
    new_title = _sim_trim(f"{tag} {seed_title}", 0.65)
    new_content = _sim_trim(seed_content, 0.68)
    return {
        "title": new_title,
        "content": new_content,
        "source_channel": "injected_test",
        "_inject_level": "L3",
        "_inject_id": f"L3_{i}",
        "_pair_tag": tag,
        "_target_sim": 0.65,
    }

def gen_L4_40pct(seed_title: str, seed_content: str, i: int) -> dict:
    """标题 ~0.40 — 低于 0.5, 不应判定为重复。"""
    tag = _unique_tag(i)
    new_title = _sim_trim(f"{tag} {seed_title}", 0.40)
    new_content = _sim_trim(seed_content, 0.42)
    return {
        "title": new_title,
        "content": new_content,
        "source_channel": "injected_test",
        "_inject_level": "L4",
        "_inject_id": f"L4_{i}",
        "_pair_tag": tag,
        "_target_sim": 0.40,
    }


GENERATORS = {
    "L0": gen_L0_identical,
    "L1": gen_L1_tweak,
    "L2": gen_L2_rephrase,
    "L3": gen_L3_65pct,
    "L4": gen_L4_40pct,
}

LEVEL_SPEC = {
    "L0": {"expected_dup": True,  "target_sim": 1.0,  "method": "high_similarity"},
    "L1": {"expected_dup": True,  "target_sim": 0.90, "method": "high_similarity"},
    "L2": {"expected_dup": True,  "target_sim": 0.78, "method": "qwen_confirmed"},
    "L3": {"expected_dup": True,  "target_sim": 0.65, "method": "qwen_confirmed"},
    "L4": {"expected_dup": False, "target_sim": 0.40, "method": "low_similarity"},
}


# ── isolated dedup: one pair per bucket ────────────────────────────────

async def dedup_single_pair(
    original_row: dict,
    variant_row: dict,
    prefilter,
) -> dict:
    """对单个 (original, variant) 对执行去重判定。

    Returns:
        {
            "level": str,
            "is_dup": bool,
            "method": str,       # high_similarity | qwen_confirmed | qwen_rejected | qwen_unavailable_* | low_similarity
            "title_similarity": float,
            "original_title": str,
            "variant_title": str,
        }
    """
    title_a = str(_pick(original_row, "title", "新闻标题", "标题") or "")
    title_b = str(_pick(variant_row, "title", "新闻标题", "标题") or "")
    ratio = _approx_sim(title_a, title_b)

    level = variant_row.get("_inject_level", "?")

    result = {
        "level": level,
        "title_similarity": round(ratio, 4),
        "original_title": title_a[:80],
        "variant_title": title_b[:80],
    }

    if ratio > 0.85:
        result["is_dup"] = True
        result["method"] = "high_similarity"
    elif ratio > 0.5 and prefilter is not None:
        t0 = time.perf_counter()
        qwen_result = prefilter.check_semantic_duplicate(title_a, title_b)
        elapsed = (time.perf_counter() - t0) * 1000
        if qwen_result is True:
            result["is_dup"] = True
            result["method"] = "qwen_confirmed"
        elif qwen_result is False:
            result["is_dup"] = False
            result["method"] = "qwen_rejected"
        else:
            # Qwen unavailable → fallback
            is_dup = ratio > 0.75
            result["is_dup"] = is_dup
            result["method"] = "qwen_unavailable_fallback" if is_dup else "qwen_unavailable_keep"
        result["qwen_ms"] = round(elapsed, 1)
    else:
        result["is_dup"] = False
        result["method"] = "low_similarity"

    return result


# ── data collection ────────────────────────────────────────────────────

async def collect_seeds(count: int) -> list[dict]:
    """Collect real news to use as seeds."""
    import akshare as ak
    results: list[dict] = []

    async def _fetch(label, func, ch):
        try:
            df = await asyncio.to_thread(func)
            if df is None or df.empty:
                return []
            recs = df.to_dict("records")
            for rec in recs:
                rec["source_channel"] = ch
                if "title" not in rec:
                    rec["title"] = _pick(rec, "标题", "title", "新闻标题") or ""
                if "content" not in rec:
                    rec["content"] = _pick(rec, "内容", "content", "新闻内容", "摘要") or ""
                if ch == "akshare_sina":
                    rec["title"] = str(rec.get("内容", ""))[:40]
            return [dict(r) for r in recs if _pick(r, "标题", "title") and len(str(_pick(r, "标题", "title") or "")) >= 25]
        except Exception as exc:
            logger.warning("%s failed: %s", label, exc)
            return []

    sources = [
        ("东方财富", ak.stock_info_global_em, "akshare_em"),
        ("新浪", ak.stock_info_global_sina, "akshare_sina"),
        ("同花顺", ak.stock_info_global_ths, "akshare_ths"),
        ("富途", ak.stock_info_global_futu, "akshare_futu"),
    ]
    tasks = [_fetch(label, func, ch) for label, func, ch in sources]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    seen = set()
    for item in gathered:
        if isinstance(item, list):
            for r in item:
                key = hashlib.sha1(str(_pick(r, "标题", "title", "") or "").encode()).hexdigest()
                if key not in seen:
                    seen.add(key)
                    results.append(r)

    # Pick richest source
    random.shuffle(results)
    # Prefer items with longer content
    results.sort(key=lambda r: -len(str(_pick(r, "内容", "content", "摘要") or "")))
    return results[:count]


# ── main test ──────────────────────────────────────────────────────────

async def run_test(per_level: int = 10) -> dict:
    print(f"\n{'='*70}")
    print(f"Qwen 1.5B 去重判定 — 分级注入测试 ({per_level}对/级)")
    print(f"{'='*70}")

    # Phase 1: Collect seeds
    print("\n[1] 采集真实新闻标题作为种子...")
    seeds = await collect_seeds(per_level)
    print(f"  获取 {len(seeds)} 条种子 (>25字标题)")
    for i, s in enumerate(seeds[:3]):
        title = _pick(s, "标题", "title", "") or ""
        print(f"    [{i}] {title[:60]}")

    # Phase 2: Init Qwen prefilter
    print("\n[2] 初始化 Qwen prefilter...")
    from stock_processing_service.application.services.news_prefilter import (
        NewsPreFilterAdapter,
    )
    prefilter = NewsPreFilterAdapter(enabled=True, mode="rule_prompt")
    qwen_ready = prefilter._ensure_qwen_ready()
    print(f"  Qwen ready: {qwen_ready}")
    if not qwen_ready:
        print("  WARNING: Qwen 不可用，无法测试灰区判定！")
        return {}

    # Phase 3: Generate variants & run dedup
    print(f"\n[3] 生成变体 + 执行去重 ({per_level * 5} 对)...")

    all_results: list[dict] = []
    for level in ["L0", "L1", "L2", "L3", "L4"]:
        gen = GENERATORS[level]
        spec = LEVEL_SPEC[level]
        level_results = []

        for i, seed in enumerate(seeds):
            seed_title = _pick(seed, "标题", "title", "") or ""
            seed_content = _pick(seed, "内容", "content", "摘要") or ""

            # Original with same unique tag as variant
            tag = _unique_tag(i)
            original = {
                "title": f"{tag} {seed_title}",
                "content": seed_content,
                "source_channel": "seed_original",
                "_pair_tag": tag,
            }
            variant = gen(seed_title, seed_content, i)

            result = await dedup_single_pair(original, variant, prefilter)
            result["pair_id"] = f"{level}_{i}"
            level_results.append(result)
            all_results.append(result)

        # Per-level stats
        detected = sum(1 for r in level_results if r["is_dup"])
        methods: dict[str, int] = {}
        qwen_ms_total = 0.0
        qwen_count = 0
        for r in level_results:
            m = r.get("method", "?")
            methods[m] = methods.get(m, 0) + 1
            if "qwen" in m:
                qwen_ms_total += r.get("qwen_ms", 0)
                qwen_count += 1

        avg_sim = sum(r["title_similarity"] for r in level_results) / len(level_results)
        expected = "dup" if spec["expected_dup"] else "distinct"
        status = "PASS" if (spec["expected_dup"] and detected == per_level) or (not spec["expected_dup"] and detected == 0) else "FAIL"
        qwen_info = f" | qwen={qwen_count} calls, avg={qwen_ms_total/max(qwen_count,1):.0f}ms" if qwen_count else ""
        print(f"  {level} [{status}] expect={expected} | detected={detected}/{per_level} "
              f"| avg_sim={avg_sim:.3f} | methods={methods}{qwen_info}")

        # Show sample
        if level_results:
            r = level_results[0]
            print(f"    sample: sim={r['title_similarity']:.3f} method={r['method']}")
            print(f"      orig: {r['original_title'][:70]}")
            print(f"      var:  {r['variant_title'][:70]}")

        if status == "FAIL":
            for r in level_results[:3]:
                if (spec["expected_dup"] and not r["is_dup"]) or (not spec["expected_dup"] and r["is_dup"]):
                    print(f"    FAIL: sim={r['title_similarity']:.3f} method={r['method']}")
                    print(f"      orig: {r['original_title'][:70]}")
                    print(f"      var:  {r['variant_title'][:70]}")

    # Phase 4: Summary
    total = len(all_results)
    correct = sum(1 for r in all_results
                  if LEVEL_SPEC[r["level"]]["expected_dup"] == r["is_dup"])
    all_methods: dict[str, int] = {}
    total_qwen_ms = 0.0
    total_qwen = 0
    for r in all_results:
        m = r.get("method", "?")
        all_methods[m] = all_methods.get(m, 0) + 1
        if "qwen" in m:
            total_qwen_ms += r.get("qwen_ms", 0)
            total_qwen += 1

    print(f"\n{'='*70}")
    print(f"总结")
    print(f"{'='*70}")
    print(f"  总对数:     {total}")
    print(f"  正确判定:   {correct}/{total} ({correct/max(total,1)*100:.1f}%)")
    print(f"  判定方式:   {all_methods}")
    print(f"  Qwen 调用:  {total_qwen} 次, avg={total_qwen_ms/max(total_qwen,1):.0f}ms")
    print(f"  Qwen 覆盖:  {'✓ L2+L3 灰区已验证' if total_qwen >= per_level * 2 else '✗ 未充分覆盖'}")

    # Per-level accuracy
    for level in ["L0", "L1", "L2", "L3", "L4"]:
        lr = [r for r in all_results if r["level"] == level]
        spec = LEVEL_SPEC[level]
        ok = sum(1 for r in lr if r["is_dup"] == spec["expected_dup"])
        methods = {}
        for r in lr:
            m = r.get("method", "?")
            methods[m] = methods.get(m, 0) + 1
        expected_method = spec["method"]
        match = "✓" if methods.get(expected_method, 0) >= len(lr) * 0.8 else f"✗ (got {methods})"
        print(f"  {level}: {ok}/{len(lr)} correct, expected_method={expected_method} {match}")

    return {"results": all_results, "summary": {"total": total, "correct": correct}}


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-level", type=int, default=10)
    args = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(run_test(per_level=args.per_level))


if __name__ == "__main__":
    main()
