"""
主题编排器 - 统一入口，智能路由
根据配置和事件特性选择处理引擎
"""
import logging
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class EngineType(Enum):
    """引擎类型枚举"""
    LEGACY = "legacy"          # 传统批量聚类引擎
    ENHANCED = "enhanced"      # 增强即时归并引擎
    HYBRID = "hybrid"          # 混合模式
    FALLBACK = "fallback"      # 降级引擎


class ProcessingMode(Enum):
    """处理模式枚举"""
    LEGACY_ONLY = "legacy_only"      # 仅使用传统引擎
    ENHANCED_ONLY = "enhanced_only"  # 仅使用增强引擎
    HYBRID = "hybrid"                # 混合模式（智能路由）
    SHADOW = "shadow"                # 影子模式（并行运行，只记录）


class ThemeOrchestrator:
    """
    主题编排器 - 智能路由和管理多个处理引擎
    
    核心功能：
    1. 根据配置和事件特性智能选择处理引擎
    2. 支持渐进式发布和特性开关
    3. 提供监控和统计功能
    4. 实现降级和容错机制
    """
    
    def __init__(self, config: Dict[str, Any], ai_client, db_manager=None):
        """
        初始化编排器
        
        Args:
            config: 配置参数
            ai_client: AI客户端
            db_manager: 数据库管理器
        """
        self.config = config
        self.ai_client = ai_client
        self.db = db_manager
        
        # 运行模式
        self.mode = self._get_processing_mode()
        
        # 初始化引擎
        self.engines = self._initialize_engines()
        
        # 状态追踪
        self.stats = {
            "total_processed": 0,
            "by_engine": defaultdict(int),
            "by_mode": defaultdict(int),
            "successful": 0,
            "failed": 0,
            "fallback_triggered": 0,
            "start_time": datetime.now()
        }
        
        # 性能监控
        self.performance_stats = {
            "avg_processing_time_ms": 0,
            "total_processing_time_ms": 0,
            "peak_processing_time_ms": 0
        }
        
        # 特征开关
        self.feature_flags = self.config.get('feature_flags', {})
        
        logger.info(f"ThemeOrchestrator 初始化完成，模式: {self.mode.value}")
    
    def _get_processing_mode(self) -> ProcessingMode:
        """获取处理模式"""
        mode_str = self.config.get('processing_mode', 'hybrid')
        
        mode_map = {
            'legacy_only': ProcessingMode.LEGACY_ONLY,
            'enhanced_only': ProcessingMode.ENHANCED_ONLY,
            'hybrid': ProcessingMode.HYBRID,
            'shadow': ProcessingMode.SHADOW
        }
        
        return mode_map.get(mode_str, ProcessingMode.HYBRID)
    
    def _initialize_engines(self) -> Dict[EngineType, Any]:
        """初始化所有引擎"""
        engines = {}
        
        try:
            # 初始化传统引擎
            if self.mode in [ProcessingMode.LEGACY_ONLY, ProcessingMode.HYBRID, ProcessingMode.SHADOW]:
                from theme_service.theme_discovery import ThemeDiscoveryEngine
                engines[EngineType.LEGACY] = ThemeDiscoveryEngine(self.ai_client, self.db)
                logger.info("传统引擎初始化成功")
        except ImportError as e:
            logger.warning(f"无法导入传统引擎: {e}")
        
        try:
            # 初始化增强引擎
            if self.mode in [ProcessingMode.ENHANCED_ONLY, ProcessingMode.HYBRID, ProcessingMode.SHADOW]:
                from theme_service.enhanced_theme_discovery_0113 import EnhancedThemeDiscoveryEngine
                enhanced_config = self.config.get('enhanced_config', {})
                engines[EngineType.ENHANCED] = EnhancedThemeDiscoveryEngine(
                    self.ai_client, self.db, enhanced_config
                )
                logger.info("增强引擎初始化成功")
        except ImportError as e:
            logger.warning(f"无法导入增强引擎: {e}")
        
        # 确保至少有一个引擎
        if not engines:
            logger.error("没有可用的引擎，创建降级引擎")
            engines[EngineType.FALLBACK] = self._create_fallback_engine()
        
        return engines
    
    def _create_fallback_engine(self):
        """创建降级引擎"""
        class FallbackEngine:
            async def process_single_event(self, event):
                return {
                    'event_id': event.get('id'),
                    'status': 'fallback',
                    'reason': '所有引擎均不可用',
                    'timestamp': datetime.now().isoformat()
                }
        
        return FallbackEngine()
    
    async def process_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个事件 - 智能路由
        
        Args:
            event: 事件数据
            
        Returns:
            处理结果
        """
        event_id = event.get('id', 'unknown')
        self.stats["total_processed"] += 1
        
        logger.info(f"开始处理事件 {event_id}，当前模式: {self.mode.value}")
        
        start_time = datetime.now()
        
        try:
            # 选择处理引擎
            selected_engine, selection_reason = self._select_engine(event)
            
            # 记录选择
            self.stats["by_engine"][selected_engine.value] += 1
            self.stats["by_mode"][self.mode.value] += 1
            
            logger.info(f"事件 {event_id} 路由到 {selected_engine.value} 引擎，原因: {selection_reason}")
            
            # 执行处理
            if self.mode == ProcessingMode.SHADOW:
                # 影子模式：并行运行，只记录不生效
                result = await self._process_in_shadow_mode(event, selected_engine)
            else:
                # 正常模式
                result = await self._process_with_engine(event, selected_engine)
            
            # 计算处理时间
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            result['processing_time_ms'] = processing_time
            result['selected_engine'] = selected_engine.value
            result['selection_reason'] = selection_reason
            
            # 更新性能统计
            self._update_performance_stats(processing_time)
            
            # 记录成功
            self.stats["successful"] += 1
            result['status'] = 'success'
            
            # 记录决策日志
            await self._log_decision(event, result, selected_engine)
            
            logger.info(f"事件 {event_id} 处理成功，用时: {processing_time:.0f}ms")
            
            return result
            
        except Exception as e:
            # 处理失败
            processing_time = (datetime.now() - start_time).total_seconds() * 1000
            error_result = self._create_error_result(event, e, processing_time)
            
            # 尝试降级处理
            fallback_result = await self._try_fallback_processing(event, e)
            if fallback_result:
                error_result['fallback_result'] = fallback_result
                error_result['status'] = 'fallback_success'
                self.stats["fallback_triggered"] += 1
            else:
                self.stats["failed"] += 1
            
            # 记录错误
            await self._log_error(event, error_result)
            
            logger.error(f"事件 {event_id} 处理失败: {e}")
            
            return error_result
    
    def _select_engine(self, event: Dict[str, Any]) -> Tuple[EngineType, str]:
        """
        智能选择处理引擎
        
        Returns:
            (引擎类型, 选择原因)
        """
        # 根据模式决定
        if self.mode == ProcessingMode.LEGACY_ONLY:
            return EngineType.LEGACY, "legacy_only模式"
        
        if self.mode == ProcessingMode.ENHANCED_ONLY:
            return EngineType.ENHANCED, "enhanced_only模式"
        
        if self.mode == ProcessingMode.SHADOW:
            # 影子模式下使用增强引擎进行测试
            return EngineType.ENHANCED, "shadow测试模式"
        
        # 混合模式：根据事件特征智能选择
        return self._select_engine_intelligently(event)
    
    def _select_engine_intelligently(self, event: Dict[str, Any]) -> Tuple[EngineType, str]:
        """智能选择引擎（混合模式）"""
        
        # 检查事件是否包含theme_directive
        if 'theme_directive' not in event:
            return EngineType.LEGACY, "事件缺少theme_directive字段"
        
        directive = event.get('theme_directive', {})
        action = directive.get('action', 'CLUSTER')
        confidence = directive.get('confidence', 0)
        
        # 规则1：重大事件使用增强引擎
        if self._is_major_event(event):
            if EngineType.ENHANCED in self.engines:
                return EngineType.ENHANCED, "重大事件，使用增强引擎"
        
        # 规则2：高置信度的CREATE_NEW指令使用增强引擎
        if action == 'CREATE_NEW' and confidence > 0.7:
            if EngineType.ENHANCED in self.engines:
                return EngineType.ENHANCED, f"高置信度CREATE_NEW指令(置信度: {confidence})"
        
        # 规则3：高置信度的CLUSTER指令使用传统引擎
        if action == 'CLUSTER' and confidence > 0.8:
            if EngineType.LEGACY in self.engines:
                return EngineType.LEGACY, f"高置信度CLUSTER指令(置信度: {confidence})"
        
        # 规则4：基于事件类型
        event_type = event.get('event_type', '')
        if event_type in ['政策发布', '技术突破', '重大合作']:
            if EngineType.ENHANCED in self.engines:
                return EngineType.ENHANCED, f"事件类型: {event_type}"
        
        # 默认：使用传统引擎（更稳定）
        if EngineType.LEGACY in self.engines:
            return EngineType.LEGACY, "默认选择传统引擎"
        elif EngineType.ENHANCED in self.engines:
            return EngineType.ENHANCED, "传统引擎不可用，使用增强引擎"
        else:
            return EngineType.FALLBACK, "所有引擎均不可用，使用降级引擎"
    
    def _is_major_event(self, event: Dict[str, Any]) -> bool:
        """判断是否为重大事件"""
        major_keywords = ["国务院", "国家", "重大突破", "首次", "革命性", "里程碑", "世界级"]
        event_type = event.get('event_type', '')
        title = event.get('title', '')
        
        is_major_type = event_type in ["政策发布", "技术突破", "重大合作"]
        has_major_keyword = any(kw in title for kw in major_keywords)
        
        return is_major_type or has_major_keyword
    
    async def _process_with_engine(self, event: Dict[str, Any], 
                                  engine_type: EngineType) -> Dict[str, Any]:
        """使用指定引擎处理事件"""
        engine = self.engines.get(engine_type)
        
        if not engine:
            raise Exception(f"引擎 {engine_type.value} 不可用")
        
        # 调用引擎的process_single_event方法
        result = await engine.process_single_event(event)
        
        # 添加引擎类型信息
        result['engine_type'] = engine_type.value
        
        return result
    
    async def _process_in_shadow_mode(self, event: Dict[str, Any],
                                    selected_engine: EngineType) -> Dict[str, Any]:
        """
        影子模式处理：并行运行新旧引擎，只记录不生效
        
        Args:
            event: 事件数据
            selected_engine: 选中的引擎
            
        Returns:
            处理结果（使用传统引擎的结果）
        """
        shadow_results = {}
        
        # 使用选中的引擎处理（不生效）
        if selected_engine in self.engines:
            shadow_engine = self.engines[selected_engine]
            shadow_result = await shadow_engine.process_single_event(event)
            shadow_results['shadow'] = shadow_result
        
        # 使用传统引擎处理（生效）
        if EngineType.LEGACY in self.engines:
            legacy_engine = self.engines[EngineType.LEGACY]
            legacy_result = await legacy_engine.process_single_event(event)
            legacy_result['shadow_mode'] = True
            legacy_result['shadow_results'] = shadow_results
            
            # 记录影子对比
            await self._log_shadow_comparison(event, legacy_result, shadow_results)
            
            return legacy_result
        else:
            # 如果没有传统引擎，返回影子结果（标记为不生效）
            if shadow_results.get('shadow'):
                shadow_results['shadow']['shadow_mode'] = True
                shadow_results['shadow']['effective'] = False
                return shadow_results['shadow']
            else:
                raise Exception("影子模式下无可用引擎")
    
    async def _try_fallback_processing(self, event: Dict[str, Any], 
                                     original_error: Exception) -> Optional[Dict[str, Any]]:
        """尝试降级处理"""
        fallback_config = self.config.get('fallback', {})
        
        if not fallback_config.get('enabled', True):
            return None
        
        max_attempts = fallback_config.get('max_attempts', 3)
        
        for attempt in range(max_attempts):
            try:
                # 尝试不同的引擎
                fallback_engine_type = self._select_fallback_engine(attempt)
                if fallback_engine_type in self.engines:
                    logger.info(f"尝试降级处理，使用引擎: {fallback_engine_type.value}")
                    
                    result = await self._process_with_engine(event, fallback_engine_type)
                    result['fallback_attempt'] = attempt + 1
                    result['original_error'] = str(original_error)
                    
                    return result
            except Exception as e:
                logger.warning(f"降级处理尝试 {attempt + 1} 失败: {e}")
                await asyncio.sleep(0.1)  # 短暂延迟
        
        return None
    
    def _select_fallback_engine(self, attempt: int) -> EngineType:
        """选择降级引擎"""
        # 降级策略
        if attempt == 0 and EngineType.LEGACY in self.engines:
            return EngineType.LEGACY
        elif attempt == 1 and EngineType.ENHANCED in self.engines:
            return EngineType.ENHANCED
        else:
            return EngineType.FALLBACK
    
    def _create_error_result(self, event: Dict[str, Any], 
                           error: Exception,
                           processing_time: float) -> Dict[str, Any]:
        """创建错误结果"""
        return {
            'event_id': event.get('id'),
            'status': 'error',
            'error_type': type(error).__name__,
            'error_message': str(error),
            'processing_time_ms': processing_time,
            'timestamp': datetime.now().isoformat(),
            'engine_type': 'error'
        }
    
    def _update_performance_stats(self, processing_time: float):
        """更新性能统计"""
        self.performance_stats["total_processing_time_ms"] += processing_time
        self.performance_stats["peak_processing_time_ms"] = max(
            self.performance_stats["peak_processing_time_ms"],
            processing_time
        )
        
        # 计算平均处理时间（滑动窗口）
        total_processed = self.stats["successful"] + self.stats["failed"]
        if total_processed > 0:
            self.performance_stats["avg_processing_time_ms"] = (
                self.performance_stats["total_processing_time_ms"] / total_processed
            )
    
    async def _log_decision(self, event: Dict[str, Any], 
                           result: Dict[str, Any],
                           engine_type: EngineType):
        """记录决策日志"""
        if not self.db:
            return
        
        try:
            log_entry = {
                'event_id': event.get('id'),
                'engine_type': engine_type.value,
                'processing_time_ms': result.get('processing_time_ms', 0),
                'decision_type': result.get('ai_decision', {}).get('decision'),
                'confidence': result.get('ai_decision', {}).get('confidence'),
                'status': result.get('status'),
                'selection_reason': result.get('selection_reason'),
                'created_at': datetime.now()
            }
            
            await self.db.insert('theme_orchestrator_log', log_entry)
            
        except Exception as e:
            logger.error(f"记录决策日志失败: {e}")
    
    async def _log_shadow_comparison(self, event: Dict[str, Any],
                                   legacy_result: Dict[str, Any],
                                   shadow_results: Dict[str, Any]):
        """记录影子对比结果"""
        if not self.db or 'shadow' not in shadow_results:
            return
        
        try:
            shadow_result = shadow_results['shadow']
            comparison = {
                'event_id': event.get('id'),
                'legacy_decision': legacy_result.get('ai_decision', {}).get('decision'),
                'shadow_decision': shadow_result.get('ai_decision', {}).get('decision'),
                'legacy_confidence': legacy_result.get('ai_decision', {}).get('confidence'),
                'shadow_confidence': shadow_result.get('ai_decision', {}).get('confidence'),
                'decision_match': self._compare_decisions(
                    legacy_result.get('ai_decision', {}),
                    shadow_result.get('ai_decision', {})
                ),
                'created_at': datetime.now()
            }
            
            await self.db.insert('shadow_comparison_log', comparison)
            
        except Exception as e:
            logger.error(f"记录影子对比失败: {e}")
    
    async def _log_error(self, event: Dict[str, Any], error_result: Dict[str, Any]):
        """记录错误日志"""
        if not self.db:
            return
        
        try:
            error_log = {
                'event_id': event.get('id'),
                'error_type': error_result.get('error_type'),
                'error_message': error_result.get('error_message'),
                'processing_time_ms': error_result.get('processing_time_ms'),
                'created_at': datetime.now()
            }
            
            await self.db.insert('orchestrator_error_log', error_log)
            
        except Exception as e:
            logger.error(f"记录错误日志失败: {e}")
    
    def _compare_decisions(self, decision1: Dict, decision2: Dict) -> bool:
        """比较两个决策是否一致"""
        if not decision1 or not decision2:
            return False
        
        type1 = decision1.get('decision')
        type2 = decision2.get('decision')
        
        # 决策类型相同
        if type1 != type2:
            return False
        
        # 如果是MERGE_INTO，检查目标题材
        if type1 == 'MERGE_INTO':
            target1 = decision1.get('target_theme_name', '')
            target2 = decision2.get('target_theme_name', '')
            return target1 == target2
        
        return True
    
    async def batch_process_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量处理事件
        
        Args:
            events: 事件列表
            
        Returns:
            处理结果列表
        """
        logger.info(f"开始批量处理 {len(events)} 个事件")
        
        results = []
        for i, event in enumerate(events):
            result = await self.process_event(event)
            results.append(result)
            
            # 进度显示
            if (i + 1) % 10 == 0:
                logger.info(f"已处理 {i + 1}/{len(events)} 个事件")
        
        logger.info(f"批量处理完成，成功: {self.stats['successful']}, 失败: {self.stats['failed']}")
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        uptime = (datetime.now() - self.stats["start_time"]).total_seconds()
        
        return {
            "processing_mode": self.mode.value,
            "total_processed": self.stats["total_processed"],
            "successful": self.stats["successful"],
            "failed": self.stats["failed"],
            "fallback_triggered": self.stats["fallback_triggered"],
            "success_rate": (
                self.stats["successful"] / self.stats["total_processed"] 
                if self.stats["total_processed"] > 0 else 0
            ),
            "engine_distribution": dict(self.stats["by_engine"]),
            "mode_distribution": dict(self.stats["by_mode"]),
            "performance": self.performance_stats,
            "uptime_seconds": uptime,
            "engines_available": list(self.engines.keys())
        }
    
    def get_engine_status(self) -> Dict[str, Any]:
        """获取引擎状态"""
        status = {}
        
        for engine_type, engine in self.engines.items():
            try:
                # 尝试获取引擎的统计信息
                if hasattr(engine, 'get_stats'):
                    stats = engine.get_stats()
                    status[engine_type.value] = {
                        "status": "active",
                        "stats": stats
                    }
                else:
                    status[engine_type.value] = {
                        "status": "active",
                        "stats": "no_stats_available"
                    }
            except Exception as e:
                status[engine_type.value] = {
                    "status": "error",
                    "error": str(e)
                }
        
        return status
    
    def change_mode(self, new_mode: str):
        """
        更改处理模式
        
        Args:
            new_mode: 新模式（legacy_only, enhanced_only, hybrid, shadow）
        """
        mode_map = {
            'legacy_only': ProcessingMode.LEGACY_ONLY,
            'enhanced_only': ProcessingMode.ENHANCED_ONLY,
            'hybrid': ProcessingMode.HYBRID,
            'shadow': ProcessingMode.SHADOW
        }
        
        if new_mode not in mode_map:
            logger.error(f"无效的模式: {new_mode}")
            return False
        
        new_mode_enum = mode_map[new_mode]
        
        if new_mode_enum == self.mode:
            logger.info(f"模式已经是 {new_mode}")
            return True
        
        # 检查新模式所需的引擎是否可用
        if new_mode_enum == ProcessingMode.LEGACY_ONLY and EngineType.LEGACY not in self.engines:
            logger.error("无法切换到legacy_only模式：传统引擎不可用")
            return False
        
        if new_mode_enum == ProcessingMode.ENHANCED_ONLY and EngineType.ENHANCED not in self.engines:
            logger.error("无法切换到enhanced_only模式：增强引擎不可用")
            return False
        
        # 切换模式
        old_mode = self.mode
        self.mode = new_mode_enum
        
        logger.info(f"处理模式已从 {old_mode.value} 切换到 {self.mode.value}")
        
        return True
    
    def clear_stats(self):
        """清除统计信息"""
        old_stats = self.get_stats()
        
        self.stats = {
            "total_processed": 0,
            "by_engine": defaultdict(int),
            "by_mode": defaultdict(int),
            "successful": 0,
            "failed": 0,
            "fallback_triggered": 0,
            "start_time": datetime.now()
        }
        
        self.performance_stats = {
            "avg_processing_time_ms": 0,
            "total_processing_time_ms": 0,
            "peak_processing_time_ms": 0
        }
        
        logger.info(f"统计信息已清除，旧统计: {old_stats}")


