#!/usr/bin/env python3
"""
更新版集成测试 - 使用优化判重配置
测试EnhancedThemeDiscoveryEngine的完整流程
"""
import json
import asyncio
import sys
from pathlib import Path
from typing import Dict, Any, List
import logging
from collections import defaultdict
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

# 最佳判重配置（从测试结果中获取）
OPTIMIZED_DEDUP_CONFIG = {
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

class EnhancedIntegrationTest:
    """增强版集成测试 - 使用优化判重配置"""
    
    def __init__(self):
        self.results = []
        self.stats = defaultdict(int)
        
    def create_test_events(self) -> List[Dict[str, Any]]:
        """创建测试事件，特别关注可能重复的事件"""
        test_events = []
        
        # 1. 重复题材测试 - AI相关
        test_events.append({
            "id": "test_ai_001",
            "title": "AI智能眼镜发布，引领可穿戴设备新潮流",
            "summary": "某公司发布最新AI智能眼镜，集成了语音助手、AR导航等功能",
            "impact_industries": ["消费电子", "人工智能", "可穿戴设备"],
            "event_type": "产品发布",
            "importance": 8
        })
        
        test_events.append({
            "id": "test_ai_002",
            "title": "人工智能眼镜技术突破，实现实时翻译",
            "summary": "新型AI眼镜实现实时多语言翻译，打破语言障碍",
            "impact_industries": ["人工智能", "消费电子", "翻译服务"],
            "event_type": "技术突破",
            "importance": 7
        })
        
        test_events.append({
            "id": "test_ai_003", 
            "title": "智能拍摄眼镜上市，AI辅助摄影",
            "summary": "配备AI摄影辅助功能的智能眼镜正式上市",
            "impact_industries": ["消费电子", "人工智能", "摄影"],
            "event_type": "产品上市",
            "importance": 6
        })
        
        # 2. 新能源汽车相关（测试包含关系）
        test_events.append({
            "id": "test_ev_001",
            "title": "新能源汽车销量创新高",
            "summary": "新能源汽车月度销量突破历史记录",
            "impact_industries": ["新能源汽车", "汽车制造"],
            "event_type": "行业数据",
            "importance": 8
        })
        
        test_events.append({
            "id": "test_ev_002",
            "title": "新能源车电池技术突破，续航达1000公里",
            "summary": "新型固态电池技术使电动车续航大幅提升",
            "impact_industries": ["新能源汽车", "电池", "新材料"],
            "event_type": "技术突破",
            "importance": 9
        })
        
        # 3. 半导体芯片相关
        test_events.append({
            "id": "test_chip_001",
            "title": "人工智能芯片研发成功",
            "summary": "国内企业成功研发高性能人工智能专用芯片",
            "impact_industries": ["半导体", "人工智能", "芯片"],
            "event_type": "技术突破",
            "importance": 9
        })
        
        test_events.append({
            "id": "test_chip_002",
            "title": "AI计算芯片市场需求激增",
            "summary": "随着AI应用普及，AI芯片市场需求快速增长",
            "impact_industries": ["半导体", "人工智能", "云计算"],
            "event_type": "市场动态",
            "importance": 7
        })
        
        # 4. 完全不同的题材（应该创建新题材）
        test_events.append({
            "id": "test_unique_001",
            "title": "新型光伏材料效率提升至30%",
            "summary": "钙钛矿光伏电池效率创下新纪录",
            "impact_industries": ["光伏", "新能源", "新材料"],
            "event_type": "技术突破",
            "importance": 8
        })
        
        logger.info(f"📋 创建了 {len(test_events)} 个测试事件，包含重复和唯一题材")
        return test_events
    
    async def run_integration_test(self):
        """运行集成测试"""
        logger.info("🚀 开始增强版集成测试（使用优化判重配置）...")
        
        try:
            # 导入引擎
            from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
            from theme_service.theme_fetcher import ThemeFetcher
            
            # 创建使用优化配置的引擎
            discovery_engine = EnhancedThemeDiscoveryEngine(
                config={
                    'fast_track_threshold': 0.95,  # 提高阈值，让更多事件进入guided_create
                    'review_threshold': 0.65,
                    'ignore_threshold': 0.3,
                    'dedup_config': OPTIMIZED_DEDUP_CONFIG  # 使用优化判重配置
                }
            )
            
            # 创建主题获取器（模拟）
            theme_fetcher = ThemeFetcher()
            
            test_events = self.create_test_events()
            all_results = []
            
            # 依次处理每个事件
            for i, event in enumerate(test_events):
                logger.info(f"\n🔍 处理事件 {i+1}/{len(test_events)}: {event['title']}")
                
                try:
                    # 获取现有题材（模拟）
                    existing_themes = await theme_fetcher.fetch_themes(limit=20)
                    
                    # 处理事件
                    result = await discovery_engine.process_event(
                        event_data=event,
                        existing_themes=existing_themes
                    )
                    
                    # 记录结果
                    result_dict = {
                        "event_id": event["id"],
                        "event_title": event["title"],
                        "event_industries": event["impact_industries"],
                        "decision": result.decision.value if result.decision else None,
                        "decision_confidence": result.decision_confidence,
                        "execution_path": result.execution_path,
                        "theme_name": result.theme_name,
                        "theme_id": result.theme_id,
                        "reason": result.reason,
                        "dedup_checked": result.dedup_checked,
                        "dedup_result": result.dedup_result.to_dict() if result.dedup_result else None,
                        "processing_time": result.processing_time
                    }
                    
                    all_results.append(result_dict)
                    
                    # 更新统计
                    self.stats["total_events"] += 1
                    self.stats[result.execution_path] = self.stats.get(result.execution_path, 0) + 1
                    
                    if result.dedup_checked:
                        self.stats["dedup_checks"] += 1
                        if result.dedup_result and result.dedup_result.should_merge:
                            self.stats["duplicates_detected"] += 1
                    
                    # 显示处理结果
                    logger.info(f"  决策: {result.decision.value if result.decision else '无'} "
                              f"(置信度: {result.decision_confidence:.2f})")
                    logger.info(f"  执行路径: {result.execution_path}")
                    if result.dedup_checked and result.dedup_result:
                        if result.dedup_result.should_merge:
                            logger.info(f"  🔄 判重结果: 合并到 {result.dedup_result.target_theme.get('name')} "
                                      f"(相似度: {result.dedup_result.similarity_score:.2f})")
                        else:
                            logger.info(f"  ✅ 判重结果: 未发现重复，可创建新题材")
                    
                except Exception as e:
                    logger.error(f"❌ 处理事件 {event['id']} 失败: {e}")
                    import traceback
                    traceback.print_exc()
                    
                    error_result = {
                        "event_id": event["id"],
                        "error": str(e),
                        "traceback": traceback.format_exc()
                    }
                    all_results.append(error_result)
                
                # 短暂延迟
                await asyncio.sleep(0.3)
            
            return all_results
            
        except Exception as e:
            logger.error(f"❌ 集成测试初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def analyze_results(self, results: List[Dict[str, Any]]):
        """分析测试结果"""
        logger.info(f"\n📊 分析 {len(results)} 个测试结果...")
        
        # 1. 执行路径分布
        logger.info("🛣️ 执行路径分布:")
        for path, count in self.stats.items():
            if path not in ["total_events", "dedup_checks", "duplicates_detected"]:
                percentage = count / self.stats["total_events"] * 100 if self.stats["total_events"] > 0 else 0
                logger.info(f"  {path}: {count} ({percentage:.1f}%)")
        
        # 2. 判重统计
        logger.info("🔍 判重功能统计:")
        logger.info(f"  判重检查次数: {self.stats.get('dedup_checks', 0)}")
        logger.info(f"  检测到的重复数: {self.stats.get('duplicates_detected', 0)}")
        
        dedup_check_rate = self.stats.get('dedup_checks', 0) / self.stats["total_events"] * 100 if self.stats["total_events"] > 0 else 0
        logger.info(f"  判重检查率: {dedup_check_rate:.1f}%")
        
        # 3. 决策分布
        decisions = defaultdict(int)
        for result in results:
            if "decision" in result and result["decision"]:
                decisions[result["decision"]] += 1
        
        if decisions:
            logger.info("🎯 决策类型分布:")
            for decision, count in decisions.items():
                percentage = count / len(results) * 100
                logger.info(f"  {decision}: {count} ({percentage:.1f}%)")
        
        # 4. 详细查看判重结果
        dedup_results = [r for r in results if r.get("dedup_checked", False) and r.get("dedup_result")]
        if dedup_results:
            logger.info("\n🔬 判重结果详情:")
            for i, result in enumerate(dedup_results[:3]):  # 只显示前3个
                dedup_info = result.get("dedup_result", {})
                if dedup_info.get("should_merge"):
                    logger.info(f"  {i+1}. {result.get('event_title', '未知事件')[:30]}...")
                    logger.info(f"     合并到: {dedup_info.get('target_theme', {}).get('name', '未知')}")
                    logger.info(f"     相似度: {dedup_info.get('similarity_score', 0):.2f}")
                    logger.info(f"     匹配类型: {dedup_info.get('match_type', '未知')}")
    
    def save_results(self, results: List[Dict[str, Any]]):
        """保存测试结果"""
        results_dir = Path("evaluate_service/data/results/enhanced_integration_test")
        results_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = results_dir / f"enhanced_integration_results_{timestamp}.json"
        
        output_data = {
            "metadata": {
                "test_type": "增强版集成测试（使用优化判重配置）",
                "test_time": datetime.now().isoformat(),
                "test_config": {
                    "fast_track_threshold": 0.95,
                    "review_threshold": 0.65,
                    "ignore_threshold": 0.3,
                    "dedup_config_used": "OPTIMIZED_DEDUP_CONFIG"
                }
            },
            "statistics": dict(self.stats),
            "test_results": results,
            "summary": {
                "total_events": self.stats.get("total_events", 0),
                "dedup_check_rate": self.stats.get("dedup_checks", 0) / self.stats.get("total_events", 1) * 100,
                "duplicate_detection_rate": self.stats.get("duplicates_detected", 0) / max(self.stats.get("dedup_checks", 1), 1) * 100
            }
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"💾 结果保存至: {output_file}")
        return output_file

async def main():
    """主函数"""
    print("=" * 70)
    print("🚀 增强版集成测试（使用优化判重配置）")
    print("验证判重功能在实际集成中的效果")
    print("=" * 70)
    
    tester = EnhancedIntegrationTest()
    
    try:
        # 运行集成测试
        print("🔧 开始测试...")
        results = await tester.run_integration_test()
        
        if not results:
            print("❌ 未获取到测试结果")
            return 1
        
        # 分析结果
        tester.analyze_results(results)
        
        # 保存结果
        results_file = tester.save_results(results)
        
        print("\n" + "=" * 70)
        print("✅ 增强版集成测试完成！")
        print("=" * 70)
        
        # 关键指标
        total_events = tester.stats.get("total_events", 0)
        dedup_checks = tester.stats.get("dedup_checks", 0)
        duplicates_detected = tester.stats.get("duplicates_detected", 0)
        
        print(f"📊 关键指标:")
        print(f"  处理事件总数: {total_events}")
        print(f"  判重检查次数: {dedup_checks}")
        print(f"  检测到的重复: {duplicates_detected}")
        
        if dedup_checks > 0:
            print(f"  判重检查率: {dedup_checks/total_events*100:.1f}%")
            print(f"  重复检测率: {duplicates_detected/dedup_checks*100:.1f}%")
        
        if dedup_checks == 0:
            print("\n⚠️ 警告: 判重引擎仍然没有被调用！")
            print("可能的原因:")
            print("  1. 执行路径决策仍将所有事件导向guided_merge")
            print("  2. AI决策置信度过高，跳过了guided_create路径")
            print("  3. 系统配置需要进一步调整")
        elif duplicates_detected > 0:
            print(f"\n✅ 成功: 判重功能正常工作，检测到 {duplicates_detected} 个重复！")
        
        return 0
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    asyncio.run(main())