#!/usr/bin/env python3
"""
多源新闻采集强化测试：可用性 / 去重率 / 去重质量 / 误杀率

每个源至少采集 100 条新闻事件。

用法:
  python test_multi_source_stress.py [--once] [--per-source 100]

输出:
  - 控制台实时进度
  - JSON 完整报告 → /tmp/multi_source_stress_report.json
"""
from __future__ import annotations

import argparse
import asyncio
import difflib
import hashlib
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

CN_TZ = timezone(timedelta(hours=8))

# ── project path ───────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

# ── source config ──────────────────────────────────────────────────────
SOURCES: dict[str, dict[str, Any]] = {
    "cls":        {"label": "财联社(CLS)",          "channel": "cls"},
    "akshare_em":  {"label": "东方财富(EastMoney)",   "channel": "akshare_em"},
    "akshare_sina":{"label": "新浪(Sina)",            "channel": "akshare_sina"},
    "akshare_ths": {"label": "同花顺(THS)",           "channel": "akshare_ths"},
    "akshare_futu":{"label": "富途(Futu)",            "channel": "akshare_futu"},
    "akshare_cctv":{"label": "CCTV新闻联播",          "channel": "akshare_cctv"},
}

SOURCE_PRIORITY = {
    "cls": 100, "akshare_em": 80, "akshare_futu": 70,
    "akshare_ths": 60, "akshare_sina": 50, "akshare_cctv": 40,
}

logger = logging.getLogger("stress_test")


# ── helpers ────────────────────────────────────────────────────────────

def _pick(row: dict, *keys: str) -> Any:
    for k in keys:
        v = row.get(k)
        if v is not None and str(v).strip() != "":
            return v
    return None


def _norm_title(s: str) -> str:
    return re.sub(r'[^\w]', '', str(s)[:30]).lower()


def _dedupe_key(row: dict) -> str:
    external_id = _pick(row, "external_id", "news_id", "id")
    if external_id:
        return hashlib.sha1(str(external_id).encode()).hexdigest()
    title = _pick(row, "title", "新闻标题", "标题") or ""
    content = _pick(row, "content", "新闻内容", "内容", "摘要") or ""
    return hashlib.sha1(f"{title}|{content}".encode()).hexdigest()


# ── data collector ─────────────────────────────────────────────────────

@dataclass
class StressStats:
    per_source: dict[str, dict] = field(default_factory=dict)
    total_fetched: int = 0
    total_raw: int = 0
    total_exact_dup: int = 0
    total_cross_dup: int = 0
    rounds: int = 0
    started_at: str = ""
    finished_at: str = ""

    # Synthetic dedup test
    synthetic_pairs: int = 0
    synthetic_detected: int = 0
    synthetic_undetected: list[dict] = field(default_factory=list)

    # Quality samples for manual review
    dedup_samples: list[dict] = field(default_factory=list)
    kept_duplicates: list[dict] = field(default_factory=list)


async def _fetch_single(label: str, func, channel: str) -> tuple[str, list[dict]]:
    """Fetch from one source, return (channel, rows)."""
    try:
        df = await asyncio.to_thread(func)
        if df is None or df.empty:
            return (channel, [])
        records = df.to_dict("records")
        for r in records:
            r["source_channel"] = channel
            if channel == "akshare_sina":
                r["title"] = str(r.get("内容", ""))[:40]
                r["publish_time"] = str(r.get("时间", ""))
                r["publish_date"] = datetime.now(CN_TZ).date().isoformat()
        return (channel, [dict(row) for row in records])
    except Exception as exc:
        logger.warning("%s fetch failed: %s", label, exc)
        return (channel, [])


