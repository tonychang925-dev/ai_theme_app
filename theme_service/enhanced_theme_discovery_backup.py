#!/usr/bin/env python3
"""
主题发现业务引擎 - 重构版
🔥 核心职责：执行业务逻辑，调用AI客户端和数据库客户端
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class EnhancedThemeDiscoveryEngine:
    """
    主题发现业务引擎 - 重构版
    负责完整的业务逻辑：AI决策 → 业务处理 → 数据库操作
    """
    
    def __init__(self, 
                 ai_client,  # EnhancedAIThemeClient实例
                 database_client=None,  # DatabaseClient实例
                 dedup_engine=None,   # ThemeDeduplicationEngine实例
                 config: Optional[Dict] = None):
        """
        初始化业务引擎
        
        Args:
            ai_client: EnhancedAIThemeClient实例（纯AI分析）
            database_client: DatabaseClient实例（数据访问）
            dedup_engine: 判重引擎实例
            config: 配置参数
        """
        self.ai_client = ai_client
        self.db_client = database_client
        self.dedup_engine = dedup_engine
        
        # 配置参数
        self.config = config or {}
        
        # 阈值配置
        self.fast_track_threshold = self.config.get('fast_track_threshold', 0.90)
        self.review_threshold = self.config.get('review_threshold', 0.65)
        self.ignore_threshold = self.config.get('ignore_threshold', 0.3)
        
        # 状态追踪
        self.processing_stats = defaultdict(int)
        self._reset_stats()
        
        logger.info(f"EnhancedThemeDiscoveryEngine 初始化完成（业务引擎版）")
        logger.info(f"  AI客户端: {'已配置' if ai_client else '未配置'}")
        logger.info(f"  数据库客户端: {'已配置' if database_client else '未配置'}")
        logger.info(f"  判重引擎: {'已配置' if dedup_engine else '未配置'}")
    
    def _reset_stats(self):
        """重置统计信息"""
        self.processing_stats.update({
            'total_processed': 0,
            'created': 0,
            'merged': 0,
            'ignored': 0,
            'failed': 0,
            'in_review': 0,
            'duplicate_prevented': 0
        })
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个事件（完整的业务逻辑）
        
        Args:
            event: 事件数据，必须包含id和theme_directive
            
        Returns:
            处理结果
        """
        event_id = event.get('id') or event.get('news_id') or event.get('event_id', 'unknown')
        event['id'] = event_id  # 确保有id字段
        
        logger.info(f"开始处理事件 {event_id}")
        
        self.processing_stats['total_processed'] += 1
        
        # 初始化结果结构
        result = {
            'event_id': event_id,
            'processed_at': datetime.now().isoformat(),
            'status': 'pending',
            'engine_version': 'business_engine_v1',
            'steps': []
        }
        
        try:
            # === 步骤1：验证事件数据 ===
            result['steps'].append({
                'step': 'validate_event',
                'status': 'started',
                'timestamp': datetime.now().isoformat()
            })
            
            if 'theme_directive' not in event:
                logger.warning(f"事件 {event_id} 缺少theme_directive，添加默认指令")
                event['theme_directive'] = {
                    'action': 'CREATE_NEW',
                    'confidence': 0.75,
                    'reason': '默认指令'
                }
            
            result['steps'][-1]['status'] = 'completed'
            
            # === 步骤2：获取相关主题（如果需要）===
            related_themes = []
            if self.db_client:
                result['steps'].append({
                    'step': 'fetch_related_themes',
                    'status': 'started',
                    'timestamp': datetime.now().isoformat()
                })
                
                try:
                    related_themes = await self.db_client.find_related_themes(event, limit=5)
                    result['related_themes_count'] = len(related_themes)
                    result['steps'][-1]['status'] = 'completed'
                    result['steps'][-1]['themes_found'] = len(related_themes)
                    logger.info(f"从数据库查询到 {len(related_themes)} 个相关主题")
                except Exception as e:
                    result['steps'][-1]['status'] = 'failed'
                    result['steps'][-1]['error'] = str(e)
                    logger.error(f"查询相关主题失败: {e}")
            else:
                logger.warning("未配置数据库客户端，跳过相关主题查询")
            
            # === 步骤3：调用AI客户端进行决策 ===
            result['steps'].append({
                'step': 'ai_decision',
                'status': 'started',
                'timestamp': datetime.now().isoformat()
            })
            
            try:
                ai_decision = await self.ai_client.analyze_event_with_context(
                    event_data=event,
                    related_themes=related_themes
                )
                result['ai_decision'] = ai_decision
                result['steps'][-1]['status'] = 'completed'
                result['steps'][-1]['decision'] = ai_decision.get('decision')
                result['steps'][-1]['confidence'] = ai_decision.get('confidence')
                logger.info(f"AI决策: {ai_decision.get('decision')}, 置信度: {ai_decision.get('confidence', 0):.2f}")
            except Exception as e:
                result['steps'][-1]['status'] = 'failed'
                result['steps'][-1]['error'] = str(e)
                logger.error(f"AI决策失败: {e}")
                raise
            
            # === 步骤4：判重检查（如果配置了判重引擎）===
            if self.dedup_engine and ai_decision.get('decision') == 'CREATE_NEW':
                result['steps'].append({
                    'step': 'deduplication_check',
                    'status': 'started',
                    'timestamp': datetime.now().isoformat()
                })
                
                try:
                    new_theme_name = ai_decision.get('target_theme_name', '新题材')
                    dedup_result = await self.dedup_engine.check_duplication(
                        new_theme_name=new_theme_name,
                        event_data=event,
                        existing_themes=related_themes
                    )
                    
                    result['dedup_result'] = dedup_result.to_dict() if hasattr(dedup_result, 'to_dict') else dedup_result
                    
                    # 如果判重认为应该合并，覆盖AI决策
                    if dedup_result.should_merge and dedup_result.target_theme:
                        logger.info(f"判重检查建议合并，覆盖AI决策")
                        ai_decision = {
                            "decision": "MERGE_INTO",
                            "target_theme_name": dedup_result.target_theme.get('name', '未知题材'),
                            "confidence": dedup_result.confidence,
                            "reason": f"判重覆盖: {dedup_result.reason}",
                            "comparison_analysis": dedup_result.reason,
                            "dedup_overridden": True
                        }
                        result['ai_decision'] = ai_decision
                        self.processing_stats['duplicate_prevented'] += 1
                    
                    result['steps'][-1]['status'] = 'completed'
                    result['steps'][-1]['should_merge'] = dedup_result.should_merge
                except Exception as e:
                    result['steps'][-1]['status'] = 'failed'
                    result['steps'][-1]['error'] = str(e)
                    logger.error(f"判重检查失败: {e}")
            
            # === 步骤5：执行业务逻辑（数据库操作）===
            result['steps'].append({
                'step': 'execute_business_logic',
                'status': 'started',
                'timestamp': datetime.now().isoformat()
            })
            
            execution_result = await self._execute_business_logic(event_id, ai_decision, event)
            result['execution_result'] = execution_result
            
            # 更新状态
            if execution_result['status'] == 'created':
                self.processing_stats['created'] += 1
                result['status'] = 'created'
                result['theme_id'] = execution_result.get('theme_id')
            elif execution_result['status'] == 'merged':
                self.processing_stats['merged'] += 1
                result['status'] = 'merged'
                result['theme_id'] = execution_result.get('theme_id')
            elif execution_result['status'] == 'ignored':
                self.processing_stats['ignored'] += 1
                result['status'] = 'ignored'
            else:
                result['status'] = execution_result['status']
            
            result['steps'][-1]['status'] = 'completed'
            result['steps'][-1]['result'] = execution_result
            
            logger.info(f"✅ 事件 {event_id} 处理完成，状态: {result['status']}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 事件 {event_id} 处理失败: {e}", exc_info=True)
            self.processing_stats['failed'] += 1
            
            result['status'] = 'failed'
            result['error'] = str(e)
            result['error_type'] = type(e).__name__
            
            # 记录失败的步骤
            if 'steps' in result and result['steps']:
                for step in result['steps']:
                    if step.get('status') == 'started':
                        step['status'] = 'failed'
                        step['error'] = str(e)
            
            return result
    
    async def _execute_business_logic(self, 
                                     event_id: int, 
                                     ai_decision: Dict[str, Any],
                                     event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行业务逻辑：根据AI决策进行数据库操作
        """
        decision_type = ai_decision.get('decision')
        target_theme_name = ai_decision.get('target_theme_name', '')
        confidence = ai_decision.get('confidence', 0.0)
        
        logger.info(f"执行业务逻辑，事件: {event_id}, 决策: {decision_type}, 目标主题: {target_theme_name}")
        
        # 如果没有数据库客户端，返回模拟结果
        if not self.db_client:
            logger.warning("未配置数据库客户端，返回模拟结果")
            return {
                'status': 'simulated',
                'decision': decision_type,
                'target_theme_name': target_theme_name,
                'message': '模拟执行（未配置数据库客户端）'
            }
        
        try:
            if decision_type == 'CREATE_NEW':
                # 创建新主题并关联事件
                theme_data = {
                    'name': target_theme_name,
                    'keywords': self._extract_keywords_from_event(event_data),
                    'description': ai_decision.get('reason', ''),
                    'discovery_source': 'enhanced_engine',
                    'discovery_confidence': confidence
                }
                
                # 使用事务确保一致性
                async with self.db_client.transaction():
                    # 创建主题
                    theme = await self.db_client.create_theme(**theme_data)
                    
                    # 创建事件-主题关联
                    relation = await self.db_client.create_event_theme_relation(
                        event_id=event_id,
                        theme_id=theme['id'],
                        confidence=confidence,
                        evidence={
                            'ai_reason': ai_decision.get('reason'),
                            'comparison_analysis': ai_decision.get('comparison_analysis', ''),
                            'source': 'enhanced_engine'
                        }
                    )
                    
                    # 标记事件已处理
                    await self.db_client.mark_event_processed(event_id)
                
                logger.info(f"创建新主题: {target_theme_name} (ID: {theme['id']})")
                
                return {
                    'status': 'created',
                    'theme_id': theme['id'],
                    'theme_name': theme['name'],
                    'relation_id': relation['id'],
                    'message': '成功创建新主题并关联事件'
                }
            
            elif decision_type == 'MERGE_INTO':
                # 将事件合并到现有主题
                
                # 首先获取主题ID
                theme = await self.db_client.get_theme_by_name(target_theme_name)
                if not theme:
                    # 如果主题不存在，创建它（降级处理）
                    logger.warning(f"目标主题 '{target_theme_name}' 不存在，自动创建")
                    theme = await self.db_client.create_theme(
                        name=target_theme_name,
                        keywords=self._extract_keywords_from_event(event_data),
                        discovery_source='enhanced_engine',
                        discovery_confidence=confidence
                    )
                
                # 使用事务确保一致性
                async with self.db_client.transaction():
                    # 创建事件-主题关联
                    relation = await self.db_client.create_event_theme_relation(
                        event_id=event_id,
                        theme_id=theme['id'],
                        confidence=confidence,
                        evidence={
                            'ai_reason': ai_decision.get('reason'),
                            'comparison_analysis': ai_decision.get('comparison_analysis', ''),
                            'merge_decision': True,
                            'source': 'enhanced_engine'
                        }
                    )
                    
                    # 标记事件已处理
                    await self.db_client.mark_event_processed(event_id)
                
                logger.info(f"将事件合并到主题: {target_theme_name} (ID: {theme['id']})")
                
                return {
                    'status': 'merged',
                    'theme_id': theme['id'],
                    'theme_name': theme['name'],
                    'relation_id': relation['id'],
                    'message': '成功将事件合并到现有主题'
                }
            
            elif decision_type == 'IGNORE':
                # 忽略事件，只标记为已处理
                await self.db_client.mark_event_processed(event_id)
                
                logger.info(f"忽略事件: {event_id}")
                
                return {
                    'status': 'ignored',
                    'message': '事件被忽略',
                    'reason': ai_decision.get('reason', '')
                }
            
            else:
                logger.warning(f"未知决策类型: {decision_type}，标记为已处理")
                await self.db_client.mark_event_processed(event_id)
                
                return {
                    'status': 'unknown_decision',
                    'decision_type': decision_type,
                    'message': '未知决策类型，已标记为处理'
                }
                
        except Exception as e:
            logger.error(f"执行业务逻辑失败: {e}")
            raise
    
    def _extract_keywords_from_event(self, event_data: Dict[str, Any]) -> List[str]:
        """从事件中提取关键词"""
        import re
        
        keywords = []
        
        # 从标题提取
        title = event_data.get('title', '')
        if title:
            chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
            keywords.extend(chinese_words[:3])  # 最多3个中文词
        
        # 添加行业
        industries = event_data.get('impact_industries', [])
        keywords.extend(industries)
        
        # 去重
        return list(set(keywords))[:5]  # 最多5个关键词
    
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
        for event in events:
            try:
                result = await self.process_single_event(event)
                results.append(result)
            except Exception as e:
                logger.error(f"处理事件失败: {event.get('id', 'unknown')}, 错误: {e}")
                results.append({
                    'event_id': event.get('id', 'unknown'),
                    'status': 'failed',
                    'error': str(e)
                })
        
        logger.info(f"批量处理完成，成功: {sum(1 for r in results if r['status'] != 'failed')}, "
                   f"失败: {sum(1 for r in results if r['status'] == 'failed')}")
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        return dict(self.processing_stats)
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            'engine_version': 'business_engine_v1',
            'components_available': {
                'ai_client': self.ai_client is not None,
                'database_client': self.db_client is not None,
                'dedup_engine': self.dedup_engine is not None
            },
            'thresholds': {
                'fast_track_threshold': self.fast_track_threshold,
                'review_threshold': self.review_threshold,
                'ignore_threshold': self.ignore_threshold
            },
            'processing_stats': dict(self.processing_stats)
        }


# 测试函数
async def test_business_engine():
    """测试业务引擎"""
    print("🧪 测试EnhancedThemeDiscoveryEngine（业务引擎版）...")
    
    # 创建模拟AI客户端
    class MockAIClient:
        async def analyze_event_with_context(self, event_data, related_themes):
            event_id = event_data.get('id', '')
            
            # 模拟AI决策
            if 'duplicate' in event_id:
                return {
                    "decision": "MERGE_INTO",
                    "target_theme_name": "人工智能",
                    "confidence": 0.78,
                    "reason": "测试重复事件",
                    "comparison_analysis": "与现有人工智能题材重复"
                }
            else:
                return {
                    "decision": "CREATE_NEW",
                    "target_theme_name": "量子计算",
                    "confidence": 0.88,
                    "reason": "测试独特事件",
                    "comparison_analysis": "新技术方向"
                }
    
    # 创建模拟数据库客户端
    class MockDatabaseClient:
        def __init__(self):
            self.themes = {}
            self.relations = []
            self.processed_events = set()
        
        async def find_related_themes(self, event_data, limit=5):
            return [
                {
                    'id': 1,
                    'name': '人工智能',
                    'keywords': ['AI', '人工智能'],
                    'discovery_confidence': 0.8
                }
            ]
        
        async def create_theme(self, **kwargs):
            theme_id = len(self.themes) + 1
            theme = {'id': theme_id, **kwargs}
            self.themes[theme_id] = theme
            return theme
        
        async def get_theme_by_name(self, name):
            for theme in self.themes.values():
                if theme['name'] == name:
                    return theme
            return None
        
        async def create_event_theme_relation(self, event_id, theme_id, **kwargs):
            relation_id = len(self.relations) + 1
            relation = {'id': relation_id, 'event_id': event_id, 'theme_id': theme_id, **kwargs}
            self.relations.append(relation)
            return relation
        
        async def mark_event_processed(self, event_id):
            self.processed_events.add(event_id)
        
        def transaction(self):
            # 模拟事务
            class MockTransaction:
                async def __aenter__(self):
                    return self
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            return MockTransaction()
    
    # 创建测试事件
    test_events = [
        {
            "id": "test_unique_event",
            "title": "量子计算重大突破",
            "summary": "量子计算取得重大突破",
            "event_type": "技术突破",
            "impact_industries": ["量子计算", "信息技术"],
            "theme_directive": {"action": "CREATE_NEW", "confidence": 0.85, "reason": "重大突破"}
        },
        {
            "id": "test_duplicate_event",
            "title": "人工智能新应用",
            "summary": "人工智能新应用发布",
            "event_type": "产品发布",
            "impact_industries": ["人工智能"],
            "theme_directive": {"action": "CREATE_NEW", "confidence": 0.78, "reason": "新应用"}
        }
    ]
    
    # 创建引擎
    ai_client = MockAIClient()
    db_client = MockDatabaseClient()
    
    engine = EnhancedThemeDiscoveryEngine(
        ai_client=ai_client,
        database_client=db_client,
        config={
            'fast_track_threshold': 0.85,
            'review_threshold': 0.65
        }
    )
    
    # 处理事件
    results = await engine.batch_process_events(test_events)
    
    # 显示结果
    print(f"\n📊 处理结果:")
    for result in results:
        print(f"  事件: {result['event_id']}, 状态: {result['status']}")
        if 'ai_decision' in result:
            print(f"    决策: {result['ai_decision'].get('decision')}")
    
    print(f"\n📈 引擎统计:")
    stats = engine.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
    
    print(f"\n✅ 业务引擎测试完成!")
    return results

if __name__ == "__main__":
    asyncio.run(test_business_engine())