# 测试函数
async def test_theme_orchestrator():
    """测试主题编排器"""
    print("🧪 测试ThemeOrchestrator...")
    
    # 创建配置
    config = {
        'processing_mode': 'hybrid',
        'feature_flags': {
            'enable_enhanced_features': True,
            'enable_shadow_mode': False
        },
        'fallback': {
            'enabled': True,
            'max_attempts': 3
        }
    }
    
    # 创建模拟AI客户端
    class MockAIClient:
        async def analyze_event_for_themes(self, event_data):
            return {
                "potential_themes": ["AI眼镜", "智能穿戴"],
                "certainty": 0.8
            }
    
        async def analyze_event_with_context(self, event_data, related_themes):
            return {
                "decision": "CREATE_NEW",
                "target_theme_name": "智能穿戴新品",
                "confidence": 0.85,
                "reason": "新产品具有创新性"
            }
    
    # 创建测试事件
    event = {
        "id": 1001,
        "title": "小米发布智能眼镜",
        "summary": "小米发布新款智能眼镜产品",
        "event_type": "产品发布",
        "impact_industries": ["消费电子", "人工智能"],
        "theme_directive": {
            "action": "CREATE_NEW",
            "confidence": 0.88,
            "reason": "新品发布可能形成新主题"
        }
    }
    
    # 创建编排器
    ai_client = MockAIClient()
    orchestrator = ThemeOrchestrator(config, ai_client)
    
    # 测试处理事件
    result = await orchestrator.process_event(event)
    
    print(f"✅ 处理测试完成!")
    print(f"   事件ID: {result.get('event_id')}")
    print(f"   状态: {result.get('status')}")
    print(f"   选择的引擎: {result.get('selected_engine')}")
    print(f"   处理时间: {result.get('processing_time_ms', 0):.0f}ms")
    
    # 显示统计信息
    stats = orchestrator.get_stats()
    print(f"\n📊 编排器统计:")
    print(f"   总处理数: {stats['total_processed']}")
    print(f"   成功率: {stats['success_rate']:.1%}")
    print(f"   引擎分布: {stats['engine_distribution']}")
    
    # 显示引擎状态
    engine_status = orchestrator.get_engine_status()
    print(f"\n🔧 引擎状态:")
    for engine_name, status_info in engine_status.items():
        print(f"   {engine_name}: {status_info['status']}")
    
    # 测试模式切换
    print(f"\n🔄 测试模式切换:")
    orchestrator.change_mode('enhanced_only')
    print(f"   当前模式: {orchestrator.mode.value}")
    
    return orchestrator


if __name__ == "__main__":
    asyncio.run(test_theme_orchestrator())