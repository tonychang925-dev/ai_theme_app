#!/usr/bin/env python3
"""
第一步：集成验证脚本
验证所有增强组件能否协同工作，处理76条测试数据
"""
import json
import asyncio
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class IntegrationVerifier:
    """集成验证器 - 验证所有组件协同工作"""
    
    def __init__(self):
        self.stats = {
            "total_events": 0,
            "processed": 0,
            "components_initialized": [],
            "errors": [],
            "processing_times": []
        }
        
    async def initialize_components(self) -> bool:
        """初始化所有必要组件"""
        logger.info("🔧 开始初始化增强架构组件...")
        
        try:
            # 1. 初始化EnhancedAIThemeClient
            from theme_service.enhanced_ai_client import EnhancedAIThemeClient
            self.ai_client = EnhancedAIThemeClient(settings={'USE_ENHANCED_MODE': True})
            self.stats["components_initialized"].append("EnhancedAIThemeClient")
            logger.info("✅ EnhancedAIThemeClient 初始化成功")
            
            # 2. 初始化EnhancedThemeDiscoveryEngine
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            self.engine = EnhancedThemeDiscoveryEngine(
                ai_client=self.ai_client,
                db_manager=None,  # 测试时不连接真实数据库
                config={
                    'fast_track_threshold': 0.85,
                    'review_threshold': 0.65,
                    'ignore_threshold': 0.3
                }
            )
            self.stats["components_initialized"].append("EnhancedThemeDiscoveryEngine")
            logger.info("✅ EnhancedThemeDiscoveryEngine 初始化成功")
            
            # 3. 测试组件连通性
            test_result = await self._test_component_connectivity()
            if not test_result:
                raise Exception("组件连通性测试失败")
                
            logger.info(f"✅ 所有 {len(self.stats['components_initialized'])} 个组件初始化成功")
            return True
            
        except ImportError as e:
            logger.error(f"❌ 导入组件失败: {e}")
            logger.info("尝试备用导入路径...")
            
            # 尝试备用导入
            try:
                theme_service_path = project_root / "theme_service"
                if theme_service_path.exists():
                    sys.path.insert(0, str(theme_service_path))
                
                from enhanced_ai_client import EnhancedAIThemeClient
                from enhanced_theme_discovery import EnhancedThemeDiscoveryEngine
                
                self.ai_client = EnhancedAIThemeClient({'USE_ENHANCED_MODE': True})
                self.engine = EnhancedThemeDiscoveryEngine(ai_client=self.ai_client)
                logger.info("✅ 从theme_service目录导入成功")
                return True
                
            except ImportError as e2:
                logger.error(f"❌ 所有导入尝试都失败: {e2}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 初始化组件失败: {e}")
            self.stats["errors"].append(f"初始化失败: {str(e)}")
            return False
    
    async def _test_component_connectivity(self) -> bool:
        """测试组件连通性"""
        try:
            # 创建测试事件
            test_event = {
                "id": "integration_test_001",
                "title": "测试组件连通性",
                "summary": "测试增强架构组件协同工作",
                "event_type": "技术突破",
                "impact_industries": ["测试行业"],
                "theme_directive": {
                    "action": "CREATE_NEW",
                    "confidence": 0.9,
                    "reason": "测试事件"
                }
            }
            
            # 测试EnhancedThemeDiscoveryEngine处理
            result = await self.engine.process_single_event(test_event)
            
            if result and result.get('status') in ['created', 'merged', 'ignored']:
                logger.info(f"✅ 组件连通性测试成功: {result.get('status')}")
                return True
            else:
                logger.warning(f"⚠️ 组件连通性测试返回异常状态: {result}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 组件连通性测试失败: {e}")
            return False
    
    async def load_test_data(self) -> List[Dict[str, Any]]:
        """加载测试数据"""
        data_path = Path("evaluate_service/data/processed/validation_events_enhanced_v2.json")
        
        if not data_path.exists():
            logger.error(f"❌ 测试数据文件不存在: {data_path}")
            raise FileNotFoundError(f"测试数据文件不存在: {data_path}")
        
        logger.info(f"📂 加载测试数据: {data_path}")
        
        with open(data_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        events = data.get("events", [])
        metadata = data.get("metadata", {})
        
        logger.info(f"✅ 加载成功: {len(events)} 个结构化事件")
        logger.info(f"   数据版本: {metadata.get('version', 'unknown')}")
        logger.info(f"   平均置信度: {metadata.get('stats', {}).get('avg_confidence', 0):.3f}")
        
        # 确保每个事件都有id
        for event in events:
            if 'id' not in event:
                event['id'] = event.get('news_id', 'unknown')
        
        self.stats["total_events"] = len(events)
        return events
    
    async def process_single_event_real(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """使用真实引擎处理单个事件"""
        start_time = datetime.now()
        
        try:
            # 调用真实的EnhancedThemeDiscoveryEngine
            result = await self.engine.process_single_event(event)
            
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            self.stats["processing_times"].append(processing_time)
            
            # 提取关键信息
            status = result.get('status', 'unknown')
            
            # 简化结果，便于分析
            simplified_result = {
                'event_id': event.get('id'),
                'original_theme': event.get('original_data', {}).get('theme', 'unknown'),
                'original_action': event.get('theme_directive', {}).get('action', 'CLUSTER'),
                'final_decision': result.get('ai_decision', {}).get('decision', 'UNKNOWN'),
                'final_theme': result.get('execution_result', {}).get('target_theme_name', '') 
                                or result.get('execution_result', {}).get('new_theme_name', '未知'),
                'status': status,
                'processing_time_ms': processing_time,
                'execution_path': result.get('execution_path', 'unknown')
            }
            
            self.stats["processed"] += 1
            
            # 进度显示
            if self.stats["processed"] % 10 == 0:
                logger.info(f"  已处理 {self.stats['processed']}/{self.stats['total_events']} 个事件")
            
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
        batch_size = 5  # 小批量处理
        
        for i in range(0, len(events), batch_size):
            batch = events[i:i + batch_size]
            batch_results = []
            
            for event in batch:
                result = await self.process_single_event_real(event)
                batch_results.append(result)
            
            results.extend(batch_results)
            
            # 显示批次统计
            batch_stats = {
                'created': sum(1 for r in batch_results if r.get('status') == 'created'),
                'merged': sum(1 for r in batch_results if r.get('status') == 'merged'),
                'failed': sum(1 for r in batch_results if r.get('status') == 'error')
            }
            logger.info(f"  批次完成: {i + len(batch)}/{len(events)} "
                       f"(创建: {batch_stats['created']}, 归并: {batch_stats['merged']}, 失败: {batch_stats['failed']})")
            
            # 短暂延迟
            if i + batch_size < len(events):
                await asyncio.sleep(0.1)
        
        logger.info(f"✅ 批量处理完成: {len(results)} 个结果")
        return results
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析处理结果"""
        logger.info(f"📊 分析 {len(results)} 个处理结果...")
        
        # 1. 状态分布
        status_counts = {}
        for result in results:
            status = result.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        logger.info("处理状态分布:")
        for status, count in sorted(status_counts.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {status}: {count} ({percentage:.1f}%)")
        
        # 2. 决策分布
        decision_counts = {}
        theme_counts = {}
        
        for result in results:
            decision = result.get('final_decision', 'UNKNOWN')
            theme = result.get('final_theme', '未知')
            
            decision_counts[decision] = decision_counts.get(decision, 0) + 1
            if theme and theme != '未知':
                theme_counts[theme] = theme_counts.get(theme, 0) + 1
        
        logger.info("最终决策分布:")
        for decision, count in sorted(decision_counts.items()):
            percentage = count / len(results) * 100
            logger.info(f"  {decision}: {count} ({percentage:.1f}%)")
        
        logger.info(f"生成的不同题材数: {len(theme_counts)}")
        if theme_counts:
            logger.info("题材分布 (前10):")
            for theme, count in sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
                logger.info(f"  {theme}: {count}")
        
        # 3. 性能统计
        if self.stats["processing_times"]:
            import statistics
            avg_time = statistics.mean(self.stats["processing_times"])
            logger.info(f"⚡ 平均处理时间: {avg_time:.1f}ms")
            logger.info(f"   单事件处理目标 (<2秒): {'✅' if avg_time < 2000 else '❌'}")
        
        # 4. 错误分析
        if self.stats["errors"]:
            logger.warning(f"⚠️  发现 {len(self.stats['errors'])} 个错误")
            for error in self.stats["errors"][:5]:  # 只显示前5个错误
                logger.warning(f"  错误: {error}")
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存处理结果"""
        results_dir = Path("evaluate_service/data/results/integration_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"integration_results_{timestamp}.json"
        
        output_data = {
            "metadata": {
                "test_type": "增强架构集成测试",
                "test_time": datetime.now().isoformat(),
                "dataset_size": self.stats["total_events"],
                "components_used": self.stats["components_initialized"]
            },
            "statistics": self.stats,
            "results": results,
            "summary": {
                "total_processed": self.stats["processed"],
                "success_rate": self.stats["processed"] / self.stats["total_events"] if self.stats["total_events"] > 0 else 0,
                "components_initialized": len(self.stats["components_initialized"]),
                "error_count": len(self.stats["errors"])
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file
    
    def generate_report(self, results_file: Path):
        """生成测试报告"""
        report_dir = Path("evaluate_service/data/results/integration_test/reports")
        report_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_file = report_dir / f"integration_report_{timestamp}.txt"
        
        with open(results_file, 'r', encoding='utf-8') as f:
            results_data = json.load(f)
        
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("增强架构集成测试报告\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"📅 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"📊 数据集: {results_data['metadata']['dataset_size']} 个事件\n")
            f.write(f"🔧 使用组件: {', '.join(results_data['metadata']['components_used'])}\n\n")
            
            stats = results_data["statistics"]
            summary = results_data["summary"]
            
            f.write("📈 处理统计:\n")
            f.write("-" * 50 + "\n")
            f.write(f"总事件数: {stats['total_events']}\n")
            f.write(f"成功处理: {stats['processed']}\n")
            f.write(f"成功率: {summary['success_rate']:.1%}\n")
            f.write(f"组件初始化: {summary['components_initialized']} 个\n")
            f.write(f"错误数量: {summary['error_count']}\n\n")
            
            # 分析结果
            f.write("🎯 处理结果分析:\n")
            f.write("-" * 50 + "\n")
            
            # 计算决策分布
            decision_counts = {}
            for result in results_data["results"]:
                decision = result.get('final_decision', 'UNKNOWN')
                decision_counts[decision] = decision_counts.get(decision, 0) + 1
            
            for decision, count in sorted(decision_counts.items()):
                percentage = count / len(results_data["results"]) * 100
                f.write(f"{decision}: {count} ({percentage:.1f}%)\n")
        
        logger.info(f"📋 测试报告生成: {report_file}")

async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 第一阶段：增强架构集成测试")
    print("验证所有组件协同工作，处理76条测试数据")
    print("=" * 70)
    
    verifier = IntegrationVerifier()
    
    try:
        # 1. 初始化组件
        init_success = await verifier.initialize_components()
        if not init_success:
            print("❌ 组件初始化失败，无法继续测试")
            return 1
        
        # 2. 加载测试数据
        events = await verifier.load_test_data()
        if not events:
            print("❌ 没有测试数据，无法继续")
            return 1
        
        # 3. 处理事件
        results = await verifier.process_batch(events)
        
        # 4. 分析结果
        verifier.analyze_results(results)
        
        # 5. 保存结果
        results_file = verifier.save_results(results)
        
        # 6. 生成报告
        verifier.generate_report(results_file)
        
        print("\n" + "=" * 70)
        print("✅ 第一阶段集成测试完成！")
        print("=" * 70)
        print(f"📊 关键结果:")
        print(f"  总事件数: {verifier.stats['total_events']}")
        print(f"  成功处理: {verifier.stats['processed']}")
        print(f"  使用组件: {len(verifier.stats['components_initialized'])} 个")
        print(f"  结果文件: {results_file}")
        
        if verifier.stats["errors"]:
            print(f"⚠️  发现 {len(verifier.stats['errors'])} 个错误，请检查日志")
        else:
            print("✅ 无错误发生")
        
        return 0
        
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())