async def collect_all_sources() -> list[dict]:
    """Collect from CLS (via service) + 5 direct akshare sources in parallel."""
    import akshare as ak
    results: list[dict] = []

    # CLS via existing service
    try:
        from news_crawler_service.services.news_crawler_service import get_news_crawler_service
        svc = get_news_crawler_service()
        r = await svc.crawl_news_auto(count=50, prefer_real=True)
        if r.get("status") == "success":
            for row in (r.get("response") or {}).get("news_list") or []:
                row["source_channel"] = "cls"
                results.append(row)
    except Exception as exc:
        logger.warning("CLS fetch failed: %s", exc)

    # Direct sources in parallel
    direct_sources = [
        ("东方财富", ak.stock_info_global_em, "akshare_em"),
        ("新浪",     ak.stock_info_global_sina, "akshare_sina"),
        ("同花顺",   ak.stock_info_global_ths, "akshare_ths"),
        ("富途",     ak.stock_info_global_futu, "akshare_futu"),
        ("CCTV",     ak.news_cctv, "akshare_cctv"),
    ]
    tasks = [_fetch_single(label, func, ch) for label, func, ch in direct_sources]
    gathered = await asyncio.gather(*tasks, return_exceptions=True)
    for item in gathered:
        if isinstance(item, Exception):
            continue
        ch, rows = item
        results.extend(rows)

    return results


# ── semantic dedup (same logic as collector) ────────────────────────────

async def cross_source_dedup(rows: list[dict], prefilter_adapter=None) -> tuple[list[dict], list[dict]]:
    """Cross-source semantic dedup. Returns (kept_rows, dedup_pairs_info)."""
    if len(rows) <= 1:
        return rows, []

    dedup_pairs: list[dict] = []

    # Bucket by normalized title prefix
    buckets: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        raw = (_pick(row, "title", "新闻标题", "标题")
               or _pick(row, "content", "内容", "摘要") or "")
        key = _norm_title(raw)
        buckets.setdefault(key, []).append(i)

    dup_pairs: list[tuple[int, int]] = []
    for indices in buckets.values():
        if len(indices) < 2:
            continue
        for a in range(len(indices)):
            for b in range(a + 1, len(indices)):
                ia, ib = indices[a], indices[b]
                title_a = str(_pick(rows[ia], "title", "新闻标题", "标题") or "")
                title_b = str(_pick(rows[ib], "title", "新闻标题", "标题") or "")
                if not title_a or not title_b:
                    continue

                ratio = difflib.SequenceMatcher(None, title_a, title_b).ratio()

                dup_method = "none"
                is_dup = False
                if ratio > 0.85:
                    is_dup = True
                    dup_method = "high_similarity"
                elif ratio > 0.5 and prefilter_adapter is not None:
                    result = prefilter_adapter.check_semantic_duplicate(title_a, title_b)
                    if result is True:
                        is_dup = True
                        dup_method = "qwen_confirmed"
                    elif result is None:
                        is_dup = ratio > 0.75
                        dup_method = "qwen_unavailable_fallback" if is_dup else "qwen_unavailable_keep"

                if is_dup:
                    ch_a = str(_pick(rows[ia], "source_channel") or "")
                    ch_b = str(_pick(rows[ib], "source_channel") or "")
                    pri_a = SOURCE_PRIORITY.get(ch_a, 0)
                    pri_b = SOURCE_PRIORITY.get(ch_b, 0)
                    keeper, dropped = (ia, ib) if pri_a >= pri_b else (ib, ia)

                    dedup_pairs.append({
                        "keeper_source": str(_pick(rows[keeper], "source_channel")),
                        "dropped_source": str(_pick(rows[dropped], "source_channel")),
                        "similarity": round(ratio, 4),
                        "method": dup_method,
                        "keeper_title": title_a if keeper == ia else title_b,
                        "dropped_title": title_b if dropped == ib else title_a,
                    })
                    dup_pairs.append((keeper, dropped))

    dropped_indices = {d for _, d in dup_pairs}
    kept = [r for i, r in enumerate(rows) if i not in dropped_indices]
    return kept, dedup_pairs


# ── synthetic dedup test ───────────────────────────────────────────────

