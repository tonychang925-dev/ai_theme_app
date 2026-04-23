#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from datetime import date, datetime
import json
from pathlib import Path
import sys
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from stock_service.services.strong_stock_tracking_service import StrongStockTrackingService
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder


def _parse_date(raw: str) -> date:
    return datetime.strptime(raw, "%Y-%m-%d").date()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="弱转强主逻辑回归验收")
    parser.add_argument("--watch-date", default="2026-04-16", help="观察池非0校验交易日")
    parser.add_argument("--rebuild-watch-pool", action="store_true", help="校验前重建观察池")
    parser.add_argument("--full-build", action="store_true", help="使用全量 build() 路径（默认使用定向快速校验）")
    parser.add_argument("--guard-date", default="2026-04-15", help="固定规模/主线占比/弱定义校验日")
    parser.add_argument("--guard-min-candidates", type=int, default=10, help="固定校验：候选最小值")
    parser.add_argument("--guard-max-candidates", type=int, default=120, help="固定校验：候选最大值")
    parser.add_argument("--guard-min-mainline-ratio", type=float, default=1.0, help="固定校验：主线占比下限")
    parser.add_argument("--guard-weak-max-pct", type=float, default=-1.0, help="固定校验：弱定义上限（pct_chg 必须 <= 该值）")
    parser.add_argument("--guard-max-nonweak-ratio", type=float, default=0.0, help="固定校验：非弱样本占比上限")
    parser.add_argument("--guard-min-prior7-strong-ratio", type=float, default=1.0, help="固定校验：近7日强势门禁命中率下限")
    parser.add_argument("--guard-next-date", default="", help="固定校验日对应 next_trade_date（可选，空则自动解析）")
    parser.add_argument("--guard-date-2", default="2026-04-16", help="第二个固定校验日")
    parser.add_argument("--guard2-min-candidates", type=int, default=5, help="第二个固定校验：候选最小值")
    parser.add_argument("--guard2-max-candidates", type=int, default=80, help="第二个固定校验：候选最大值")
    parser.add_argument("--guard2-min-mainline-ratio", type=float, default=1.0, help="第二个固定校验：主线占比下限")
    parser.add_argument("--guard2-weak-max-pct", type=float, default=-1.0, help="第二个固定校验：弱定义上限")
    parser.add_argument("--guard2-max-nonweak-ratio", type=float, default=0.0, help="第二个固定校验：非弱样本占比上限")
    parser.add_argument("--guard2-min-prior7-strong-ratio", type=float, default=1.0, help="第二个固定校验：近7日强势门禁命中率下限")
    parser.add_argument("--guard2-next-date", default="2026-04-18", help="第二个固定校验日对应 next_trade_date（可选）")
    return parser.parse_args()


def _has_stock(candidates: List[Dict[str, object]], code: str) -> bool:
    for row in candidates:
        raw = str(row.get("stock_id") or "")
        stock_code = raw.split(".", 1)[0]
        if stock_code == code:
            return True
    return False


def _match_stock_rows(candidates: List[Dict[str, object]], code: str) -> List[Dict[str, object]]:
    matched: List[Dict[str, object]] = []
    for row in candidates:
        raw = str(row.get("stock_id") or "")
        stock_code = raw.split(".", 1)[0]
        if stock_code == code:
            matched.append(row)
    return matched


async def _collect_target_candidates(
    builder: WeakToStrongCandidateBuilder,
    day: date,
    stock_code: str,
    *,
    use_full_build: bool,
) -> tuple[List[Dict[str, object]], date, int]:
    if use_full_build:
        result = await builder.build(day, max_candidates=300)
        matched = _match_stock_rows(result.candidates, stock_code)
        return matched, result.next_trade_date, len(result.candidates)

    next_day = await builder.resolve_next_trade_date(day)
    rows = await builder._fetch_candidate_inputs(day)
    selected: List[Dict[str, object]] = []
    for row in rows:
        raw = str(row.get("stock_id") or "")
        code = raw.split(".", 1)[0]
        if code != stock_code:
            continue
        if not builder._quick_row_gate(row, source="static"):
            continue
        candidate = await builder._async_to_candidate(row, day, next_day)
        if candidate is not None:
            selected.append(candidate)
    selected.sort(key=lambda x: float(x.get("candidate_score") or 0.0), reverse=True)
    return selected, next_day, len(rows)


