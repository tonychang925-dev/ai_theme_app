#!/usr/bin/env python3
"""
优化判重引擎配置测试
降低阈值，提高判重敏感度
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging
from collections import defaultdict

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class OptimizedDedupTest:
    """优化判重引擎配置测试"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_tests": 0,
            "duplicates_detected": 0,
            "test_passed": 0,
            "configurations_tested": []
        }
    
    def create_optimized_configs(self) -> List[Dict[str, Any]]:
        """创建不同的优化配置"""
        configs = []
        
        # 配置1：降低语义相似度阈值
        configs.append({
            "config_id": "config_low_threshold",
            "description": "低阈值配置 (semantic: 0.7)",
            "config": {
                "thresholds": {
                    "exact_match": 1.0,
                    "inclusion_match": 0.8,      # 降低包含阈值
                    "semantic_similarity": 0.7,  # 大幅降低语义阈值
                    "event_overlap": 0.7,
                    "auto_merge": 0.80,          # 降低自动合并阈值
                    "suggest_merge": 0.60,       # 降低建议合并阈值
                    "keep_separate": 0.4         # 降低保持独立阈值
                },
                "weights": {
                    "name_similarity": 0.4,
                    "keyword_overlap": 0.3,
                    "industry_match": 0.2,
                    "semantic_similarity": 0.1
                }
            }
        })
        
        # 配置2：调整权重，更关注行业匹配
        configs.append({
            "config_id": "config_industry_focus",
            "description": "行业焦点配置",
            "config": {
                "thresholds": {
                    "exact_match": 1.0,
                    "inclusion_match": 0.7,      # 进一步降低
                    "semantic_similarity": 0.75,
                    "event_overlap": 0.7,
                    "auto_merge": 0.75,
                    "suggest_merge": 0.55,
                    "keep_separate": 0.35
                },
                "weights": {
                    "name_similarity": 0.3,      # 降低名称权重
                    "keyword_overlap": 0.3,
                    "industry_match": 0.3,       # 提高行业权重
                    "semantic_similarity": 0.1
                }
            }
        })
        
        # 配置3：激进配置（高敏感度）
        configs.append({
            "config_id": "config_aggressive",
            "description": "激进配置 (高敏感度)",
            "config": {
                "thresholds": {
                    "exact_match": 1.0,
                    "inclusion_match": 0.6,      # 非常低的包含阈值
                    "semantic_similarity": 0.65, # 很低的语义阈值
                    "event_overlap": 0.6,
                    "auto_merge": 0.70,          # 70%就自动合并
                    "suggest_merge": 0.50,
                    "keep_separate": 0.3
                },
                "weights": {
                    "name_similarity": 0.25,
                    "keyword_overlap": 0.35,     # 提高关键词权重
                    "industry_match": 0.25,
                    "semantic_similarity": 0.15  # 提高语义权重
                }
            }
        })
        
        logger.info(f"📋 创建了 {len(configs)} 种优化配置")
        return configs
    
    def create_test_cases(self) -> List[Dict[str, Any]]:
        """创建测试用例（使用之前失败的用例）"""
        test_cases = []
        
        # 之前失败的用例
        test_cases.append({
            "test_id": "inclusion_failed_001",
            "description": "包含关系测试 - 之前失败",
            "new_theme_name": "人工智能芯片",
            "event_data": {
                "title": "人工智能芯片技术突破",
                "impact_industries": ["半导体", "人工智能"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能", "event_count": 50},
                {"id": 2, "name": "半导体芯片", "keywords": "芯片,半导体", "event_count": 30}
            ],
            "expected_should_merge": True
        })
        
        test_cases.append({
            "test_id": "semantic_failed_001",
            "description": "语义相似度测试 - 之前失败",
            "new_theme_name": "智能机器人技术",
            "event_data": {
                "title": "智能机器人技术发展",
                "impact_industries": ["机器人", "人工智能"]
            },
            "existing_themes": [
                {"id": 1, "name": "机器人", "keywords": "工业机器人,服务机器人", "event_count": 40}
            ],
            "expected_should_merge": True
        })
        
        test_cases.append({
            "test_id": "real_world_failed_001",
            "description": "实际AI拍摄眼镜用例 - 之前失败",
            "new_theme_name": "AI智能眼镜",
            "event_data": {
                "title": "AI智能眼镜发布",
                "impact_industries": ["消费电子", "人工智能"]
            },
            "existing_themes": [
                {"id": 100, "name": "AI拍摄眼镜", "keywords": "AI,眼镜,拍摄", "event_count": 5},
                {"id": 101, "name": "可穿戴设备", "keywords": "智能穿戴,设备", "event_count": 20}
            ],
            "expected_should_merge": True
        })
        
        # 添加一些边界测试
        test_cases.append({
            "test_id": "boundary_test_001",
            "description": "边界测试 - 适度相似",
            "new_theme_name": "新能源车电池",
            "event_data": {
                "title": "新能源车电池技术",
                "impact_industries": ["新能源汽车", "电池"]
            },
            "existing_themes": [
                {"id": 1, "name": "新能源汽车", "keywords": "电动车,新能源车", "event_count": 60},
                {"id": 2, "name": "锂电池", "keywords": "电池,锂电", "event_count": 45}
            ],
            "expected_should_merge": True  # 应该检测到与新能源汽车的相似
        })
        
        logger.info(f"📋 创建了 {len(test_cases)} 个测试用例")
        return test_cases
    
    async def test_configuration(self, config: Dict[str, Any], test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
        """测试特定配置"""
        from theme_service.deduplication_engine import ThemeDeduplicationEngine
        
        logger.info(f"🧪 测试配置: {config['description']}")
        
        # 使用优化配置创建引擎
        dedup_engine = ThemeDeduplicationEngine(config=config["config"])
        
        config_results = {
            "config_id": config["config_id"],
            "description": config["description"],
            "tests": [],
            "summary": {
                "total_tests": 0,
                "passed": 0,
                "duplicates_detected": 0
            }
        }
        
        for test_case in test_cases:
            try:
                result = await dedup_engine.check_duplication(
                    new_theme_name=test_case["new_theme_name"],
                    event_data=test_case["event_data"],
                    existing_themes=test_case["existing_themes"]
                )
                
                test_result = {
                    "test_id": test_case["test_id"],
                    "description": test_case["description"],
                    "new_theme_name": test_case["new_theme_name"],
                    "expected_should_merge": test_case["expected_should_merge"],
                    "actual_should_merge": result.should_merge,
                    "similarity": result.similarity_score,
                    "match_type": result.match_type,
                    "passed": (test_case["expected_should_merge"] == result.should_merge)
                }
                
                config_results["tests"].append(test_result)
                config_results["summary"]["total_tests"] += 1
                
                if test_result["passed"]:
                    config_results["summary"]["passed"] += 1
                
                if result.should_merge:
                    config_results["summary"]["duplicates_detected"] += 1
                
                logger.debug(f"    测试 {test_case['test_id']}: 预期={test_case['expected_should_merge']}, 实际={result.should_merge}, 相似度={result.similarity_score:.2f}")
                
            except Exception as e:
                logger.error(f"    测试 {test_case['test_id']} 失败: {e}")
                test_result = {
                    "test_id": test_case["test_id"],
                    "error": str(e),
                    "passed": False
                }
                config_results["tests"].append(test_result)
        
        # 计算准确率
        if config_results["summary"]["total_tests"] > 0:
            accuracy = config_results["summary"]["passed"] / config_results["summary"]["total_tests"]
        else:
            accuracy = 0
        
        config_results["summary"]["accuracy"] = accuracy
        
        logger.info(f"    配置结果: 通过={config_results['summary']['passed']}/{config_results['summary']['total_tests']}, 准确率={accuracy:.1%}")
        
        return config_results
    
    async def run_all_tests(self):
        """运行所有配置的测试"""
        logger.info("🚀 开始优化配置测试...")
        
        configs = self.create_optimized_configs()
        test_cases = self.create_test_cases()
        
        all_results = []
        
        for config in configs:
            config_results = await self.test_configuration(config, test_cases)
            all_results.append(config_results)
            
            # 更新总体统计
            self.stats["total_tests"] += config_results["summary"]["total_tests"]
            self.stats["test_passed"] += config_results["summary"]["passed"]
            self.stats["duplicates_detected"] += config_results["summary"]["duplicates_detected"]
            self.stats["configurations_tested"].append(config["config_id"])
            
            # 短暂延迟
            await asyncio.sleep(0.5)
        
        return all_results
    
    def analyze_results(self, all_results: List[Dict[str, Any]]):
        """分析所有配置的结果"""
        logger.info(f"📊 分析 {len(all_results)} 种配置的测试结果...")
        
        # 1. 找出最佳配置
        best_config = None
        best_accuracy = 0
        
        for config_results in all_results:
            accuracy = config_results["summary"]["accuracy"]
            config_id = config_results["config_id"]
            description = config_results["description"]
            
            logger.info(f"🔧 配置 {config_id}:")
            logger.info(f"  描述: {description}")
            logger.info(f"  准确率: {accuracy:.1%}")
            logger.info(f"  重复检测数: {config_results['summary']['duplicates_detected']}")
            
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_config = config_results
        
        # 2. 显示最佳配置
        if best_config:
            logger.info(f"🎯 最佳配置: {best_config['config_id']}")
            logger.info(f"  准确率: {best_accuracy:.1%}")
            logger.info(f"  描述: {best_config['description']}")
            
            # 显示最佳配置的详细阈值
            config_data = None
            for config in self.create_optimized_configs():
                if config["config_id"] == best_config["config_id"]:
                    config_data = config["config"]
                    break
            
            if config_data:
                logger.info("  阈值配置:")
                for key, value in config_data.get("thresholds", {}).items():
                    logger.info(f"    {key}: {value}")
        
        # 3. 总体统计
        total_tests = self.stats["total_tests"]
        if total_tests > 0:
            overall_accuracy = self.stats["test_passed"] / total_tests
            logger.info(f"📈 总体统计:")
            logger.info(f"  总测试数: {total_tests}")
            logger.info(f"  总体准确率: {overall_accuracy:.1%}")
            logger.info(f"  重复检测总数: {self.stats['duplicates_detected']}")
            logger.info(f"  测试的配置数: {len(self.stats['configurations_tested'])}")
    
    def save_results(self, all_results: List[Dict[str, Any]]):
        """保存测试结果"""
        results_dir = Path("evaluate_service/data/results/optimized_dedup_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"optimized_dedup_results_{timestamp}.json"
        
        # 找出最佳配置
        best_config = None
        best_accuracy = 0
        for config_results in all_results:
            if config_results["summary"]["accuracy"] > best_accuracy:
                best_accuracy = config_results["summary"]["accuracy"]
                best_config = config_results
        
        output_data = {
            "metadata": {
                "test_type": "判重引擎优化配置测试",
                "test_time": datetime.now().isoformat(),
                "test_focus": "寻找最佳判重阈值配置"
            },
            "statistics": self.stats,
            "all_config_results": all_results,
            "best_configuration": best_config,
            "summary": {
                "total_configurations_tested": len(all_results),
                "overall_accuracy": self.stats["test_passed"] / self.stats["total_tests"] if self.stats["total_tests"] > 0 else 0,
                "best_config_id": best_config["config_id"] if best_config else None,
                "best_accuracy": best_accuracy
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        
        # 生成最佳配置的代码片段
        if best_config:
            self._generate_best_config_snippet(best_config)
        
        return output_file
    
    def _generate_best_config_snippet(self, best_config: Dict[str, Any]):
        """生成最佳配置的代码片段"""
        snippet_dir = Path("evaluate_service/data/results/optimized_dedup_test/snippets")
        snippet_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snippet_file = snippet_dir / f"best_config_{timestamp}.py"
        
        # 找到对应的配置数据
        config_data = None
        for config in self.create_optimized_configs():
            if config["config_id"] == best_config["config_id"]:
                config_data = config["config"]
                break
        
        if config_data:
            with open(snippet_file, 'w', encoding='utf-8') as f:
                f.write("# 最佳判重引擎配置\n")
                f.write("# 测试准确率: {:.1%}\n".format(best_config["summary"]["accuracy"]))
                f.write("# 配置ID: {}\n".format(best_config["config_id"]))
                f.write("# 描述: {}\n\n".format(best_config["description"]))
                
                f.write("OPTIMIZED_DEDUP_CONFIG = ")
                import json
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                f.write("\n\n")
                
                f.write("# 使用方法:\n")
                f.write("# from theme_service.deduplication_engine import ThemeDeduplicationEngine\n")
                f.write("# dedup_engine = ThemeDeduplicationEngine(config=OPTIMIZED_DEDUP_CONFIG)\n")
            
            logger.info(f"📝 最佳配置代码片段: {snippet_file}")

async def main():
    """主函数"""
    print("=" * 70)
    print("🔧 判重引擎优化配置测试")
    print("寻找最佳阈值配置以提高判重准确率")
    print("=" * 70)
    
    tester = OptimizedDedupTest()
    
    try:
        # 运行所有测试
        print("🚀 测试不同配置...")
        all_results = await tester.run_all_tests()
        
        # 分析结果
        tester.analyze_results(all_results)
        
        # 保存结果
        results_file = tester.save_results(all_results)
        
        print("\n" + "=" * 70)
        print("✅ 优化配置测试完成！")
        print("=" * 70)
        
        # 找出最佳配置
        best_config = None
        best_accuracy = 0
        for config_results in all_results:
            if config_results["summary"]["accuracy"] > best_accuracy:
                best_accuracy = config_results["summary"]["accuracy"]
                best_config = config_results
        
        if best_config:
            print(f"🎯 最佳配置: {best_config['config_id']}")
            print(f"   准确率: {best_accuracy:.1%}")
            print(f"   描述: {best_config['description']}")
            print(f"   重复检测数: {best_config['summary']['duplicates_detected']}/{best_config['summary']['total_tests']}")
        
        print(f"\n📊 总体结果:")
        print(f"   测试配置数: {len(all_results)}")
        print(f"   总体准确率: {tester.stats['test_passed']}/{tester.stats['total_tests']} ({tester.stats['test_passed']/tester.stats['total_tests']*100 if tester.stats['total_tests'] > 0 else 0:.1f}%)")
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())