def generate_synthetic_test(rows: list[dict]) -> list[dict]:
    """From real rows, generate synthetic known-duplicate and known-distinct pairs."""
    test_cases: list[dict] = []

    # Group by source for pairing
    by_source: dict[str, list[int]] = {}
    for i, row in enumerate(rows):
        ch = str(_pick(row, "source_channel") or "")
        by_source.setdefault(ch, []).append(i)

    # 1. KNOWN DUPLICATES: same row with slight title variation
    for i, row in enumerate(rows[:30]):
        title = str(_pick(row, "title", "新闻标题", "标题") or "")
        if len(title) < 10:
            continue
        # Create a variant with minor edits
        variant = dict(row)
        variant["_synth_id"] = f"dup_of_{i}"
        # Slightly modify title
        if "：" in title:
            variant["title"] = title.replace("：", ":")
        elif len(title) > 20:
            variant["title"] = title[:15] + "，" + title[15:]
        else:
            variant["title"] = title + "（快讯）"
        variant["source_channel"] = "synth_test"
        test_cases.append({
            "type": "known_duplicate",
            "original_row": dict(row),
            "variant_row": variant,
            "expected_dup": True,
        })

    # 2. KNOWN DISTINCT: pick two rows from different buckets
    distinct_titles = []
    for row in rows:
        t = str(_pick(row, "title", "新闻标题", "标题") or "")
        if len(t) > 15 and t not in distinct_titles:
            distinct_titles.append(t)
        if len(distinct_titles) >= 20:
            break

    for i in range(0, len(distinct_titles) - 1, 2):
        test_cases.append({
            "type": "known_distinct",
            "title_a": distinct_titles[i],
            "title_b": distinct_titles[i + 1],
            "expected_dup": False,
        })

    return test_cases


# ── main test ──────────────────────────────────────────────────────────

