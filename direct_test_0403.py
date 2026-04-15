#!/usr/bin/env python3
import asyncio
from datetime import date
import asyncpg
from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder

async def test():
    # Create builder
    builder = WeakToStrongCandidateBuilder()

    # Mock a row for Shenjian on April 3, 2026
    # Based on database data:
    # pct_chg: -8.9647, is_leader: False, limit_up: False, rank_order: 13
    # recent_limit_up_count: 4, prev_day_pct: 1.7059 (from April 2), prev_day_limit_up: False

    class MockRecord:
        def __init__(self, data):
            self._data = data

        def get(self, key, default=None):
            return self._data.get(key, default)

        def __getitem__(self, key):
            return self._data[key]

    row = MockRecord({
        "stock_code": "002361",
        "stock_id": "002361",
        "stock_name": "神剑股份",
        "subject_key": "9062832",
        "theme_name": "安徽商业航天",
        "rank_order": 13,
        "pct_chg": -8.9647,
        "limit_up": False,
        "is_leader": False,
        "primary_cycle_stage": "fade",
        "action_bias": "放弃",
        "is_divergence": False,
        "is_rebound": False,
        "is_fermentation": False,
        "is_fade": True,
        "is_main_theme": False,
        "recent_limit_up_count": 4,
        "prev_day_pct_chg": 1.7059,  # April 2 pct_chg
        "prev_day_limit_up": False
    })

    trade_date = date(2026, 4, 3)
    next_trade_date = date(2026, 4, 7)  # Assume next trading day

    print(f"测试神剑股份 4月3日 弱转强候选过滤")
    print("=" * 60)

    # Call _to_candidate directly
    candidate = builder._to_candidate(row, trade_date, next_trade_date)

    if candidate is None:
        print("✅ 候选被正确拒绝 (返回None)")

        # Let's manually check which filter failed
        print("\n手动检查过滤条件:")

        pct_chg = -8.9647
        is_leader = False
        limit_up = False
        rank_order = 13
        recent_limit_up_count = 4
        prev_day_pct = 1.7059
        prev_day_limit_up = False

        # 1. 强势背景检查
        strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
        print(f"  强势背景: is_leader={is_leader}, limit_up={limit_up}, recent_limit_up_count={recent_limit_up_count}>=2={recent_limit_up_count >= 2}, rank_order={rank_order}<=3={rank_order <= 3}")
        print(f"  strong_background = {strong_background}")

        # 2. 修复窗口检查 (假设原始数据)
        stage = "fade"
        action_bias = "放弃"
        is_divergence = False
        is_rebound = False
        is_fermentation = False
        is_fade = True

        repair_window = (
            ("弱转强" in action_bias)
            or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"}
            or is_divergence
            or is_rebound
            or is_fermentation
        )
        if is_fade:
            repair_window = False
        print(f"  修复窗口: action_bias={action_bias}, stage={stage}, is_fade={is_fade}")
        print(f"  repair_window = {repair_window}")

        # 3. 支撑强度检查
        support_type = builder._support_type_from_row(pct_chg, prev_day_pct)
        support_strength = builder._support_strength(pct_chg, prev_day_pct, support_type)
        print(f"  支撑类型: pct_chg={pct_chg}, prev_day_pct={prev_day_pct}")
        print(f"  support_type = {support_type}, support_strength = {support_strength}")
        print(f"  支撑强度阈值检查: support_strength >= 30.0? {support_strength >= 30.0}")

    else:
        print("❌ 候选未被拒绝")
        print(f"候选详情: {candidate}")

    await builder.close()

if __name__ == "__main__":
    asyncio.run(test())