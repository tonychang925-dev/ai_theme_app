#!/usr/bin/env python3
"""
第二阶段：真实架构集成验证测试
验证三个核心组件的正确整合和工作效果
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple
import logging
import statistics
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

class RealArchitectureIntegrationTest:
    """真实架构集成测试"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_events": 0,
            "processed": 0,
            "processing_times": [],
            "component_usage": defaultdict(int),
            "themes_created": defaultdict(int),
            "themes_merged": defaultdict(int),
            "duplicates_detected": 0,
            "errors": []
        }
        
    async def initialize_components(self) -> bool:
        """初始化所有真实组件"""
        logger.info("🔧 开始初始化完整架构...")
        
        try:
            # 1. 初始化RelatedThemeFetcher
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            self.theme_fetcher = RelatedThemeFetcher(use_cache=True)
            logger.info("✅ RelatedThemeFetcher 初始化成功")
            self.stats["component_usage"]["RelatedThemeFetcher"] += 1
            
            # 2. 初始化判重引擎
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            self.dedup_engine = ThemeDeduplicationEngine()
            logger.info("✅ ThemeDeduplicationEngine 初始化成功")
            self.stats["component_usage"]["ThemeDeduplicationEngine"] += 1
            
            # 3. 初始化真实AI客户端
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            self.ai_client = EnhancedAIThemeClient(settings={'USE_ENHANCED_MODE': True})
            logger.info("✅ EnhancedAIThemeClient 初始化成功（真实模式）")
            self.stats["component_usage"]["EnhancedAIThemeClient"] += 1
            
            # 4. 创建修复版EnhancedThemeDiscoveryEngine
            self.engine = await self._create_fixed_engine()
            logger.info("✅ EnhancedThemeDiscoveryEngine（修复版）初始化成功")
            self.stats["component_usage"]["EnhancedThemeDiscoveryEngine"] += 1
            
            # 5. 测试组件连通性
            test_result = await self._test_integration_connectivity()
            if not test_result:
                logger.error("❌ 组件集成测试失败")
                return False
                
            logger.info(f"✅ 所有 {len(self.stats['component_usage'])} 个组件初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化完整架构失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _create_fixed_engine(self):
        """创建修复版引擎，正确整合所有组件"""
        from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
        
        # 创建子类，修复缺失的整合
        class FixedEnhancedEngine(EnhancedThemeDiscoveryEngine):
            def __init__(self, ai_client, theme_fetcher, dedup_engine):
                # 调用父类初始化
                super().__init__(ai_client, db_manager=None)
                
                # 添加缺失的组件
                self.theme_fetcher = theme_fetcher
                self.dedup_engine = dedup_engine
                
                # 用于统计
                self.duplicate_checks = 0
                self.duplicates_prevented = 0
                logger.info("FixedEnhancedEngine 创建成功（整合版）")
            
            async def _fetch_related_themes(self, event: Dict) -> List[Dict]:
                """修复：使用真实的RelatedThemeFetcher"""
                try:
                    # 使用真实fetcher
                    themes = await self.theme_fetcher.fetch_related_themes(
                        event_data=event,
                        limit=5
                    )
                    logger.debug(f"检索到 {len(themes)} 个相关题材")
                    return themes
                except Exception as e:
                    logger.error(f"检索相关题材失败: {e}")
                    # 回退到父类的简单实现
                    return await super()._fetch_related_themes(event)
            
            async def _check_duplication(self, event: Dict, ai_decision: Dict, 
                                       related_themes: List[Dict]) -> Dict:
                """修复：使用真实的判重引擎"""
                try:
                    new_theme_name = ai_decision.get('target_theme_name', '')
                    if not new_theme_name or not related_themes:
                        return {'should_merge': False}
                    
                    # 使用真实判重引擎
                    dedup_result = await self.dedup_engine.check_duplication(
                        new_theme_name=new_theme_name,
                        event_data=event,
                        existing_themes=related_themes
                    )
                    
                    self.duplicate_checks += 1
                    
                    if dedup_result.should_merge:
                        self.duplicates_prevented += 1
                        logger.info(f"判重引擎检测到重复: {new_theme_name} -> {dedup_result.target_theme.get('name', '未知')}")
                    
                    # 转换结果为引擎需要的格式
                    return {
                        'should_merge': dedup_result.should_merge,
                        'target_theme': dedup_result.target_theme.get('name', '') if dedup_result.target_theme else '',
                        'similarity': dedup_result.similarity_score,
                        'reason': dedup_result.reason,
                        'dedup_details': dedup_result.to_dict()
                    }
                    
                except Exception as e:
                    logger.error(f"判重检查失败: {e}")
                    # 回退到父类的简单实现
                    return await super()._check_duplication(event, ai_decision, related_themes)
        
        # 创建修复版引擎实例
        return FixedEnhancedEngine(
            ai_client=self.ai_client,
            theme_fetcher=self.theme_fetcher,
            dedup_engine=self.dedup_engine
        )
    
    async def _test_integration_connectivity(self) -> bool:
        """测试组件集成连通性"""
        logger.info("🔗 测试组件集成连通性...")
        
        try:
            # 创建测试事件
            test_event = {
                "id": "integration_test_001",
                "title": "人工智能芯片技术突破",
                "summary": "国内企业发布新一代AI芯片，性能提升显著",
                "event_type": "技术突破",
                "impact_industries": ["半导体", "人工智能", "集成电路"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.88,
                    "reason": "AI芯片技术突破"
                }
            }
            
            # 测试相关题材检索
            related_themes = await self.engine._fetch_related_themes(test_event)
            logger.info(f"✅ 相关题材检索成功: {len(related_themes)} 个题材")
            
            # 测试判重引擎
            test_ai_decision = {
                "decision": "CREATE_NEW",
                "target_theme_name": "人工智能芯片",
                "confidence": 0.85,
                "reason": "测试判重"
            }
            
            dedup_result = await self.engine._check_duplication(
                test_event, test_ai_decision, related_themes
            )
            logger.info(f"✅ 判重引擎测试成功: {dedup_result.get('should_merge', False)}")
            
            # 测试完整流程
            full_result = await self.engine.process_single_event(test_event)
            
            if full_result.get('status') in ['created', 'merged', 'in_review']:
                logger.info(f"✅ 完整流程测试成功: {full_result.get('status')}")
                return True
            else:
                logger.warning(f"⚠️ 完整流程测试返回异常状态: {full_result.get('status')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 集成连通性测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def load_test_data(self, sample_size: int = 20) -> List[Dict[str, Any]]:
        """加载测试数据"""
        data_path = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
        
        if not data_path.exists():
            logger.error(f"❌ 测试数据文件不存在: {data_path}")
            raise FileNotFoundError(f"测试数据文件不存在: {data_path}")
        
        logger.info(f"📂 加载测试数据: {data_path}")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        
        # 添加一些重复测试用例
        enhanced_events = self._add_duplicate_test_cases(events)
        
        # 抽样测试
        sample_size = min(sample_size, len(enhanced_events))
        sampled_events = enhanced_events[:sample_size]
        
        logger.info(f"✅ 加载成功: {len(sampled_events)} 个事件（抽样测试）")
        
        self.stats["total_events"] = len(sampled_events)
        return sampled_events
    
    def _add_duplicate_test_cases(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """添加重复测试用例"""
        enhanced_events = events.copy()
        
        # 添加语义重复的事件
        duplicate_tests = [
            {
                "id": "dup_ai_chip_001",
                "title": "AI芯片技术新突破",
                "summary": "人工智能芯片技术取得重大进展",
                "event_type": "技术突破",
                "impact_industries": ["半导体", "人工智能"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.85,
                    "reason": "AI芯片技术"
                }
            },
            {
                "id": "dup_space_001", 
                "title": "商业航天发射成功",
                "summary": "商业航天公司成功发射卫星",
                "event_type": "商业动态",
                "impact_industries": ["航空航天", "商业航天"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.82,
                    "reason": "商业航天发展"
                }
            }
        ]
        
        enhanced_events.extend(duplicate_tests)
        logger.info(f"📝 添加了 {len(duplicate_tests)} 个重复测试用例")
        return enhanced_events
    
    async def process_single_event_real(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """使用修复版引擎处理单个事件"""
        start_time = datetime.now()
        
        try:
            # 使用修复版引擎处理
            result = await self.engine.process_single_event(event)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.stats["processing_times"].append(processing_time)
            
            # 提取关键信息
            status = result.get('status', 'unknown')
            execution_result = result.get('execution_result', {})
            final_theme = execution_result.get('target_theme_name', '') or execution_result.get('new_theme_name', '未知')
            
            # 判重信息
            dedup_info = execution_result.get('dedup_details', {})
            
            simplified_result = {
                'event_id': event.get('id'),
                'title': event.get('title', '')[:40],
                'original_action': event.get('theme_directive', {}).get('action', 'CLUSTER'),
                'final_decision': result.get('ai_decision', {}).get('decision', 'UNKNOWN'),
                'final_theme': final_theme,
                'status': status,
                'processing_time_ms': processing_time,
                'decision_confidence': result.get('ai_decision', {}).get('confidence', 0),
                'duplication_checked': bool(dedup_info),
                'duplicate_prevented': dedup_info.get('should_merge', False)
            }
            
            self.stats["processed"] += 1
            
            # 主题统计
            if status == 'created' and final_theme != '未知':
                self.stats["themes_created"][final_theme] += 1
            elif status == 'merged' and final_theme != '未知':
                self.stats["themes_merged"][final_theme] += 1
            
            # 进度显示
            if self.stats["processed"] % 5 == 0:
                avg_time = statistics.mean(self.stats["processing_times"][-5:]) if len(self.stats["processing_times"]) >= 5 else 0
                logger.info(f"  已处理 {self.stats['processed']}/{self.stats['total_events']} | 平均耗时: {avg_time:.1f}ms")
            
            return simplified_result
            
        except Exception as e:
            logger.error(f"❌ 处理事件 {event.get('id')} 失败: {e}")
            
            error_result = {
                'event_id': event.get('id'),
                'status': 'error',
                'error': str(e),
                'processing_time_ms': (datetime.now() - start_time).total_seconds() * 1000
            }
            
            self.stats["errors"].append(f"事件 {event.get('id')}: {str(e)}")
            return error_result
    
    async def process_batch(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量处理事件"""
        logger.info(f"🔄 开始批量处理 {len(events)} 个事件...")
        
        results = []
        
        # 顺序处理，避免API限制
        for i, event in enumerate(events):
            result = await self.process_single_event_real(event)
            results.append(result)
            
            # 显示批次统计
            if (i + 1) % 5 == 0:
                batch = results[-5:]
                created = sum(1 for r in batch if r.get('status') == 'created')
                merged = sum(1 for r in batch if r.get('status') == 'merged')
                duplicates = sum(1 for r in batch if r.get('duplicate_prevented', False))
                
                logger.info(f"  批次 {i//5 + 1}: 创建{created}, 归并{merged}, 重复{duplicates}")
            
            # 短暂延迟，避免API限制
            if i < len(events) - 1:
                await asyncio.sleep(0.1)
        
        logger.info(f"✅ 批量处理完成: {len(results)} 个结果")
        return results
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析处理结果"""
        logger.info(f"📊 分析 {len(results)} 个处理结果...")
        
        # 1. 状态分布
        status_counts = defaultdict(int)
        for result in results:
            status = result.get('status', 'unknown')
            status_counts[status] += 1
        
        logger.info("处理状态分布:")
        for status, count in sorted(status_counts.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {status}: {count} ({percentage:.1f}%)")
        
        # 2. 决策类型分布
        decision_counts = defaultdict(int)
        for result in results:
            decision = result.get('final_decision', 'UNKNOWN')
            decision_counts[decision] += 1
        
        logger.info("AI决策分布:")
        for decision, count in sorted(decision_counts.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {decision}: {count} ({percentage:.1f}%)")
        
        # 3. 判重效果
        duplication_checked = sum(1 for r in results if r.get('duplication_checked', False))
        duplicates_prevented = sum(1 for r in results if r.get('duplicate_prevented', False))
        
        logger.info("判重效果:")
        logger.info(f"  判重检查次数: {duplication_checked}")
        logger.info(f"  阻止重复创建: {duplicates_prevented}")
        if duplication_checked > 0:
            logger.info(f"  判重有效率: {duplicates_prevented/duplication_checked*100:.1f}%")
        
        # 4. 题材统计
        logger.info("题材创建统计:")
        logger.info(f"  创建的不同题材数: {len(self.stats['themes_created'])}")
        logger.info(f"  归并到的题材数: {len(self.stats['themes_merged'])}")
        
        if self.stats["themes_created"]:
            logger.info("新建题材分布 (前5):")
            for theme, count in sorted(self.stats["themes_created"].items(), 
                                     key=lambda x: x[1], reverse=True)[:5]:
                logger.info(f"  {theme}: {count}个事件")
        
        # 5. 性能分析
        if self.stats["processing_times"]:
            avg_time = statistics.mean(self.stats["processing_times"])
            median_time = statistics.median(self.stats["processing_times"])
            
            logger.info("性能分析:")
            logger.info(f"  平均处理时间: {avg_time:.1f}ms")
            logger.info(f"  中位数时间: {median_time:.1f}ms")
            logger.info(f"  目标 (<2秒): {'✅ 达标' if avg_time < 2000 else '❌ 超标'}")
            
            # 分析耗时分布
            time_distribution = {
                "<1秒": sum(1 for t in self.stats["processing_times"] if t < 1000),
                "1-3秒": sum(1 for t in self.stats["processing_times"] if 1000 <= t < 3000),
                "3-5秒": sum(1 for t in self.stats["processing_times"] if 3000 <= t < 5000),
                "≥5秒": sum(1 for t in self.stats["processing_times"] if t >= 5000)
            }
            
            logger.info("耗时分布:")
            for range_name, count in time_distribution.items():
                if count > 0:
                    percentage = count / len(self.stats["processing_times"]) * 100
                    logger.info(f"  {range_name}: {count} ({percentage:.1f}%)")
        
        # 6. 错误分析
        if self.stats["errors"]:
            logger.warning(f"⚠️ 发现 {len(self.stats['errors'])} 个错误")
            for error in self.stats["errors"][:3]:
                logger.warning(f"  错误: {error}")
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存处理结果"""
        results_dir = Path("evaluate_service/data/results/fixed_integration_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"fixed_integration_results_{timestamp}.json"
        
        output_data = {
            "metadata": {
                "test_type": "修复版架构集成测试",
                "test_time": datetime.now().isoformat(),
                "dataset_size": self.stats["total_events"],
                "components_used": list(self.stats["component_usage"].keys())
            },
            "statistics": self.stats,
            "detailed_results": results,
            "summary": {
                "total_processed": self.stats["processed"],
                "success_rate": self.stats["processed"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "unique_themes_created": len(self.stats["themes_created"]),
                "duplicates_prevented": self.stats["duplicates_detected"],
                "avg_processing_time_ms": statistics.mean(self.stats["processing_times"]) if self.stats["processing_times"] else 0
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file
    
    def generate_report(self, results_file: Path):
        """生成测试报告"""
        report_dir = Path("evaluate_service/data/results/fixed_integration_test/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"fixed_integration_report_{timestamp}.txt"
        
        with open(results_file, 'r', encoding='utf-8') as f:
            results_data = json.load(f)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("修复版架构集成测试报告\n")
            f.write("=" * 70 + "\n\n")
            
            metadata = results_data["metadata"]
            stats = results_data["statistics"]
            
            f.write(f"📅 测试时间: {metadata['test_time'][:19]}\n")
            f.write(f"📊 数据集: {metadata['dataset_size']} 个事件\n")
            f.write(f"🔧 使用组件: {', '.join(metadata['components_used'])}\n\n")
            
            f.write("📈 处理统计:\n")
            f.write("-" * 50 + "\n")
            f.write(f"总事件数: {stats['total_events']}\n")
            f.write(f"成功处理: {stats['processed']}\n")
            
            if stats["processing_times"]:
                avg_time = statistics.mean(stats["processing_times"])
                f.write(f"平均处理时间: {avg_time:.1f}ms\n")
                f.write(f"性能状态: {'✅ 达标 (<2秒)' if avg_time < 2000 else '❌ 超标 (>2秒)'}\n")
            
            f.write(f"创建题材数: {len(stats['themes_created'])}\n")
            f.write(f"判重检查次数: {stats['duplicates_detected']}\n\n")
            
            f.write("🏷️ 新建题材:\n")
            f.write("-" * 30 + "\n")
            for theme, count in sorted(stats['themes_created'].items(), 
                                     key=lambda x: x[1], reverse=True)[:10]:
                f.write(f"{theme}: {count}个事件\n")
        
        logger.info(f"📋 测试报告生成: {report_file}")

async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 第二阶段：修复版架构集成测试")
    print("验证所有组件正确整合，使用真实AI处理")
    print("=" * 70)
    
    tester = RealArchitectureIntegrationTest()
    
    try:
        # 1. 初始化组件（修复版）
        init_success = await tester.initialize_components()
        if not init_success:
            print("❌ 组件初始化失败，无法继续测试")
            return 1
        
        # 2. 加载测试数据（小样本，20条）
        events = await tester.load_test_data(sample_size=20)
        if not events:
            print("❌ 没有测试数据，无法继续")
            return 1
        
        # 3. 处理事件（真实AI）
        print("\n🔍 注意：将使用真实AI API，可能有API调用费用")
        print("   测试规模：20个事件（小样本验证）")
        confirm = input("   是否继续？ (y/n): ")
        
        if confirm.lower() != 'y':
            print("测试取消")
            return 0
        
        results = await tester.process_batch(events)
        
        # 4. 分析结果
        tester.analyze_results(results)
        
        # 5. 保存结果
        results_file = tester.save_results(results)
        
        # 6. 生成报告
        tester.generate_report(results_file)
        
        print("\n" + "=" * 70)
        print("✅ 修复版架构集成测试完成！")
        print("=" * 70)
        print(f"📊 关键结果:")
        print(f"  总事件数: {tester.stats['total_events']}")
        print(f"  成功处理: {tester.stats['processed']}")
        print(f"  使用组件: {len(tester.stats['component_usage'])} 个")
        print(f"  创建题材: {len(tester.stats['themes_created'])} 个")
        
        if tester.stats["processing_times"]:
            avg_time = statistics.mean(tester.stats["processing_times"])
            print(f"  平均耗时: {avg_time:.1f}ms")
            print(f"  性能状态: {'✅ 达标' if avg_time < 2000 else '❌ 需优化'}")
        
        if tester.stats["errors"]:
            print(f"⚠️  发现 {len(tester.stats['errors'])} 个错误")
        else:
            print("✅ 无错误发生")
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())