async def run_stress_test(per_source: int = 100, use_qwen: bool = False) -> StressStats:
    stats = StressStats()
    stats.started_at = datetime.now(CN_TZ).isoformat()

    # Per-source accumulators
    accum: dict[str, list[dict]] = {ch: [] for ch in SOURCES}
    all_exact_keys: set[str] = set()

    # Init prefilter adapter for Qwen access
    prefilter = None
    if use_qwen:
        try:
            from stock_processing_service.application.services.news_prefilter import (
                NewsPreFilterAdapter,
            )
            prefilter = NewsPreFilterAdapter(enabled=True, mode="rule_prompt")
            logger.info("Qwen prefilter initialized for dedup test")
        except Exception as exc:
            logger.warning("Qwen init failed, using similarity-only dedup: %s", exc)

    # ── Phase 1: Collect until each source has ≥ per_source rows ────────
    print(f"\n{'='*70}")
    print(f"Phase 1: 采集阶段 (每源目标 ≥ {per_source} 条)")
    print(f"{'='*70}")

    # Per-source unique-key tracking (for newness detection)
    per_source_keys: dict[str, set[str]] = {ch: set() for ch in SOURCES}
    stalled_rounds = 0

    max_rounds = 60
    for round_idx in range(1, max_rounds + 1):
        stats.rounds = round_idx
        rows = await collect_all_sources()
        stats.total_raw += len(rows)

        # Count per source WITH internal dedup
        source_counts: dict[str, int] = {}
        new_this_round = 0
        for r in rows:
            ch = str(_pick(r, "source_channel") or "unknown")
            if ch not in accum:
                continue
            key = _dedupe_key(r)
            source_counts[ch] = source_counts.get(ch, 0) + 1
            # Per-source exact dedup
            if key not in per_source_keys[ch]:
                per_source_keys[ch].add(key)
                accum[ch].append(r)
                new_this_round += 1
                # Also track global exact dedup
                if key in all_exact_keys:
                    stats.total_exact_dup += 1
                all_exact_keys.add(key)
            else:
                stats.total_exact_dup += 1

        # Stalled detection
        if new_this_round == 0:
            stalled_rounds += 1
        else:
            stalled_rounds = 0

        # Progress
        counts_str = " | ".join(
            f"{SOURCES[ch]['label']}: {len(accum[ch])}/{per_source}"
            for ch in SOURCES if len(accum[ch]) > 0 or ch in source_counts
        )
        this_round = " | ".join(
            f"{k}={v}" for k, v in sorted(source_counts.items())
        )
        print(f"  Round {round_idx:2d}: new={new_this_round} | {this_round}")
        print(f"    Unique: {counts_str}")

        # Check done: all sources with data have >= target, or stalled 3+ rounds
        active_sources = [ch for ch in SOURCES if len(accum[ch]) > 0]
        all_hit_target = all(len(accum[ch]) >= per_source for ch in active_sources)
        if all_hit_target:
            print(f"\n  所有活跃源均达到目标！{round_idx} 轮完成")
            break
        if stalled_rounds >= 3:
            print(f"\n  连续 {stalled_rounds} 轮无新数据，提前结束")
            break

        await asyncio.sleep(3)

    stats.total_fetched = sum(len(v) for v in accum.values())  # unique per source

    # ── Phase 2: Source availability report ─────────────────────────────
    print(f"\n{'='*70}")
    print(f"Phase 2: 源可用性报告")
    print(f"{'='*70}")

    for ch, cfg in SOURCES.items():
        count = len(accum.get(ch, []))
        available = count > 0
        pct = count / max(stats.total_fetched, 1) * 100
        status = "✓ 可用" if available else "✗ 不可用"
        print(f"  {cfg['label']:25s} | {status} | {count:4d} 条 | {pct:5.1f}%")
        stats.per_source[ch] = {
            "label": cfg["label"],
            "available": available,
            "count": count,
            "pct_of_total": round(pct, 1),
        }

    # ── Phase 3: Cross-source dedup test ────────────────────────────────
    print(f"\n{'='*70}")
    print(f"Phase 3: 跨源语义去重测试")
    print(f"{'='*70}")

    if stats.total_fetched > 0:
        all_rows = []
        for ch in SOURCES:
            all_rows.extend(accum.get(ch, []))

        kept, dedup_pairs = await cross_source_dedup(all_rows, prefilter)
        stats.total_cross_dup = len(dedup_pairs)
        cross_dup_rate = len(dedup_pairs) / max(len(all_rows), 1) * 100

        print(f"  去重前: {len(all_rows)} 条")
        print(f"  去重后: {len(kept)} 条")
        print(f"  跨源去重: {len(dedup_pairs)} 对 ({cross_dup_rate:.1f}%)")

        # Dedup method breakdown
        methods: dict[str, int] = {}
        for p in dedup_pairs:
            m = p.get("method", "unknown")
            methods[m] = methods.get(m, 0) + 1
        print(f"  去重方式分布:")
        for m, c in sorted(methods.items()):
            print(f"    {m}: {c}")

        # Save samples for manual review (max 20)
        stats.dedup_samples = dedup_pairs[:20]

        # ── Phase 3b: Which source pairs are most often deduped ─────────
        pair_counts: dict[tuple, int] = {}
        for p in dedup_pairs:
            pair = (p["keeper_source"], p["dropped_source"])
            pair_counts[pair] = pair_counts.get(pair, 0) + 1
        print(f"  高频去重对:")
        for (k, d), c in sorted(pair_counts.items(), key=lambda x: -x[1])[:10]:
            print(f"    {k} 保留 ← {d} 丢弃: {c} 对")

    # ── Phase 4: Synthetic test (false positive/negative) ───────────────
    print(f"\n{'='*70}")
    print(f"Phase 4: 误杀率/漏杀率 (合成测试)")
    print(f"{'='*70}")

    # Gather enough real data for synthetic test
    all_rows = []
    for ch in SOURCES:
        all_rows.extend(accum.get(ch, [])[:50])  # top 50 from each

    if len(all_rows) >= 20:
        test_cases = generate_synthetic_test(all_rows)
        stats.synthetic_pairs = len(test_cases)

        fp_count = 0  # false positive: distinct judged as duplicate
        fn_count = 0  # false negative: duplicate judged as distinct

        for tc in test_cases:
            if tc["type"] == "known_duplicate":
                title_a = str(_pick(tc["original_row"], "title", "新闻标题", "标题") or "")
                title_b = str(_pick(tc["variant_row"], "title", "新闻标题", "标题") or "")
                ratio = difflib.SequenceMatcher(None, title_a, title_b).ratio()

                is_dup = ratio > 0.85
                if not is_dup and ratio > 0.5 and prefilter is not None:
                    result = prefilter.check_semantic_duplicate(title_a, title_b)
                    if result is True:
                        is_dup = True
                    elif result is None:
                        is_dup = ratio > 0.75

                if not is_dup:
                    fn_count += 1
                    stats.synthetic_undetected.append({
                        "type": "false_negative",
                        "title_a": title_a[:60],
                        "title_b": title_b[:60],
                        "similarity": round(ratio, 4),
                    })

            elif tc["type"] == "known_distinct":
                ratio = difflib.SequenceMatcher(None, tc["title_a"], tc["title_b"]).ratio()
                is_dup = ratio > 0.85
                if not is_dup and ratio > 0.5 and prefilter is not None:
                    result = prefilter.check_semantic_duplicate(tc["title_a"], tc["title_b"])
                    if result is True:
                        is_dup = True
                    elif result is None:
                        is_dup = ratio > 0.75

                if is_dup:
                    fp_count += 1
                    stats.synthetic_undetected.append({
                        "type": "false_positive",
                        "title_a": tc["title_a"][:60],
                        "title_b": tc["title_b"][:60],
                        "similarity": round(ratio, 4),
                    })

        detected = stats.synthetic_pairs - fp_count - fn_count
        stats.synthetic_detected = detected

        fn_rate = fn_count / max(len([t for t in test_cases if t["type"] == "known_duplicate"]), 1) * 100
        fp_rate = fp_count / max(len([t for t in test_cases if t["type"] == "known_distinct"]), 1) * 100

        print(f"  合成测试对: {stats.synthetic_pairs}")
        print(f"  正确判定:   {detected}")
        print(f"  误杀 (FP):  {fp_count} ({fp_rate:.1f}%)")
        print(f"  漏杀 (FN):  {fn_count} ({fn_rate:.1f}%)")

        if stats.synthetic_undetected:
            print(f"\n  误判详情:")
            for u in stats.synthetic_undetected[:10]:
                print(f"    [{u['type']}] sim={u['similarity']:.3f}")
                print(f"      A: {u['title_a']}")
                print(f"      B: {u['title_b']}")

    # ── Phase 5: Final summary ──────────────────────────────────────────
    stats.finished_at = datetime.now(CN_TZ).isoformat()
    print(f"\n{'='*70}")
    print(f"Phase 5: 最终统计")
    print(f"{'='*70}")
    print(f"  采集轮次:     {stats.rounds}")
    print(f"  原始抓取:     {stats.total_raw} 条")
    print(f"  有效留存:     {stats.total_fetched} 条（去空/去序号重后）")
    print(f"  精确去重:     {stats.total_exact_dup} 条")
    print(f"  跨源语义去重: {stats.total_cross_dup} 对")
    print(f"  合成误杀率:   {fp_rate:.1f}%")
    print(f"  合成漏杀率:   {fn_rate:.1f}%")

    # Save report
    report = {
        "summary": {
            "rounds": stats.rounds,
            "total_raw": stats.total_raw,
            "total_fetched": stats.total_fetched,
            "exact_dup_count": stats.total_exact_dup,
            "cross_dup_count": stats.total_cross_dup,
            "synthetic_pairs": stats.synthetic_pairs,
            "synthetic_detected": stats.synthetic_detected,
            "false_positive_count": fp_count,
            "false_negative_count": fn_count,
        },
        "per_source": stats.per_source,
        "dedup_method_breakdown": methods,
        "dedup_pair_counts": {f"{k}→{d}": c for (k, d), c in sorted(pair_counts.items(), key=lambda x: -x[1])},
        "dedup_samples": stats.dedup_samples,
        "synthetic_errors": stats.synthetic_undetected,
        "started_at": stats.started_at,
        "finished_at": stats.finished_at,
    }
    out_path = Path("/tmp/multi_source_stress_report.json")
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"\n  完整报告: {out_path}")

    return stats


# ── CLI ────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Multi-source news stress test")
    ap.add_argument("--per-source", type=int, default=100,
                    help="Target rows per source (default 100)")
    ap.add_argument("--use-qwen", action="store_true",
                    help="Enable Qwen 1.5B semantic dedup")
    ap.add_argument("--once", action="store_true",
                    help="Single round only (no loop)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    if args.once:
        async def once():
            rows = await collect_all_sources()
            src_counts: dict[str, int] = {}
            for r in rows:
                ch = str(_pick(r, "source_channel") or "unknown")
                src_counts[ch] = src_counts.get(ch, 0) + 1
            print(f"\n总抓取: {len(rows)} 条")
            for ch, c in sorted(src_counts.items()):
                print(f"  {ch}: {c}")
            kept, pairs = await cross_source_dedup(rows)
            print(f"  去重后: {len(kept)} 条, 去重: {len(pairs)} 对")
            for p in pairs[:5]:
                print(f"    [{p['method']}] {p['keeper_source']}←{p['dropped_source']}: {p['keeper_title'][:50]}")
        asyncio.run(once())
    else:
        asyncio.run(run_stress_test(per_source=args.per_source, use_qwen=args.use_qwen))


if __name__ == "__main__":
    main()
