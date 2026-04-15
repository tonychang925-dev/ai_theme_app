#!/usr/bin/env python3
"""
增强版候选构建器端到端测试

测试完整流程：
1. 获取候选输入
2. 计算周期特征
3. 计算增强评分
4. 确定准入类型
5. 对比原始构建器结果

测试后会清理测试数据
"""

import asyncio
import sys
import os
import json
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder
from stock_service.config import StockServiceConfig
import asyncpg


class EndToEndTester:
    def __init__(self):
        self.config = StockServiceConfig()
        self.test_date = date(2026, 4, 13)  # 使用今天的日期
        self.test_next_date = None

    async def setup(self):
        """设置测试环境"""
        print("🔧 设置测试环境...")
        self.original_builder = WeakToStrongCandidateBuilder()
        self.enhanced_builder = EnhancedCandidateBuilder()

        # 确定下一个交易日
        self.test_next_date = await self.original_builder.resolve_next_trade_date(self.test_date)
        print(f"📅 测试日期: {self.test_date}, 下一个交易日: {self.test_next_date}")

        # 清理之前的测试数据（如果有）
        await self.cleanup_test_data()

    async def cleanup_test_data(self):
        """清理测试数据"""
        pool = await self.enhanced_builder._ensure_pool()
        async with pool.acquire() as conn:
            # 删除测试日期的候选
            delete_sql = """
            DELETE FROM weak_to_strong_candidate_pool
            WHERE trade_date = $1 OR next_trade_date = $1
            """
            deleted = await conn.execute(delete_sql, self.test_date)
            if deleted.endswith("0"):
                print("   ✅ 无现有测试数据需要清理")
            else:
                print(f"   🗑️  清理了 {deleted.split()[1]} 条测试数据")

    async def run_original_builder(self) -> Dict[str, Any]:
        """运行原始构建器"""
        print("\n🔍 运行原始构建器...")
        try:
            result = await self.original_builder.build(
                self.test_date,
                next_trade_date=self.test_next_date,
                max_candidates=50
            )

            print(f"   📊 扫描股票: {result.total_scanned}")
            print(f"   📊 候选数量: {len(result.candidates)}")
            print(f"   📊 插入数量: {result.total_inserted}")

            # 分析候选特征
            if result.candidates:
                sample = result.candidates[0]
                print(f"   🧪 样本候选: {sample.get('stock_name')}({sample.get('stock_id')})")
                print(f"      类型: {sample.get('candidate_type')}, 评分: {sample.get('candidate_score')}")

            return {
                "result": result,
                "candidates": result.candidates,
                "count": len(result.candidates)
            }
        finally:
            await self.original_builder.close()

    async def run_enhanced_builder(self) -> Dict[str, Any]:
        """运行增强构建器"""
        print("\n🚀 运行增强构建器...")
        try:
            # 使用增强版构建
            result = await self.enhanced_builder.build_enhanced(
                self.test_date,
                next_trade_date=self.test_next_date,
                max_formal=35,  # 70% of 50
                max_observe=15   # 30% of 50
            )

            # 分类统计
            formal_candidates = [c for c in result.candidates if c.get("pool_entry_type") == "formal"]
            observe_candidates = [c for c in result.candidates if c.get("pool_entry_type") == "observe_only"]

            print(f"   📊 扫描股票: {result.total_scanned}")
            print(f"   📊 候选总数: {len(result.candidates)}")
            print(f"   📊 正式候选: {len(formal_candidates)}")
            print(f"   📊 观察候选: {len(observe_candidates)}")
            print(f"   📊 插入数量: {result.total_inserted}")

            # 分析增强特征
            if result.candidates:
                sample = result.candidates[0]
                print(f"   🧪 样本候选: {sample.get('stock_name')}({sample.get('stock_id')})")
                print(f"      类型: {sample.get('pool_entry_type')}, 评分: {sample.get('candidate_score')}")

                # 显示增强特征
                evidence = json.loads(sample.get("evidence_json", "{}"))
                enhanced = evidence.get("enhanced_features", {})
                if enhanced:
                    print(f"      强势背景评分: {enhanced.get('strong_background_score', 0):.1f}")
                    print(f"      修复窗口评分: {enhanced.get('repair_window_score', 0):.1f}")
                    print(f"      主线存活: {enhanced.get('mainline_alive', False)}")

            return {
                "result": result,
                "candidates": result.candidates,
                "formal_count": len(formal_candidates),
                "observe_count": len(observe_candidates),
                "total_count": len(result.candidates)
            }
        finally:
            await self.enhanced_builder.close()

    async def compare_results(self, original: Dict[str, Any], enhanced: Dict[str, Any]) -> Dict[str, Any]:
        """对比结果"""
        print("\n🔀 对比分析...")

        original_ids = {c["stock_id"] for c in original.get("candidates", [])}
        enhanced_ids = {c["stock_id"] for c in enhanced.get("candidates", [])}

        common_ids = original_ids & enhanced_ids
        only_original = original_ids - enhanced_ids
        only_enhanced = enhanced_ids - original_ids

        print(f"   📊 共同候选: {len(common_ids)}")
        print(f"   📊 仅原始有: {len(only_original)}")
        print(f"   📊 仅增强有: {len(only_enhanced)}")

        if original_ids:
            overlap_ratio = len(common_ids) / len(original_ids)
            print(f"   📊 重叠比例: {overlap_ratio:.1%}")
        else:
            overlap_ratio = 0

        # 分析差异原因
        if only_original:
            print(f"\n   🔍 分析仅原始有的候选 (共{len(only_original)}个):")
            # 随机取1-2个分析
            sample_original = [c for c in original["candidates"] if c["stock_id"] in only_original][:2]
            for cand in sample_original:
                print(f"      • {cand.get('stock_name')}({cand.get('stock_id')}) - {cand.get('candidate_type')}")

        if only_enhanced:
            print(f"\n   🔍 分析仅增强有的候选 (共{len(only_enhanced)}个):")
            # 随机取1-2个分析
            sample_enhanced = [c for c in enhanced["candidates"] if c["stock_id"] in only_enhanced][:2]
            for cand in sample_enhanced:
                entry_type = cand.get("pool_entry_type", "N/A")
                evidence = json.loads(cand.get("evidence_json", "{}"))
                enhanced_feat = evidence.get("enhanced_features", {})
                bg_score = enhanced_feat.get("strong_background_score", 0)
                repair_score = enhanced_feat.get("repair_window_score", 0)
                print(f"      • {cand.get('stock_name')}({cand.get('stock_id')}) - {entry_type}")
                print(f"        评分: {cand.get('candidate_score')}, 背景: {bg_score:.1f}, 修复: {repair_score:.1f}")

        return {
            "common_count": len(common_ids),
            "only_original_count": len(only_original),
            "only_enhanced_count": len(only_enhanced),
            "overlap_ratio": overlap_ratio,
            "original_total": len(original_ids),
            "enhanced_total": len(enhanced_ids)
        }

    async def analyze_enhanced_features(self, enhanced_candidates: List[Dict[str, Any]]):
        """分析增强特征分布"""
        if not enhanced_candidates:
            return

        print("\n📊 增强特征分布分析...")

        bg_scores = []
        repair_scores = []
        strength_scores = []
        entry_types = {"formal": 0, "observe_only": 0}

        for candidate in enhanced_candidates:
            evidence_json = candidate.get("evidence_json")
            if isinstance(evidence_json, str):
                try:
                    evidence = json.loads(evidence_json)
                    enhanced = evidence.get("enhanced_features", {})

                    bg_scores.append(enhanced.get("strong_background_score", 0))
                    repair_scores.append(enhanced.get("repair_window_score", 0))
                    strength_scores.append(candidate.get("mainline_strength_score", 0))

                    entry_type = candidate.get("pool_entry_type", "formal")
                    if entry_type in entry_types:
                        entry_types[entry_type] += 1
                except:
                    continue

        if bg_scores:
            print(f"   📈 强势背景评分:")
            print(f"      平均: {sum(bg_scores)/len(bg_scores):.1f}")
            print(f"      范围: {min(bg_scores):.1f} - {max(bg_scores):.1f}")
            print(f"      阈值({self.enhanced_builder.STRONG_BACKGROUND_THRESHOLD})以上: {sum(1 for s in bg_scores if s >= self.enhanced_builder.STRONG_BACKGROUND_THRESHOLD)}")

        if repair_scores:
            print(f"   📈 修复窗口评分:")
            print(f"      平均: {sum(repair_scores)/len(repair_scores):.1f}")
            print(f"      范围: {min(repair_scores):.1f} - {max(repair_scores):.1f}")
            print(f"      阈值({self.enhanced_builder.REPAIR_WINDOW_THRESHOLD})以上: {sum(1 for s in repair_scores if s >= self.enhanced_builder.REPAIR_WINDOW_THRESHOLD)}")

        print(f"   🎯 准入类型分布:")
        print(f"      正式候选: {entry_types.get('formal', 0)}")
        print(f"      观察候选: {entry_types.get('observe_only', 0)}")

    async def run(self):
        """运行完整测试"""
        print("="*60)
        print("增强版候选构建器端到端测试")
        print("="*60)

        try:
            await self.setup()

            # 运行两个构建器
            original_result = await self.run_original_builder()
            enhanced_result = await self.run_enhanced_builder()

            # 对比分析
            comparison = await self.compare_results(original_result, enhanced_result)

            # 分析增强特征
            await self.analyze_enhanced_features(enhanced_result.get("candidates", []))

            # 评估优化效果
            print("\n" + "="*60)
            print("优化效果评估")
            print("="*60)

            original_count = comparison["original_total"]
            enhanced_total = comparison["enhanced_total"]
            enhanced_formal = enhanced_result.get("formal_count", 0)

            print(f"📈 候选数量变化:")
            print(f"   原始构建器: {original_count} 候选")
            print(f"   增强构建器: {enhanced_total} 候选 ({enhanced_formal} 正式 + {enhanced_result.get('observe_count', 0)} 观察)")

            if original_count > 0:
                change_pct = (enhanced_total - original_count) / original_count * 100
                print(f"   数量变化: {change_pct:+.1f}%")

            print(f"\n🎯 准入细化:")
            print(f"   观察流机制: {'✅ 启用' if enhanced_result.get('observe_count', 0) > 0 else '⚠ 未使用'}")

            print(f"\n🔍 硬门槛优化效果:")
            only_enhanced = comparison["only_enhanced_count"]
            if only_enhanced > 0:
                print(f"   ✅ 保留了 {only_enhanced} 个被原始硬门槛过滤的候选")
            else:
                print(f"   ⚠ 未发现被原始硬门槛过滤的候选")

            # 检查是否有数据被插入
            pool = await self.enhanced_builder._ensure_pool()
            async with pool.acquire() as conn:
                count_sql = """
                SELECT COUNT(*) FROM weak_to_strong_candidate_pool
                WHERE trade_date = $1 OR next_trade_date = $1
                """
                test_data_count = await conn.fetchval(count_sql, self.test_date)
                print(f"\n💾 测试数据检查:")
                print(f"   数据库中的测试数据: {test_data_count} 条")

            print("\n" + "="*60)
            print("✅ 端到端测试完成!")
            return True

        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


async def main():
    tester = EndToEndTester()
    success = await tester.run()

    if success:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())