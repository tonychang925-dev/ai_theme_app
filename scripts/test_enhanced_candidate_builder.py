#!/usr/bin/env python3
"""
增强版候选构建器测试脚本

用途：
- 对比原始WeakToStrongCandidateBuilder和EnhancedCandidateBuilder的表现
- 测试三级准入机制（formal, observe_only, reject）
- 验证硬门槛优化效果
- 分析优化前后候选池数量和质量变化

使用方法：
  python test_enhanced_candidate_builder.py --trade-date YYYY-MM-DD [--max-candidates 120]
"""

import sys
import asyncio
import argparse
import json
from datetime import datetime, date
from typing import Dict, List, Any
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root))

from stock_service.services.weak_to_strong_candidate_builder import WeakToStrongCandidateBuilder
from stock_service.services.enhanced_candidate_builder import EnhancedCandidateBuilder


class CandidateBuilderTester:
    """候选构建器对比测试器"""

    def __init__(self):
        self.original_builder = WeakToStrongCandidateBuilder()
        self.enhanced_builder = EnhancedCandidateBuilder()

    async def test_original_builder(self, trade_date: date,
                                   next_trade_date: date = None,
                                   max_candidates: int = 120) -> Dict[str, Any]:
        """测试原始构建器"""
        try:
            result = await self.original_builder.build(
                trade_date,
                next_trade_date=next_trade_date,
                max_candidates=max_candidates
            )

            return {
                "total_scanned": result.total_scanned,
                "total_inserted": result.total_inserted,
                "candidate_count": len(result.candidates),
                "candidates": result.candidates[:20],  # 只取前20条作为样本
                "builder_type": "original",
                "rule_version": "weak_to_strong_candidate.v1"
            }
        finally:
            await self.original_builder.close()

    async def test_enhanced_builder(self, trade_date: date,
                                   next_trade_date: date = None,
                                   max_formal: int = 80,
                                   max_observe: int = 40) -> Dict[str, Any]:
        """测试增强构建器"""
        try:
            result = await self.enhanced_builder.build_enhanced(
                trade_date,
                next_trade_date=next_trade_date,
                max_formal=max_formal,
                max_observe=max_observe
            )

            # 分类统计
            formal_candidates = [c for c in result.candidates if c.get("pool_entry_type") == "formal"]
            observe_candidates = [c for c in result.candidates if c.get("pool_entry_type") == "observe_only"]

            return {
                "total_scanned": result.total_scanned,
                "total_inserted": result.total_inserted,
                "total_candidates": len(result.candidates),
                "formal_candidates": len(formal_candidates),
                "observe_candidates": len(observe_candidates),
                "candidates": result.candidates[:30],  # 多取一些，因为要展示分类
                "builder_type": "enhanced",
                "rule_version": EnhancedCandidateBuilder.ENHANCED_RULE_VERSION
            }
        finally:
            await self.enhanced_builder.close()

    async def compare_builders(self, trade_date: date,
                              max_candidates: int = 120) -> Dict[str, Any]:
        """对比两个构建器的结果"""
        next_trade_date = await self.original_builder.resolve_next_trade_date(trade_date)

        # 运行两个构建器
        original_result = await self.test_original_builder(
            trade_date, next_trade_date, max_candidates
        )

        # 增强版：保持总候选数相同，70%正式，30%观察
        max_formal = int(max_candidates * 0.7)
        max_observe = max_candidates - max_formal

        enhanced_result = await self.test_enhanced_builder(
            trade_date, next_trade_date, max_formal, max_observe
        )

        # 分析差异
        original_ids = {c["stock_id"] for c in original_result.get("candidates", [])}
        enhanced_ids = {c["stock_id"] for c in enhanced_result.get("candidates", [])}

        common_ids = original_ids & enhanced_ids
        only_in_original = original_ids - enhanced_ids
        only_in_enhanced = enhanced_ids - original_ids

        return {
            "trade_date": trade_date.isoformat(),
            "next_trade_date": next_trade_date.isoformat(),
            "original_builder": original_result,
            "enhanced_builder": enhanced_result,
            "comparison": {
                "total_candidates_original": original_result["candidate_count"],
                "total_candidates_enhanced": enhanced_result["total_candidates"],
                "common_candidates": len(common_ids),
                "only_in_original": len(only_in_original),
                "only_in_enhanced": len(only_in_enhanced),
                "formal_candidates": enhanced_result["formal_candidates"],
                "observe_candidates": enhanced_result["observe_candidates"],
                "candidate_overlap_ratio": len(common_ids) / max(len(original_ids), 1)
            }
        }

    async def analyze_enhanced_features(self, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析增强特征分布"""
        if not candidates:
            return {}

        # 收集评分数据
        bg_scores = []
        repair_scores = []
        strength_scores = []
        entry_types = {"formal": 0, "observe_only": 0}

        for candidate in candidates:
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

        def compute_stats(scores):
            if not scores:
                return {}
            return {
                "min": min(scores),
                "max": max(scores),
                "avg": sum(scores) / len(scores),
                "count": len(scores)
            }

        return {
            "strong_background_score": compute_stats(bg_scores),
            "repair_window_score": compute_stats(repair_scores),
            "mainline_strength_score": compute_stats(strength_scores),
            "entry_type_distribution": entry_types,
            "total_candidates_analyzed": len(candidates)
        }


async def main():
    parser = argparse.ArgumentParser(description="增强版候选构建器测试")
    parser.add_argument(
        "--trade-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=date.today(),
        help="交易日 (格式: YYYY-MM-DD，默认今天)"
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=120,
        help="最大候选数 (默认: 120)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="输出JSON文件路径 (可选)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出详细信息"
    )
    args = parser.parse_args()

    print("增强版候选构建器对比测试")
    print(f"交易日: {args.trade_date}")
    print(f"最大候选数: {args.max_candidates}")
    print()

    tester = CandidateBuilderTester()

    try:
        # 对比测试
        print("🔍 运行对比测试...")
        comparison_result = await tester.compare_builders(args.trade_date, args.max_candidates)

        # 分析增强特征
        print("📊 分析增强特征...")
        enhanced_candidates = comparison_result["enhanced_builder"]["candidates"]
        feature_analysis = await tester.analyze_enhanced_features(enhanced_candidates)
        comparison_result["feature_analysis"] = feature_analysis

        # 打印结果
        print("\n" + "="*60)
        print("对比测试结果")
        print("="*60)

        original = comparison_result["original_builder"]
        enhanced = comparison_result["enhanced_builder"]
        comp = comparison_result["comparison"]

        print(f"📈 原始构建器:")
        print(f"   • 扫描股票: {original['total_scanned']}")
        print(f"   • 候选数量: {original['candidate_count']}")
        print(f"   • 规则版本: {original['rule_version']}")

        print(f"\n🚀 增强构建器:")
        print(f"   • 扫描股票: {enhanced['total_scanned']}")
        print(f"   • 候选总数: {enhanced['total_candidates']}")
        print(f"   • 正式候选: {enhanced['formal_candidates']}")
        print(f"   • 观察候选: {enhanced['observe_candidates']}")
        print(f"   • 规则版本: {enhanced['rule_version']}")

        print(f"\n🔀 对比分析:")
        print(f"   • 共同候选: {comp['common_candidates']}")
        print(f"   • 仅原始有: {comp['only_in_original']}")
        print(f"   • 仅增强有: {comp['only_in_enhanced']}")
        print(f"   • 重叠比例: {comp['candidate_overlap_ratio']:.1%}")

        print(f"\n📊 特征分析:")
        if feature_analysis:
            bg_stats = feature_analysis.get("strong_background_score", {})
            repair_stats = feature_analysis.get("repair_window_score", {})
            entry_dist = feature_analysis.get("entry_type_distribution", {})

            if bg_stats.get("count", 0) > 0:
                print(f"   • 强势背景评分: {bg_stats['avg']:.1f} (范围: {bg_stats['min']:.1f}-{bg_stats['max']:.1f})")
            if repair_stats.get("count", 0) > 0:
                print(f"   • 修复窗口评分: {repair_stats['avg']:.1f} (范围: {repair_stats['min']:.1f}-{repair_stats['max']:.1f})")

            print(f"   • 准入类型: {entry_dist.get('formal', 0)}正式, {entry_dist.get('observe_only', 0)}观察")

        # 样本展示
        if args.verbose and enhanced_candidates:
            print(f"\n📋 增强候选样本 (前10个):")
            for i, cand in enumerate(enhanced_candidates[:10]):
                entry_type = cand.get("pool_entry_type", "N/A")
                stock_name = cand.get("stock_name", "N/A")
                stock_id = cand.get("stock_id", "N/A")
                score = cand.get("candidate_score", 0)
                print(f"   {i+1:2d}. [{entry_type:^12}] {stock_name}({stock_id}) - 评分: {score:.2f}")

        # 保存结果
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(comparison_result, f, ensure_ascii=False, indent=2, default=str)
            print(f"\n💾 结果已保存到: {output_path}")

        print("\n" + "="*60)
        print("✅ 测试完成!")

        # 返回退出码
        if comp["total_candidates_enhanced"] == 0:
            print("⚠ 警告: 增强构建器未生成任何候选")
            return 1
        else:
            return 0

    except Exception as e:
        print(f"❌ 测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # 清理资源
        pass


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))