async def _check_shenjian(builder: WeakToStrongCandidateBuilder, *, use_full_build: bool) -> bool:
    cases = [
        ("2026-04-03", False),
        ("2026-04-07", True),
        ("2026-04-08", False),
    ]
    ok = True
    for raw_day, expected in cases:
        day = _parse_date(raw_day)
        matched, next_day, total = await _collect_target_candidates(
            builder, day, "002361", use_full_build=use_full_build
        )
        hit = bool(matched)
        print(
            f"[CHECK] shenjian day={day.isoformat()} next={next_day.isoformat()} "
            f"hit={hit} expected={expected} total={total}"
        )
        if hit != expected:
            ok = False
            print(f"[FAIL] shenjian_case day={day.isoformat()}")
    if ok:
        print("[PASS] shenjian_cases")
    return ok


async def _check_liande(builder: WeakToStrongCandidateBuilder, *, use_full_build: bool) -> bool:
    day = _parse_date("2026-04-15")
    matched, next_day, total = await _collect_target_candidates(
        builder, day, "605060", use_full_build=use_full_build
    )
    has_formal = any(str(row.get("pool_entry_type") or "").lower() == "formal" for row in matched)
    print(
        f"[CHECK] liande day={day.isoformat()} next={next_day.isoformat()} "
        f"matched={len(matched)} has_formal={has_formal} total={total}"
    )
    if not matched or not has_formal:
        print("[FAIL] liande_case")
        return False
    print("[PASS] liande_case")
    return True


async def _check_watch_nonzero(watch_date: date, rebuild: bool) -> bool:
    service = StrongStockTrackingService()
    try:
        if rebuild:
            seed_count = await service.seed_watch_pool(watch_date)
            refresh_count = await service.refresh_watch_pool(watch_date)
            promote_count = await service.promote_watch_candidates(watch_date)
            prune_count = await service.prune_watch_pool(watch_date)
            print(
                f"[CHECK] watch_rebuild date={watch_date.isoformat()} "
                f"seed={seed_count} refresh={refresh_count} promote={promote_count} prune={prune_count}"
            )
        rows = await service.list_screening_candidates(watch_date)
    finally:
        await service.close()
    print(f"[CHECK] watch_candidates date={watch_date.isoformat()} count={len(rows)}")
    if not rows:
        print("[FAIL] watch_candidates_zero")
        return False
    print("[PASS] watch_candidates_nonzero")
    return True


def _extract_day_pct_chg(candidate: Dict[str, object]) -> float | None:
    evidence_raw = str(candidate.get("evidence_json") or "")
    if not evidence_raw:
        return None
    try:
        payload = json.loads(evidence_raw)
    except Exception:
        return None
    value = (
        payload.get("scores", {})
        .get("breakdown", {})
        .get("entry_components", {})
        .get("day_pct_chg")
    )
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


