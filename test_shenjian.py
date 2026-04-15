#!/usr/bin/env python3
import asyncio
import sys
from datetime import date
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder

async def main():
    test_date = date(2026, 4, 7)
    builder = EnhancedCandidateBuilder()
    try:
        print(f"开始构建 {test_date} 的弱转强候选池 (增强版)...")
        # 获取基础候选输入
        rows = await builder._fetch_candidate_inputs(test_date)
        print(f"基础输入行数: {len(rows)}")
        # 查找神剑股份的行
        shenjian_row = None
        for row in rows:
            stock_id = row.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                shenjian_row = row
                break
        if shenjian_row is None:
            print("❌ 神剑股份不在基础输入行中")
            # 打印前几个行看看
            for i, row in enumerate(rows[:5]):
                print(f"Row {i}: stock_id={row.get('stock_id')}, rank_order={row.get('rank_order')}, limit_up={row.get('limit_up')}, is_leader={row.get('is_leader')}, subject_key={row.get('subject_key')}")
            return

        print("✅ 神剑股份在基础输入行中")
        print("行数据:")
        for key, value in shenjian_row.items():
            print(f"  {key}: {value}")

        # 获取周期特征
        subject_key = str(shenjian_row.get("subject_key") or "")
        print(f"主题KEY: {subject_key}")
        cycle_features = await builder.fetch_cycle_features(test_date, subject_key)
        print("周期特征:")
        print(f"  mainline_alive: {cycle_features.mainline_alive}")
        print(f"  mainline_strength_score: {cycle_features.mainline_strength_score}")
        print(f"  cycle_state: {cycle_features.cycle_state}")
        print(f"  fade_watch: {cycle_features.fade_watch}")
        print(f"  fade_confirmed: {cycle_features.fade_confirmed}")

        # 构建增强候选
        next_day = await builder.resolve_next_trade_date(test_date)
        candidate = builder._to_enhanced_candidate(shenjian_row, test_date, next_day, cycle_features)
        if candidate is None:
            print("❌ 增强候选构建返回 None (被过滤)")
            # 尝试用父类方法看看是否被过滤
            from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder
            parent_builder = WeakToStrongCandidateBuilder()
            parent_candidate = parent_builder._to_candidate(shenjian_row, test_date, next_day)
            if parent_candidate is None:
                print("父类方法也返回 None，说明基础条件不满足")
                # 手动检查条件
                pct_chg = float(shenjian_row.get("pct_chg") or 0.0)
                is_leader = bool(shenjian_row.get("is_leader") or False)
                limit_up = bool(shenjian_row.get("limit_up") or False)
                rank_order = int(shenjian_row.get("rank_order") or 999)
                recent_limit_up_count = int(shenjian_row.get("recent_limit_up_count") or 0)
                prev_day_pct = float(shenjian_row.get("prev_day_pct_chg") or 0.0)
                prev_day_limit_up = bool(shenjian_row.get("prev_day_limit_up") or False)
                stage = str(shenjian_row.get("primary_cycle_stage") or "").lower()
                action_bias = str(shenjian_row.get("action_bias") or "")
                is_divergence = bool(shenjian_row.get("is_divergence") or False)
                is_rebound = bool(shenjian_row.get("is_rebound") or False)
                is_fermentation = bool(shenjian_row.get("is_fermentation") or False)
                is_fade = bool(shenjian_row.get("is_fade") or False)

                print("检查强背景条件:")
                strong_background = (is_leader or limit_up or recent_limit_up_count >= 2 or rank_order <= 3)
                print(f"  is_leader={is_leader}, limit_up={limit_up}, recent_limit_up_count={recent_limit_up_count}, rank_order={rank_order}")
                print(f"  strong_background={strong_background}")
                if not strong_background:
                    print("  ❌ 强背景条件失败")

                print("检查修复窗口条件:")
                repair_window = (("弱转强" in action_bias) or stage in {"divergence", "rebound", "fermentation", "分歧", "回流", "发酵", "启动"} or is_divergence or is_rebound or is_fermentation)
                if is_fade:
                    repair_window = False
                print(f"  action_bias={action_bias}, stage={stage}, is_divergence={is_divergence}, is_rebound={is_rebound}, is_fermentation={is_fermentation}, is_fade={is_fade}")
                print(f"  repair_window={repair_window}")
                if not repair_window:
                    print("  ❌ 修复窗口条件失败")
            else:
                print("父类方法返回候选，说明增强构建中有其他过滤")
            await parent_builder.close()
        else:
            print("✅ 神剑股份入选候选池!")
            print(f"   股票: {candidate.get('stock_name')} ({candidate.get('stock_id')})")
            print(f"   主题: {candidate.get('subject_key')} ({candidate.get('theme_name')})")
            print(f"   准入类型: {candidate.get('pool_entry_type', 'unknown')}")
            print(f"   周期状态: {candidate.get('cycle_state')}, 退潮确认: {candidate.get('fade_confirmed')}")
            print(f"   主线存活: {candidate.get('mainline_alive')}, 主线强度: {candidate.get('mainline_strength_score')}")
            print(f"   候选分数: {candidate.get('candidate_score')}")

        # 仍然运行完整构建以查看整体结果
        print("\n--- 完整构建结果 ---")
        result = await builder.build_enhanced(test_date, max_formal=80, max_observe=40)
        print(f"扫描 {result.total_scanned} 只股票，插入 {result.total_inserted} 只候选")
        found = False
        for candidate in result.candidates:
            stock_id = candidate.get("stock_id")
            if stock_id == "002361" or stock_id == "002361.SZ":
                found = True
                print(f"✅ 神剑股份入选候选池 (完整构建)!")
                break
        if not found:
            print(f"❌ 神剑股份未入选候选池 (完整构建)")
            print("前10个候选:")
            for i, candidate in enumerate(result.candidates[:10], 1):
                print(f"{i}. {candidate.get('stock_id')} {candidate.get('stock_name')} - {candidate.get('theme_name')} - {candidate.get('pool_entry_type')} - score:{candidate.get('candidate_score')}")
    finally:
        await builder.close()

if __name__ == "__main__":
    asyncio.run(main())
