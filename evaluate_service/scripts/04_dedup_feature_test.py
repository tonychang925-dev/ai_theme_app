#!/usr/bin/env python3
"""
判重功能专项测试
专门测试ThemeDeduplicationEngine的效果
"""
import json
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List
import logging
from collections import defaultdict

# 修复导入问题 - 在文件顶部添加
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DeduplicationFeatureTest:
    """判重功能专项测试"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_tests": 0,
            "duplicates_detected": 0,
            "false_positives": 0,
            "false_negatives": 0,
            "test_cases": defaultdict(int)
        }
        
    async def initialize_engine(self) -> bool:
        """初始化判重引擎"""
        logger.info("🔧 初始化判重引擎...")
        
        try:
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            self.dedup_engine = ThemeDeduplicationEngine()
            
            # 获取引擎信息
            engine_info = self.dedup_engine.get_engine_info()
            logger.info(f"✅ ThemeDeduplicationEngine 初始化成功")
            logger.info(f"  同义词数量: {engine_info.get('synonym_count', 0)}")
            logger.info(f"  停用词数量: {engine_info.get('stop_word_count', 0)}")
            logger.info(f"  使用Jieba: {engine_info.get('use_jieba', False)}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 判重引擎初始化失败: {e}")
            return False
    
    def create_test_cases(self) -> List[Dict[str, Any]]:
        """创建判重测试用例"""
        test_cases = []
        
        # 1. 精确匹配测试
        test_cases.append({
            "test_id": "exact_match_001",
            "description": "精确匹配测试",
            "new_theme_name": "人工智能",
            "event_data": {
                "title": "人工智能发展规划",
                "impact_industries": ["人工智能", "信息技术"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能,机器学习", "event_count": 50}
            ],
            "expected_should_merge": True,
            "expected_match_type": "exact"
        })
        
        # 2. 同义词匹配测试
        test_cases.append({
            "test_id": "synonym_match_001",
            "description": "同义词匹配测试",
            "new_theme_name": "AI技术发展",
            "event_data": {
                "title": "AI技术新突破",
                "impact_industries": ["人工智能", "软件"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能,机器学习", "event_count": 50}
            ],
            "expected_should_merge": True,
            "expected_match_type": "exact_with_synonyms"
        })
        
        # 3. 包含关系测试
        test_cases.append({
            "test_id": "inclusion_match_001",
            "description": "包含关系测试",
            "new_theme_name": "人工智能芯片",
            "event_data": {
                "title": "人工智能芯片技术突破",
                "impact_industries": ["半导体", "人工智能"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能", "event_count": 50},
                {"id": 2, "name": "半导体芯片", "keywords": "芯片,半导体", "event_count": 30}
            ],
            "expected_should_merge": True,
            "expected_match_type": "inclusion"
        })
        
        # 4. 语义相似度测试
        test_cases.append({
            "test_id": "semantic_similarity_001",
            "description": "语义相似度测试",
            "new_theme_name": "智能机器人技术",
            "event_data": {
                "title": "智能机器人技术发展",
                "impact_industries": ["机器人", "人工智能"]
            },
            "existing_themes": [
                {"id": 1, "name": "机器人", "keywords": "工业机器人,服务机器人", "event_count": 40}
            ],
            "expected_should_merge": True,
            "expected_match_type": "semantic"
        })
        
        # 5. 不重复测试（应保持独立）
        test_cases.append({
            "test_id": "distinct_theme_001",
            "description": "不同题材测试",
            "new_theme_name": "新能源汽车",
            "event_data": {
                "title": "新能源汽车销量增长",
                "impact_industries": ["新能源汽车", "汽车制造"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能", "event_count": 50},
                {"id": 2, "name": "光伏发电", "keywords": "太阳能,光伏", "event_count": 30}
            ],
            "expected_should_merge": False,
            "expected_match_type": "distinct"
        })
        
        # 6. 从实际测试数据中提取的用例
        test_cases.append({
            "test_id": "real_world_001",
            "description": "实际AI拍摄眼镜用例",
            "new_theme_name": "AI智能眼镜",
            "event_data": {
                "title": "AI智能眼镜发布",
                "impact_industries": ["消费电子", "人工智能"]
            },
            "existing_themes": [
                {"id": 100, "name": "AI拍摄眼镜", "keywords": "AI,眼镜,拍摄", "event_count": 5},
                {"id": 101, "name": "可穿戴设备", "keywords": "智能穿戴,设备", "event_count": 20}
            ],
            "expected_should_merge": True,
            "expected_match_type": "semantic"
        })
        
        logger.info(f"📋 创建了 {len(test_cases)} 个判重测试用例")
        return test_cases
    
    async def run_single_test(self, test_case: Dict[str, Any]) -> Dict[str, Any]:
        """运行单个测试用例"""
        test_id = test_case["test_id"]
        logger.info(f"🧪 运行测试: {test_case['description']}")
        
        try:
            # 执行判重检查
            result = await self.dedup_engine.check_duplication(
                new_theme_name=test_case["new_theme_name"],
                event_data=test_case["event_data"],
                existing_themes=test_case["existing_themes"]
            )
            
            # 转换为字典以便分析
            result_dict = result.to_dict()
            
            # 验证测试结果
            expected_merge = test_case["expected_should_merge"]
            actual_merge = result_dict["should_merge"]
            
            test_passed = (expected_merge == actual_merge)
            
            test_result = {
                "test_id": test_id,
                "description": test_case["description"],
                "new_theme_name": test_case["new_theme_name"],
                "existing_themes": [t["name"] for t in test_case["existing_themes"]],
                "expected_should_merge": expected_merge,
                "actual_should_merge": actual_merge,
                "similarity_score": result_dict["similarity_score"],
                "match_type": result_dict["match_type"],
                "reason": result_dict["reason"],
                "test_passed": test_passed,
                "result_details": result_dict
            }
            
            # 更新统计
            self.stats["total_tests"] += 1
            self.stats["test_cases"][test_case["description"]] += 1
            
            if actual_merge:
                self.stats["duplicates_detected"] += 1
            
            if not test_passed:
                if expected_merge and not actual_merge:
                    self.stats["false_negatives"] += 1
                    logger.warning(f"❌ 测试失败: 应该合并但未检测到重复 (漏报)")
                elif not expected_merge and actual_merge:
                    self.stats["false_positives"] += 1
                    logger.warning(f"❌ 测试失败: 不应合并但检测到重复 (误报)")
            
            if test_passed:
                logger.info(f"✅ 测试通过: {test_case['description']}")
                if actual_merge:
                    logger.info(f"   检测到重复: {test_case['new_theme_name']} -> {result_dict.get('target_theme', {}).get('name', '未知')}")
                    logger.info(f"   相似度: {result_dict['similarity_score']:.2f}, 类型: {result_dict['match_type']}")
                else:
                    logger.info(f"   未检测到重复，可以创建新题材")
            
            return test_result
            
        except Exception as e:
            logger.error(f"❌ 测试 {test_id} 执行失败: {e}")
            
            error_result = {
                "test_id": test_id,
                "description": test_case["description"],
                "error": str(e),
                "test_passed": False
            }
            
            return error_result
    
    async def run_all_tests(self):
        """运行所有测试用例"""
        logger.info("🚀 开始判重功能专项测试...")
        
        test_cases = self.create_test_cases()
        results = []
        
        for test_case in test_cases:
            result = await self.run_single_test(test_case)
            results.append(result)
            
            # 短暂延迟
            await asyncio.sleep(0.1)
        
        return results
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析测试结果"""
        logger.info(f"📊 分析 {len(results)} 个测试结果...")
        
        # 1. 总体统计
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.get("test_passed", False))
        failed_tests = total_tests - passed_tests
        
        logger.info("📈 总体测试结果:")
        logger.info(f"  总测试数: {total_tests}")
        logger.info(f"  通过数: {passed_tests} ({passed_tests/total_tests*100:.1f}%)")
        logger.info(f"  失败数: {failed_tests} ({failed_tests/total_tests*100:.1f}%)")
        
        # 2. 判重检测统计
        logger.info("🔍 判重检测统计:")
        logger.info(f"  检测到的重复数: {self.stats['duplicates_detected']}")
        logger.info(f"  漏报数 (应该检测但未检测): {self.stats['false_negatives']}")
        logger.info(f"  误报数 (不应检测但检测): {self.stats['false_positives']}")
        
        # 3. 匹配类型分布
        match_types = defaultdict(int)
        for result in results:
            if result.get("test_passed", False) and result.get("actual_should_merge", False):
                match_type = result.get("match_type", "unknown")
                match_types[match_type] += 1
        
        if match_types:
            logger.info("🎯 匹配类型分布:")
            for match_type, count in match_types.items():
                logger.info(f"  {match_type}: {count}")
        
        # 4. 失败测试详情
        failed_results = [r for r in results if not r.get("test_passed", True)]
        if failed_results:
            logger.warning("⚠️ 失败测试详情:")
            for failed in failed_results[:3]:  # 只显示前3个失败
                logger.warning(f"  测试: {failed.get('description', '未知')}")
                logger.warning(f"    预期合并: {failed.get('expected_should_merge', 'N/A')}")
                logger.warning(f"    实际合并: {failed.get('actual_should_merge', 'N/A')}")
                if "error" in failed:
                    logger.warning(f"    错误: {failed['error']}")
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存测试结果"""
        results_dir = Path("evaluate_service/data/results/dedup_feature_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"dedup_feature_results_{timestamp}.json"
        
        output_data = {
            "metadata": {
                "test_type": "判重功能专项测试",
                "test_time": datetime.now().isoformat(),
                "test_focus": "验证ThemeDeduplicationEngine的准确性"
            },
            "statistics": self.stats,
            "test_results": results,
            "summary": {
                "total_tests": self.stats["total_tests"],
                "passed_tests": sum(1 for r in results if r.get("test_passed", False)),
                "accuracy_rate": sum(1 for r in results if r.get("test_passed", False)) / len(results) if results else 0,
                "duplicate_detection_rate": self.stats["duplicates_detected"] / self.stats["total_tests"] if self.stats["total_tests"] > 0 else 0
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file

async def main():
    """主函数"""
    print("=" * 70)
    print("🔍 判重功能专项测试")
    print("验证ThemeDeduplicationEngine的准确性")
    print("=" * 70)
    
    tester = DeduplicationFeatureTest()
    
    try:
        # 1. 初始化判重引擎
        init_success = await tester.initialize_engine()
        if not init_success:
            print("❌ 判重引擎初始化失败，无法继续测试")
            return 1
        
        # 2. 运行所有测试
        print("🚀 运行判重测试用例...")
        results = await tester.run_all_tests()
        
        # 3. 分析结果
        tester.analyze_results(results)
        
        # 4. 保存结果
        results_file = tester.save_results(results)
        
        print("\n" + "=" * 70)
        print("✅ 判重功能专项测试完成！")
        print("=" * 70)
        
        # 关键指标
        passed_tests = sum(1 for r in results if r.get("test_passed", False))
        total_tests = len(results)
        
        print(f"📊 测试结果:")
        print(f"  通过率: {passed_tests}/{total_tests} ({passed_tests/total_tests*100:.1f}%)")
        print(f"  检测到的重复: {tester.stats['duplicates_detected']}")
        print(f"  漏报数: {tester.stats['false_negatives']}")
        print(f"  误报数: {tester.stats['false_positives']}")
        
        if tester.stats['false_negatives'] > 0:
            print("\n⚠️  发现漏报问题：判重引擎可能不够敏感")
            print("建议：降低相似度阈值或增加同义词")
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())