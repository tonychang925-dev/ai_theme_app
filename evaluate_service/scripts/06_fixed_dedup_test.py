#!/usr/bin/env python3
"""
修复版判重引擎测试
使用正确的配置结构测试判重引擎
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

class FixedDedupTest:
    """修复版判重引擎测试"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_tests": 0,
            "duplicates_detected": 0,
            "test_passed": 0,
            "configurations_tested": []
        }
    
    def create_correct_configs(self) -> List[Dict[str, Any]]:
        """创建正确的配置格式（基于引擎的实际结构）"""
        configs = []
        
        # 配置1：默认配置（查看实际效果）
        configs.append({
            "config_id": "config_default",
            "description": "默认配置（引擎原版）",
            "config": None  # 使用引擎默认配置
        })
        
        # 配置2：优化配置（降低阈值）
        configs.append({
            "config_id": "config_optimized",
            "description": "优化配置（降低阈值）",
            "config": {
                "thresholds": {
                    "exact_match": 1.0,
                    "inclusion_match": 0.7,      # 降低包含关系阈值
                    "semantic_similarity": 0.65,  # 降低语义相似度阈值
                    "event_overlap": 0.6,
                    "auto_merge": 0.75,          # 降低自动合并阈值
                    "suggest_merge": 0.60,
                    "keep_separate": 0.4
                },
                "weights": {
                    "name_similarity": 0.4,
                    "keyword_overlap": 0.3,
                    "industry_match": 0.2,
                    "semantic_similarity": 0.1
                },
                "strategies": {
                    "enable_exact_match": True,
                    "enable_inclusion_check": True,
                    "enable_semantic_analysis": True,
                    "enable_event_overlap": True,
                    "use_jieba": True,
                    "cache_enabled": True
                }
            }
        })
        
        # 配置3：高敏感度配置（非常容易检测重复）
        configs.append({
            "config_id": "config_sensitive",
            "description": "高敏感度配置（易于检测重复）",
            "config": {
                "thresholds": {
                    "exact_match": 1.0,
                    "inclusion_match": 0.6,      # 非常低的包含阈值
                    "semantic_similarity": 0.55, # 很低的语义阈值
                    "event_overlap": 0.5,
                    "auto_merge": 0.65,          # 65%就自动合并
                    "suggest_merge": 0.50,
                    "keep_separate": 0.3
                },
                "weights": {
                    "name_similarity": 0.35,
                    "keyword_overlap": 0.35,     # 提高关键词权重
                    "industry_match": 0.20,
                    "semantic_similarity": 0.10
                },
                "strategies": {
                    "enable_exact_match": True,
                    "enable_inclusion_check": True,
                    "enable_semantic_analysis": True,
                    "enable_event_overlap": True,
                    "use_jieba": True,
                    "cache_enabled": True
                }
            }
        })
        
        # 配置4：保守配置（需要高相似度才判重）
        configs.append({
            "config_id": "config_conservative",
            "description": "保守配置（高相似度才判重）",
            "config": {
                "thresholds": {
                    "exact_match": 1.0,
                    "inclusion_match": 0.95,     # 很高的包含阈值
                    "semantic_similarity": 0.90, # 很高的语义阈值
                    "event_overlap": 0.8,
                    "auto_merge": 0.95,          # 95%才自动合并
                    "suggest_merge": 0.85,
                    "keep_separate": 0.6
                },
                "strategies": {
                    "enable_exact_match": True,
                    "enable_inclusion_check": True,
                    "enable_semantic_analysis": True,
                    "use_jieba": True,
                    "cache_enabled": True
                }
            }
        })
        
        logger.info(f"📋 创建了 {len(configs)} 种正确格式的配置")
        return configs
    
    def create_test_cases(self) -> List[Dict[str, Any]]:
        """创建测试用例"""
        test_cases = []
        
        # 1. 精确匹配（应该总是检测到）
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
            "expected_should_merge": True
        })
        
        # 2. 包含关系（核心测试）
        test_cases.append({
            "test_id": "inclusion_001",
            "description": "包含关系测试-人工智能芯片",
            "new_theme_name": "人工智能芯片",
            "event_data": {
                "title": "人工智能芯片技术突破",
                "impact_industries": ["半导体", "人工智能"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能", "event_count": 50}
            ],
            "expected_should_merge": True
        })
        
        # 3. 同义词测试
        test_cases.append({
            "test_id": "synonym_001",
            "description": "同义词测试-AI技术",
            "new_theme_name": "AI技术发展",
            "event_data": {
                "title": "AI技术新突破",
                "impact_industries": ["人工智能", "软件"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能,机器学习", "event_count": 50}
            ],
            "expected_should_merge": True
        })
        
        # 4. 语义相似度测试
        test_cases.append({
            "test_id": "semantic_001",
            "description": "语义相似度测试-智能机器人",
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
        
        # 5. 实际用例测试
        test_cases.append({
            "test_id": "real_world_001",
            "description": "实际用例-AI智能眼镜",
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
        
        # 6. 不同题材测试（应该不合并）
        test_cases.append({
            "test_id": "distinct_001",
            "description": "不同题材测试-新能源汽车",
            "new_theme_name": "新能源汽车",
            "event_data": {
                "title": "新能源汽车销量增长",
                "impact_industries": ["新能源汽车", "汽车制造"]
            },
            "existing_themes": [
                {"id": 1, "name": "人工智能", "keywords": "AI,人工智能", "event_count": 50}
            ],
            "expected_should_merge": False
        })
        
        # 7. 边界测试
        test_cases.append({
            "test_id": "boundary_001",
            "description": "边界测试-新能源车电池",
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
        
        try:
            # 创建引擎
            if config["config"] is None:
                dedup_engine = ThemeDeduplicationEngine()  # 使用默认配置
            else:
                dedup_engine = ThemeDeduplicationEngine(config=config["config"])
        except Exception as e:
            logger.error(f"❌ 引擎初始化失败: {e}")
            return {
                "config_id": config["config_id"],
                "description": config["description"],
                "error": f"初始化失败: {e}",
                "tests": [],
                "summary": {"total_tests": 0, "passed": 0, "accuracy": 0.0}
            }
        
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
                    "existing_themes": [t["name"] for t in test_case["existing_themes"]],
                    "expected_should_merge": test_case["expected_should_merge"],
                    "actual_should_merge": result.should_merge,
                    "similarity": round(result.similarity_score, 4),
                    "match_type": result.match_type,
                    "reason": result.reason,
                    "passed": (test_case["expected_should_merge"] == result.should_merge)
                }
                
                config_results["tests"].append(test_result)
                config_results["summary"]["total_tests"] += 1
                
                if test_result["passed"]:
                    config_results["summary"]["passed"] += 1
                
                if result.should_merge:
                    config_results["summary"]["duplicates_detected"] += 1
                
                # 详细日志
                status = "✅" if test_result["passed"] else "❌"
                logger.debug(f"    {status} {test_case['test_id']}: 预期={test_case['expected_should_merge']}, 实际={result.should_merge}, 相似度={result.similarity_score:.3f}, 类型={result.match_type}")
                
            except Exception as e:
                logger.error(f"    ❌ 测试 {test_case['test_id']} 失败: {e}")
                test_result = {
                    "test_id": test_case["test_id"],
                    "error": str(e),
                    "passed": False
                }
                config_results["tests"].append(test_result)
                config_results["summary"]["total_tests"] += 1
        
        # 计算准确率
        if config_results["summary"]["total_tests"] > 0:
            accuracy = config_results["summary"]["passed"] / config_results["summary"]["total_tests"]
        else:
            accuracy = 0
        
        config_results["summary"]["accuracy"] = accuracy
        
        logger.info(f"    📊 配置结果: 通过={config_results['summary']['passed']}/{config_results['summary']['total_tests']}, 准确率={accuracy:.1%}, 重复检测={config_results['summary']['duplicates_detected']}")
        
        return config_results
    
    async def run_all_tests(self):
        """运行所有配置的测试"""
        logger.info("🚀 开始判重引擎配置测试...")
        
        configs = self.create_correct_configs()
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
        logger.info(f"\n📊 分析 {len(all_results)} 种配置的测试结果...")
        
        # 1. 找出最佳配置
        best_config = None
        best_accuracy = 0
        best_detection = 0
        
        for config_results in all_results:
            accuracy = config_results["summary"]["accuracy"]
            duplicates = config_results["summary"]["duplicates_detected"]
            config_id = config_results["config_id"]
            description = config_results["description"]
            
            # 跳过有错误的配置
            if "error" in config_results:
                logger.info(f"❌ 配置 {config_id}: 有错误 - {config_results['error']}")
                continue
            
            logger.info(f"🔧 配置 {config_id}:")
            logger.info(f"  描述: {description}")
            logger.info(f"  准确率: {accuracy:.1%} ({config_results['summary']['passed']}/{config_results['summary']['total_tests']})")
            logger.info(f"  重复检测数: {duplicates}")
            
            # 优先选择高准确率且能检测到足够重复的配置
            if accuracy > best_accuracy or (accuracy == best_accuracy and duplicates > best_detection):
                best_accuracy = accuracy
                best_detection = duplicates
                best_config = config_results
        
        # 2. 显示最佳配置
        if best_config:
            logger.info(f"\n🎯 最佳配置: {best_config['config_id']}")
            logger.info(f"  准确率: {best_accuracy:.1%}")
            logger.info(f"  描述: {best_config['description']}")
            
            # 显示失败用例
            failed_tests = [t for t in best_config["tests"] if not t.get("passed", True)]
            if failed_tests:
                logger.info("  ❌ 失败用例:")
                for test in failed_tests[:3]:  # 只显示前3个
                    logger.info(f"    - {test.get('description', '未知')}: 预期={test.get('expected_should_merge')}, 实际={test.get('actual_should_merge')}")
        
        # 3. 总体统计
        total_tests = self.stats["total_tests"]
        if total_tests > 0:
            overall_accuracy = self.stats["test_passed"] / total_tests
            logger.info(f"\n📈 总体统计:")
            logger.info(f"  总测试数: {total_tests}")
            logger.info(f"  总体准确率: {overall_accuracy:.1%}")
            logger.info(f"  重复检测总数: {self.stats['duplicates_detected']}")
            logger.info(f"  测试的配置数: {len(self.stats['configurations_tested'])}")
    
    def save_results(self, all_results: List[Dict[str, Any]]):
        """保存测试结果"""
        results_dir = Path("evaluate_service/data/results/fixed_dedup_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"fixed_dedup_results_{timestamp}.json"
        
        # 找出最佳配置
        best_config = None
        best_accuracy = 0
        for config_results in all_results:
            if "error" not in config_results and config_results["summary"]["accuracy"] > best_accuracy:
                best_accuracy = config_results["summary"]["accuracy"]
                best_config = config_results
        
        output_data = {
            "metadata": {
                "test_type": "判重引擎修复版配置测试",
                "test_time": datetime.now().isoformat(),
                "test_focus": "使用正确配置格式测试判重引擎"
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
        if best_config and best_config["config_id"] != "config_default":
            self._generate_best_config_snippet(best_config)
        
        return output_file
    
    def _generate_best_config_snippet(self, best_config: Dict[str, Any]):
        """生成最佳配置的代码片段"""
        snippet_dir = Path("evaluate_service/data/results/fixed_dedup_test/snippets")
        snippet_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snippet_file = snippet_dir / f"best_config_{timestamp}.py"
        
        # 找到对应的配置数据
        configs = self.create_correct_configs()
        config_data = None
        for config in configs:
            if config["config_id"] == best_config["config_id"]:
                config_data = config["config"]
                break
        
        if config_data:
            with open(snippet_file, 'w', encoding='utf-8') as f:
                f.write("""#!/usr/bin/env python3
# 最佳判重引擎配置
# 基于测试结果生成
""")
                f.write(f"# 测试准确率: {best_config['summary']['accuracy']:.1%}\n")
                f.write(f"# 配置ID: {best_config['config_id']}\n")
                f.write(f"# 描述: {best_config['description']}\n\n")
                
                f.write("OPTIMIZED_DEDUP_CONFIG = ")
                import json
                json.dump(config_data, f, indent=2, ensure_ascii=False)
                f.write("\n\n")
                
                f.write("""# 使用方法:
# 1. 在ThemeDiscoveryEngine中使用:
#    from theme_service.deduplication_engine import ThemeDeduplicationEngine
#    dedup_engine = ThemeDeduplicationEngine(config=OPTIMIZED_DEDUP_CONFIG)
#    discovery_engine.set_dedup_engine(dedup_engine)
#
# 2. 或者在EnhancedThemeDiscoveryEngine中设置:
#    config = {
#        'fast_track_threshold': 0.95,
#        'dedup_config': OPTIMIZED_DEDUP_CONFIG
#    }
#    discovery_engine = EnhancedThemeDiscoveryEngine(config=config)
""")
            
            logger.info(f"📝 最佳配置代码片段已保存: {snippet_file}")
    
    def print_summary_table(self, all_results: List[Dict[str, Any]]):
        """打印汇总表格"""
        print("\n" + "="*120)
        print("📊 判重引擎配置测试汇总")
        print("="*120)
        print(f"{'配置ID':<20} {'描述':<30} {'准确率':<10} {'重复检测':<12} {'测试数':<8}")
        print("-"*120)
        
        for config_results in all_results:
            config_id = config_results["config_id"]
            description = config_results["description"]
            accuracy = config_results["summary"]["accuracy"]
            duplicates = config_results["summary"]["duplicates_detected"]
            total_tests = config_results["summary"]["total_tests"]
            
            # 标记最佳配置
            best_marker = ""
            if accuracy >= 0.8:
                best_marker = "🌟 "
            
            # 格式化输出
            print(f"{best_marker}{config_id:<20} {description:<30} {accuracy:>7.1%} {duplicates:>8}/{total_tests:<8}")

async def main():
    """主函数"""
    print("=" * 70)
    print("🔧 判重引擎修复版配置测试")
    print("使用正确的配置格式测试判重引擎")
    print("=" * 70)
    
    tester = FixedDedupTest()
    
    try:
        # 运行所有测试
        print("🚀 开始测试不同配置...")
        all_results = await tester.run_all_tests()
        
        # 分析结果
        tester.analyze_results(all_results)
        
        # 打印汇总表格
        tester.print_summary_table(all_results)
        
        # 保存结果
        results_file = tester.save_results(all_results)
        
        print("\n" + "=" * 70)
        print("✅ 修复版配置测试完成！")
        print("=" * 70)
        
        # 找出最佳配置
        best_config = None
        best_accuracy = 0
        for config_results in all_results:
            if "error" not in config_results and config_results["summary"]["accuracy"] > best_accuracy:
                best_accuracy = config_results["summary"]["accuracy"]
                best_config = config_results
        
        if best_config:
            print(f"🎯 最佳配置: {best_config['config_id']}")
            print(f"   准确率: {best_accuracy:.1%}")
            print(f"   重复检测: {best_config['summary']['duplicates_detected']}/{best_config['summary']['total_tests']}")
            print(f"   描述: {best_config['description']}")
        
        print(f"\n📊 总体结果:")
        print(f"   测试配置数: {len(all_results)}")
        print(f"   总体准确率: {tester.stats['test_passed']}/{tester.stats['total_tests']} ({tester.stats['test_passed']/tester.stats['total_tests']*100 if tester.stats['total_tests'] > 0 else 0:.1f}%)")
        print(f"   重复检测总数: {tester.stats['duplicates_detected']}")
        
        if best_accuracy < 0.7:
            print(f"\n⚠️  警告: 最佳准确率只有 {best_accuracy:.1%}，判重引擎可能需要进一步优化")
        elif best_accuracy >= 0.8:
            print(f"\n✅ 好消息: 最佳准确率达到 {best_accuracy:.1%}，配置效果良好")
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())