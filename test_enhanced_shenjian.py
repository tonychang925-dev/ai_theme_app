#!/usr/bin/env python3
import asyncio
import sys
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock
import asyncpg

from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder, CycleFeatureInputs

async def main():
    test_date = date(2026, 4, 7)
    builder = EnhancedCandidateBuilder()

    # Mock row data matching the SQL columns
    # From test_shenjian_query.py output
    mock_row = {
        "stock_code": "002361",
        "stock_id": "002361",
        "stock_name": "神剑股份",
        "subject_key": "9062832",
        "theme_name": "安徽商业航天",
        "rank_order": 12,
        "pct_chg": -3.1100,
        "limit_up": False,
        "is_leader": False,
        "primary_cycle_stage": "fade",
        "action_bias": "放弃",
        "is_divergence": False,
        "is_rebound": False,
        "is_fermentation": False,
        "is_fade": True,
        "is_main_theme": False,
        "recent_limit_up_count": 4,  # from earlier analysis
        "prev_day_pct_chg": None,  # unknown
        "prev_day_limit_up": False,
    }

    # Convert dict to asyncpg.Record-like object
    # We'll create a simple class that implements get()
    class MockRecord:
        def __init__(self, data):
            self._data = data
        def get(self, key, default=None):
            return self._data.get(key, default)
        def __getitem__(self, key):
            return self._data[key]
        def keys(self):
            return self._data.keys()
        def items(self):
            return self._data.items()

    mock_record = MockRecord(mock_row)

    # Mock _fetch_candidate_inputs to return single row
    async def mock_fetch(trade_date):
        return [mock_record]
    builder._fetch_candidate_inputs = mock_fetch

    # Mock fetch_cycle_features to return V2 features
    async def mock_fetch_cycle(trade_date, subject_key):
        # Return CycleFeatureInputs matching V2 data
        return CycleFeatureInputs(
            subject_key=subject_key,
            trade_date=trade_date,
            mainline_alive=False,
            mainline_strength_score=18.0,
            cycle_state="fade_watch",
            fade_watch=True,
            fade_confirmed=False,
            previous_cycle_state=None
        )
    builder.fetch_cycle_features = mock_fetch_cycle

    # Mock resolve_next_trade_date to return next day
    async def mock_resolve(trade_date):
        return trade_date + timedelta(days=1)
    builder.resolve_next_trade_date = mock_resolve

    # Mock _replace_enhanced_candidates to avoid DB operations
    async def mock_replace(next_trade_date, candidates):
        # Just return count of candidates as inserted
        return len(candidates)
    builder._replace_enhanced_candidates = mock_replace

    # Mock close to avoid pool close errors
    async def mock_close():
        pass
    builder.close = mock_close

    # Ensure pool is not used elsewhere
    builder.pool = None
    builder._ensure_pool = AsyncMock(return_value=None)

    print(f"Testing enhanced candidate builder for {test_date} with Shenjian row...")
    try:
        result = await builder.build_enhanced(test_date, max_formal=80, max_observe=40)
        print(f"Total scanned: {result.total_scanned}")
        print(f"Total inserted: {result.total_inserted}")
        print(f"Candidates count: {len(result.candidates)}")

        # Print all candidates (should be just Shenjian)
        for i, candidate in enumerate(result.candidates, 1):
            print(f"✅ 神剑股份入选候选池!")
            print(f"   股票: {candidate.get('stock_name')} ({candidate.get('stock_id')})")
            print(f"   主题: {candidate.get('subject_key')} ({candidate.get('theme_name')})")
            print(f"   周期状态: {candidate.get('cycle_state')}, 退潮确认: {candidate.get('fade_confirmed')}")
            print(f"   准入类型: {candidate.get('pool_entry_type', 'unknown')}")
            print(f"   支撑位类型: {candidate.get('support_type')}, 支撑强度: {candidate.get('support_strength')}")
            # Parse evidence_json
            evidence_json = candidate.get("evidence_json", "{}")
            import json
            evidence = json.loads(evidence_json) if isinstance(evidence_json, str) else evidence_json
            enhanced = evidence.get("enhanced_features", {})
            print(f"   强势背景评分: {enhanced.get('strong_background_score', 'N/A')}")
            print(f"   修复窗口评分: {enhanced.get('repair_window_score', 'N/A')}")
            print(f"   主线存活: {enhanced.get('mainline_alive', 'N/A')}")
            print(f"   主线强度评分: {enhanced.get('mainline_strength_score', 'N/A')}")
            print(f"   修复窗口阈值: {enhanced.get('thresholds', {}).get('repair_window', 'N/A')}")
            print(f"   观察阈值: {enhanced.get('thresholds', {}).get('observe', 'N/A')}")
    except Exception as e:
        print(f"Error during build: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())