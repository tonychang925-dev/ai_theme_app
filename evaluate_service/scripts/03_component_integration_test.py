#!/usr/bin/env python3
"""
新集成测试：验证优化后的引擎组件整合
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
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

class NewIntegrationTest:
    """新集成测试：使用优化后的引擎"""
    
    def __init__(self):
        self.results = []
        self.stats = {
            "total_events": 0,
            "processed": 0,
            "processing_times": [],
            "components_verified": defaultdict(int),
            "themes_created": defaultdict(int),
            "themes_merged": defaultdict(int),
            "duplicates_prevented": 0,
            "errors": []
        }
        
    async def initialize_components(self) -> bool:
        """初始化所有组件，使用优化后的引擎"""
        logger.info("🔧 开始初始化优化版引擎...")
        
        try:
            # 1. 初始化RelatedThemeFetcher
            from theme_service.related_theme_fetcher import RelatedThemeFetcher
            theme_fetcher = RelatedThemeFetcher(use_cache=True)
            logger.info("✅ RelatedThemeFetcher 初始化成功")
            
            # 2. 初始化判重引擎
            from theme_service.deduplication_engine import ThemeDeduplicationEngine
            dedup_engine = ThemeDeduplicationEngine()
            logger.info("✅ ThemeDeduplicationEngine 初始化成功")
            
            # 3. 初始化AI客户端
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            ai_client = EnhancedAIThemeClient(settings={'USE_ENHANCED_MODE': True})
            logger.info("✅ EnhancedAIThemeClient 初始化成功")
            
            # 4. 初始化优化后的引擎（使用我们修改的版本）
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            
            # 使用优化后的构造函数
            self.engine = EnhancedThemeDiscoveryEngine(
                ai_client=ai_client,
                db_manager=None,
                theme_fetcher=theme_fetcher,  # 传递theme_fetcher
                dedup_engine=dedup_engine,    # 传递dedup_engine
                config={
                    'fast_track_threshold': 0.85,
                    'review_threshold': 0.65,
                    'ignore_threshold': 0.3,
                    'dedup_threshold': 0.8
                }
            )
            
            logger.info("✅ EnhancedThemeDiscoveryEngine（优化版）初始化成功")
            
            # 5. 验证引擎信息
            engine_info = self.engine.get_engine_info()
            logger.info(f"🔧 引擎组件状态:")
            logger.info(f"  theme_fetcher: {'✅ 可用' if engine_info['components_available']['theme_fetcher'] else '❌ 不可用'}")
            logger.info(f"  dedup_engine: {'✅ 可用' if engine_info['components_available']['dedup_engine'] else '❌ 不可用'}")
            
            # 6. 测试组件功能
            test_result = await self._test_component_functionality()
            if not test_result:
                logger.warning("⚠️ 组件功能测试有警告，但继续测试")
            
            logger.info("✅ 所有组件初始化验证完成")
            return True
            
        except Exception as e:
            logger.error(f"❌ 初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _test_component_functionality(self) -> bool:
        """测试组件功能"""
        logger.info("🔍 测试组件功能...")
        
        try:
            # 创建测试事件
            test_event = {
                "id": "component_test",
                "title": "AI芯片技术测试",
                "summary": "测试组件功能",
                "event_type": "测试",
                "impact_industries": ["人工智能", "半导体"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.85,
                    "reason": "测试组件"
                }
            }
            
            # 测试主题检索功能
            logger.info("测试主题检索功能...")
            related_themes = await self.engine._fetch_related_themes(test_event)
            logger.info(f"主题检索结果: {len(related_themes)} 个主题")
            self.stats["components_verified"]["theme_fetcher"] += 1
            
            # 测试判重功能
            logger.info("测试判重功能...")
            test_ai_decision = {
                "decision": "CREATE_NEW",
                "target_theme_name": "人工智能芯片",
                "confidence": 0.85,
                "reason": "测试判重"
            }
            
            dedup_result = await self.engine._check_duplication(
                test_event, test_ai_decision, related_themes
            )
            logger.info(f"判重结果: should_merge={dedup_result.get('should_merge', False)}")
            self.stats["components_verified"]["dedup_engine"] += 1
            
            # 测试完整流程
            logger.info("测试完整处理流程...")
            result = await self.engine.process_single_event(test_event)
            
            if result.get('status') in ['created', 'merged', 'in_review']:
                logger.info(f"完整流程测试成功: {result.get('status')}")
                
                # 检查组件使用信息
                components_used = result.get('components_used', {})
                if components_used:
                    logger.info(f"组件使用情况: {components_used}")
                
                return True
            else:
                logger.warning(f"完整流程测试返回异常状态: {result.get('status')}")
                return False
                
        except Exception as e:
            logger.error(f"组件功能测试失败: {e}")
            return False
    
    async def load_test_data(self, sample_size: int = 10) -> List[Dict[str, Any]]:
        """加载测试数据（小样本，专注于功能验证）"""
        data_path = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
        
        if not data_path.exists():
            logger.error(f"❌ 测试数据文件不存在: {data_path}")
            raise FileNotFoundError(f"测试数据文件不存在: {data_path}")
        
        logger.info(f"📂 加载测试数据: {data_path}")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        
        # 专门选择可能触发判重的事件
        selected_events = []
        for event in events[:sample_size*2]:  # 多看一些事件
            # 选择AI相关的事件，更容易触发判重
            industries = event.get('impact_industries', [])
            if any(keyword in str(industries) for keyword in ['人工智能', 'AI', '半导体', '芯片']):
                selected_events.append(event)
                if len(selected_events) >= sample_size:
                    break
        
        # 如果不够，补充其他事件
        if len(selected_events) < sample_size:
            selected_events.extend(events[len(selected_events):sample_size])
        
        # 添加一个明显的重复测试用例
        duplicate_test = {
            "id": "explicit_duplicate_test",
            "title": "人工智能芯片技术突破重复测试",
            "summary": "这是专门测试判重的重复事件",
            "event_type": "技术突破",
            "impact_industries": ["人工智能", "半导体"],
            "theme_directive": {
                "action": "CREATE_NEW",
                "confidence": 0.9,
                "reason": "测试判重功能"
            }
        }
        
        selected_events.append(duplicate_test)
        
        logger.info(f"✅ 加载成功: {len(selected_events)} 个事件（包含重复测试）")
        
        self.stats["total_events"] = len(selected_events)
        return selected_events
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """处理单个事件"""
        start_time = datetime.now()
        
        try:
            # 使用优化后的引擎处理
            result = await self.engine.process_single_event(event)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.stats["processing_times"].append(processing_time)
            
            # 提取关键信息
            status = result.get('status', 'unknown')
            execution_result = result.get('execution_result', {})
            final_theme = execution_result.get('target_theme_name', '') or execution_result.get('new_theme_name', '未知')
            
            # 提取组件使用信息
            components_used = result.get('components_used', {})
            deduplication_info = result.get('deduplication_info', {})
            
            simplified_result = {
                'event_id': event.get('id'),
                'title': event.get('title', '')[:30],
                'final_decision': result.get('ai_decision', {}).get('decision', 'UNKNOWN'),
                'final_theme': final_theme,
                'status': status,
                'processing_time_ms': processing_time,
                'components_used': components_used,
                'deduplication_checked': bool(deduplication_info),
                'duplicate_prevented': deduplication_info.get('should_merge', False),
                'execution_path': result.get('execution_path', 'unknown')
            }
            
            self.stats["processed"] += 1
            
            # 统计组件使用
            for component, used in components_used.items():
                if used:
                    self.stats["components_verified"][f"{component}_used"] += 1
            
            # 统计判重效果
            if deduplication_info.get('should_merge', False):
                self.stats["duplicates_prevented"] += 1
            
            # 题材统计
            if status == 'created' and final_theme != '未知':
                self.stats["themes_created"][final_theme] += 1
            elif status == 'merged' and final_theme != '未知':
                self.stats["themes_merged"][final_theme] += 1
            
            # 进度显示
            if self.stats["processed"] % 5 == 0:
                logger.info(f"  已处理 {self.stats['processed']}/{self.stats['total_events']}")
            
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
        
        for i, event in enumerate(events):
            result = await self.process_single_event(event)
            results.append(result)
            
            # 显示进度
            if (i + 1) % 3 == 0:
                logger.info(f"  进度: {i + 1}/{len(events)}")
            
            # 短暂延迟
            if i < len(events) - 1:
                await asyncio.sleep(0.1)
        
        logger.info(f"✅ 批量处理完成: {len(results)} 个结果")
        return results
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析处理结果"""
        logger.info(f"📊 分析 {len(results)} 个处理结果...")
        
        # 1. 组件使用统计
        logger.info("🔧 组件使用统计:")
        for component, count in sorted(self.stats["components_verified"].items()):
            percentage = count / self.stats["processed"] * 100 if self.stats["processed"] > 0 else 0
            logger.info(f"  {component}: {count} ({percentage:.1f}%)")
        
        # 2. 判重效果
        deduplication_checked = sum(1 for r in results if r.get('deduplication_checked', False))
        duplicates_prevented = sum(1 for r in results if r.get('duplicate_prevented', False))
        
        logger.info("🔄 判重效果:")
        logger.info(f"  判重检查次数: {deduplication_checked}")
        logger.info(f"  阻止重复创建: {duplicates_prevented}")
        if deduplication_checked > 0:
            logger.info(f"  判重有效率: {duplicates_prevented/deduplication_checked*100:.1f}%")
        
        # 3. 执行路径分析
        execution_paths = defaultdict(int)
        for result in results:
            path = result.get('execution_path', 'unknown')
            execution_paths[path] += 1
        
        logger.info("🛣️ 执行路径分布:")
        for path, count in sorted(execution_paths.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {path}: {count} ({percentage:.1f}%)")
        
        # 4. 状态分布
        status_counts = defaultdict(int)
        for result in results:
            status = result.get('status', 'unknown')
            status_counts[status] += 1
        
        logger.info("📈 处理状态分布:")
        for status, count in sorted(status_counts.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {status}: {count} ({percentage:.1f}%)")
        
        # 5. 性能分析
        if self.stats["processing_times"]:
            avg_time = statistics.mean(self.stats["processing_times"])
            logger.info("⏱️ 性能分析:")
            logger.info(f"  平均处理时间: {avg_time:.1f}ms")
            logger.info(f"  目标 (<2秒): {'✅ 达标' if avg_time < 2000 else '❌ 超标'}")
        
        # 6. 引擎信息
        try:
            engine_info = self.engine.get_engine_info()
            logger.info("🔍 引擎信息:")
            logger.info(f"  版本: {engine_info.get('engine_version')}")
            logger.info(f"  缓存大小: {engine_info.get('cache_size')}")
        except:
            pass
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存测试结果"""
        results_dir = Path("evaluate_service/data/results/new_integration_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"new_integration_results_{timestamp}.json"
        
        output_data = {
            "metadata": {
                "test_type": "新集成测试（优化版引擎）",
                "test_time": datetime.now().isoformat(),
                "dataset_size": self.stats["total_events"],
                "test_focus": "组件整合验证"
            },
            "statistics": self.stats,
            "detailed_results": results,
            "engine_info": self.engine.get_engine_info() if hasattr(self.engine, 'get_engine_info') else {},
            "summary": {
                "total_processed": self.stats["processed"],
                "success_rate": self.stats["processed"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "components_verified": dict(self.stats["components_verified"]),
                "duplicates_prevented": self.stats["duplicates_prevented"],
                "avg_processing_time_ms": statistics.mean(self.stats["processing_times"]) if self.stats["processing_times"] else 0
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file

async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 新集成测试：验证优化版引擎组件整合")
    print("=" * 70)
    
    tester = NewIntegrationTest()
    
    try:
        # 1. 初始化组件
        init_success = await tester.initialize_components()
        if not init_success:
            print("❌ 组件初始化失败，无法继续测试")
            return 1
        
        # 2. 加载测试数据
        events = await tester.load_test_data(sample_size=10)
        if not events:
            print("❌ 没有测试数据，无法继续")
            return 1
        
        print(f"📊 测试规模: {len(events)} 个事件")
        print("🎯 测试重点: 组件整合和判重功能")
        
        # 3. 处理事件
        print("\n🔍 注意：将使用真实AI API")
        confirm = input("是否继续？ (y/n): ")
        
        if confirm.lower() != 'y':
            print("测试取消")
            return 0
        
        print("🚀 开始处理...")
        results = await tester.process_batch(events)
        
        # 4. 分析结果
        tester.analyze_results(results)
        
        # 5. 保存结果
        results_file = tester.save_results(results)
        
        print("\n" + "=" * 70)
        print("✅ 新集成测试完成！")
        print("=" * 70)
        
        # 关键指标
        print(f"📊 关键结果:")
        print(f"  总事件数: {tester.stats['total_events']}")
        print(f"  成功处理: {tester.stats['processed']}")
        print(f"  判重检查次数: {sum(1 for r in results if r.get('deduplication_checked', False))}")
        print(f"  阻止重复: {tester.stats['duplicates_prevented']}")
        
        # 组件使用情况
        print(f"🔧 组件使用:")
        for component in ['theme_fetcher', 'dedup_engine']:
            used_key = f"{component}_used"
            if used_key in tester.stats["components_verified"]:
                count = tester.stats["components_verified"][used_key]
                print(f"  {component}: {count}/{tester.stats['processed']}")
        
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