async def _check_fixed_0415_guard(
    builder: WeakToStrongCandidateBuilder,
    *,
    guard_date: date,
    guard_next_date: date | None,
    min_candidates: int,
    max_candidates: int,
    min_mainline_ratio: float,
    weak_max_pct: float,
    max_nonweak_ratio: float,
    min_prior7_strong_ratio: float,
) -> bool:
    result = await builder.build(guard_date, next_trade_date=guard_next_date, max_candidates=500)
    candidates = result.candidates
    count = len(candidates)
    if count <= 0:
        print(
            f"[CHECK] fixed_guard date={guard_date.isoformat()} count=0 "
            f"expected_range=[{min_candidates},{max_candidates}]"
        )
        print("[FAIL] fixed_guard_empty")
        return False

    mainline_count = sum(1 for row in candidates if bool(row.get("is_main_theme") or False))
    mainline_ratio = mainline_count / count
    prior7_strong_count = sum(1 for row in candidates if int(row.get("prior7_strong_days") or 0) >= 1)
    prior7_strong_ratio = prior7_strong_count / count

    nonweak_count = 0
    missing_pct_count = 0
    for row in candidates:
        day_pct = _extract_day_pct_chg(row)
        if day_pct is None:
            missing_pct_count += 1
            nonweak_count += 1
            continue
        if day_pct > weak_max_pct:
            nonweak_count += 1
    nonweak_ratio = nonweak_count / count

    print(
        f"[CHECK] fixed_guard date={guard_date.isoformat()} count={count} "
        f"mainline_ratio={mainline_ratio:.4f} nonweak_ratio={nonweak_ratio:.4f} "
        f"prior7_strong_ratio={prior7_strong_ratio:.4f} missing_day_pct={missing_pct_count}"
    )

    ok = True
    if count < min_candidates or count > max_candidates:
        ok = False
        print(
            f"[FAIL] fixed_guard_count_out_of_range actual={count} "
            f"expected=[{min_candidates},{max_candidates}]"
        )
    if mainline_ratio < min_mainline_ratio:
        ok = False
        print(
            f"[FAIL] fixed_guard_mainline_ratio actual={mainline_ratio:.4f} "
            f"expected_min={min_mainline_ratio:.4f}"
        )
    if nonweak_ratio > max_nonweak_ratio:
        ok = False
        print(
            f"[FAIL] fixed_guard_nonweak_ratio actual={nonweak_ratio:.4f} "
            f"expected_max={max_nonweak_ratio:.4f} weak_max_pct={weak_max_pct:.2f}"
        )
    if prior7_strong_ratio < min_prior7_strong_ratio:
        ok = False
        print(
            f"[FAIL] fixed_guard_prior7_strong_ratio actual={prior7_strong_ratio:.4f} "
            f"expected_min={min_prior7_strong_ratio:.4f}"
        )
    if ok:
        print(f"[PASS] fixed_guard_{guard_date.isoformat().replace('-', '_')}")
    return ok


async def main_async() -> int:
    args = parse_args()
    watch_date = _parse_date(args.watch_date)
    guard_date = _parse_date(args.guard_date)
    guard_date_2 = _parse_date(args.guard_date_2)
    guard_next_date = _parse_date(args.guard_next_date) if str(args.guard_next_date or "").strip() else None
    guard_next_date_2 = _parse_date(args.guard2_next_date) if str(args.guard2_next_date or "").strip() else None
    builder = WeakToStrongCandidateBuilder()
    try:
        shenjian_ok = await _check_shenjian(builder, use_full_build=bool(args.full_build))
        liande_ok = await _check_liande(builder, use_full_build=bool(args.full_build))
        fixed_guard_ok = await _check_fixed_0415_guard(
            builder,
            guard_date=guard_date,
            guard_next_date=guard_next_date,
            min_candidates=int(args.guard_min_candidates),
            max_candidates=int(args.guard_max_candidates),
            min_mainline_ratio=float(args.guard_min_mainline_ratio),
            weak_max_pct=float(args.guard_weak_max_pct),
            max_nonweak_ratio=float(args.guard_max_nonweak_ratio),
            min_prior7_strong_ratio=float(args.guard_min_prior7_strong_ratio),
        )
        fixed_guard_2_ok = await _check_fixed_0415_guard(
            builder,
            guard_date=guard_date_2,
            guard_next_date=guard_next_date_2,
            min_candidates=int(args.guard2_min_candidates),
            max_candidates=int(args.guard2_max_candidates),
            min_mainline_ratio=float(args.guard2_min_mainline_ratio),
            weak_max_pct=float(args.guard2_weak_max_pct),
            max_nonweak_ratio=float(args.guard2_max_nonweak_ratio),
            min_prior7_strong_ratio=float(args.guard2_min_prior7_strong_ratio),
        )
    finally:
        await builder.close()
    watch_ok = await _check_watch_nonzero(watch_date, rebuild=args.rebuild_watch_pool)
    all_ok = shenjian_ok and liande_ok and fixed_guard_ok and fixed_guard_2_ok and watch_ok
    print(f"[SUMMARY] all_ok={all_ok}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
