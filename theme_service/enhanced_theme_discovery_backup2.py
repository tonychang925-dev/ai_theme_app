#!/usr/bin/env python3
"""
主题发现业务引擎 - 重构版（使用AI相似性分析）
🔥 核心职责：执行业务逻辑，使用AI相似性分析器
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
    使用AI相似性分析器，彻底取代关键词匹配
    """
    
    def __init__(self, 
                 ai_client,           # EnhancedAIThemeClient实例
                 database_client,     # DatabaseClient实例
                 similarity_analyzer, # AIThemeSimilarityAnalyzer实例（新增）
                 config: Optional[Dict] = None):
        """
        初始化业务引擎
        
        Args:
            ai_client: EnhancedAIThemeClient实例
            database_client: DatabaseClient实例
            similarity_analyzer: AIThemeSimilarityAnalyzer实例（关键新增）
            config: 配置参数
        """
        self.ai_client = ai_client
        self.db_client = database_client
        self.similarity_analyzer = similarity_analyzer
        
        # 🔥 创建新的RelatedThemeFetcher（使用AI相似性分析）
        from database_service.pure_data_fetcher import PureDataFetcher
        from theme_service.related_theme_fetcher import RelatedThemeFetcher
        
        # 创建纯数据获取器
        data_fetcher = PureDataFetcher(database_client)
        
        # 创建使用AI相似性分析的检索器
        self.theme_fetcher = RelatedThemeFetcher(
            data_fetcher=data_fetcher,
            similarity_analyzer=similarity_analyzer,
            use_cache=True
        )
        
        # 配置参数
        self.config = config or {}
        
        # 阈值配置
        self.fast_track_threshold = self.config.get('fast_track_threshold', 0.90)
        self.review_threshold = self.config.get('review_threshold', 0.65)
        self.ignore_threshold = self.config.get('ignore_threshold', 0.3)
        
        # 状态追踪
        self.processing_stats = defaultdict(int)
        self._reset_stats()
        
        logger.info(f"EnhancedThemeDiscoveryEngine 初始化完成（AI相似性分析版）")
        logger.info(f"  组件: AI客户端 ✅, 数据库客户端 ✅, AI相似性分析器 ✅")
        logger.info(f"  主题检索器: 使用AI相似性分析（非关键词匹配）")
    
    def _reset_stats(self):
        """重置统计信息"""
        self.processing_stats.update({
            'total_processed': 0,
            'created': 0,
            'merged': 0,
            'ignored': 0,
            'failed': 0,
            'in_review': 0,
            'duplicate_prevented': 0,
            'ai_similarity_calls': 0
        })
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个事件（使用AI相似性分析）
        
        Args:
            event: 事件数据，必须包含id和theme_directive
            
        Returns:
            处理结果
        """
        event_id = event.get('id') or event.get('news_id') or event.get('event_id', 'unknown')
        event['id'] = event_id  # 确保有id字段
        
        logger.info(f"开始处理事件 {event_id}（使用AI相似性分析）")
        
        self.processing_stats['total_processed'] += 1
        
        # 初始化结果结构
        result = {
            'event_id': event_id,
            'processed_at': datetime.now().isoformat(),
            'status': 'pending',
            'engine_version': 'ai_similarity_engine_v1',
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
            
            # === 步骤2：使用AI相似性分析器获取相关主题 ===
            result['steps'].append({
                'step': 'fetch_related_themes_ai',
                'status': 'started',
                'timestamp': datetime.now().isoformat()
            })
            
            try:
                # 🔥 关键：使用AI相似性分析器获取相关主题
                related_themes = await self.theme_fetcher.fetch_related_themes(event, limit=5)
                self.processing_stats['ai_similarity_calls'] += 1
                
                result['related_themes_count'] = len(related_themes)
                result['steps'][-1]['status'] = 'completed'
                result['steps'][-1]['themes_found'] = len(related_themes)
                result['steps'][-1]['method'] = 'ai_similarity_analysis'
                
                logger.info(f"AI相似性分析找到 {len(related_themes)} 个相关主题")
                
                # 记录相似度信息
                if related_themes:
                    best_match = related_themes[0]
                    result['best_match'] = {
                        'theme_name': best_match.get('name'),
                        'similarity_score': best_match.get('similarity_score', 0),
                        'similarity_reason': best_match.get('similarity_reason', '')[:100]
                    }
                    
            except Exception as e:
                result['steps'][-1]['status'] = 'failed'
                result['steps'][-1]['error'] = str(e)
                logger.error(f"AI相似性分析失败: {e}")
                related_themes = []  # 使用空列表继续
            
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
            
            # === 步骤4：执行业务逻辑（数据库操作）===
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
                    'discovery_source': 'enhanced_engine_ai',
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
                            'source': 'enhanced_engine_ai',
                            'similarity_analysis': '使用AI相似性分析'
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
                    # 如果主题不存在，创建它
                    logger.warning(f"目标主题 '{target_theme_name}' 不存在，自动创建")
                    theme = await self.db_client.create_theme(
                        name=target_theme_name,
                        keywords=self._extract_keywords_from_event(event_data),
                        discovery_source='enhanced_engine_ai',
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
                            'source': 'enhanced_engine_ai',
                            'similarity_analysis': '使用AI相似性分析'
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
        """从事件中提取关键词（仅用于描述，不用于匹配）"""
        import re
        
        keywords = []
        
        # 从标题提取
        title = event_data.get('title', '')
        if title:
            chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
            keywords.extend(chinese_words[:3])
        
        # 添加行业
        industries = event_data.get('impact_industries', [])
        keywords.extend(industries)
        
        # 去重
        return list(set(keywords))[:5]
    
    async def batch_process_events(self, events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        批量处理事件
        
        Args:
            events: 事件列表
            
        Returns:
            处理结果列表
        """
        logger.info(f"开始批量处理 {len(events)} 个事件（使用AI相似性分析）")
        
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
        stats = dict(self.processing_stats)
        
        # 计算成功率
        if stats['total_processed'] > 0:
            success_count = stats['created'] + stats['merged'] + stats['ignored']
            stats['success_rate'] = success_count / stats['total_processed']
            stats['ai_similarity_call_rate'] = stats['ai_similarity_calls'] / stats['total_processed']
        
        return stats
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            'engine_version': 'ai_similarity_engine_v1',
            'components_available': {
                'ai_client': self.ai_client is not None,
                'database_client': self.db_client is not None,
                'similarity_analyzer': self.similarity_analyzer is not None,
                'theme_fetcher': self.theme_fetcher is not None
            },
            'analysis_method': 'ai_similarity_analysis',
            'thresholds': {
                'fast_track_threshold': self.fast_track_threshold,
                'review_threshold': self.review_threshold,
                'ignore_threshold': self.ignore_threshold
            },
            'processing_stats': self.get_stats()
        }

# 测试函数
async def test_enhanced_engine():
    """测试增强的引擎"""
    print("🧪 测试EnhancedThemeDiscoveryEngine（AI相似性分析版）...")
    
    # 检查API密钥
    import os
    if not os.getenv('DEEPSEEK_API_KEY'):
        print("⚠️  DEEPSEEK_API_KEY未设置，跳过真实测试")
        return True
    
    try:
        # 导入组件
        from database_service.config import DatabaseConfig
        from database_service.memory_manager import MemoryDatabaseManager
        from database_service.client import DatabaseClient
        
        from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
        from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
        from theme_service.enhanced_ai_client import EnhancedAIThemeClient
        
        # 初始化数据库
        db_config = DatabaseConfig()
        db_manager = MemoryDatabaseManager(db_config)
        await db_manager.connect()
        db_client = DatabaseClient(db_manager)
        
        # 添加测试主题
        await db_manager.create_theme(
            name="人工智能芯片",
            keywords=["AI", "芯片", "半导体"],
            description="AI专用芯片技术"
        )
        await db_manager.create_theme(
            name="AR/VR设备",
            keywords=["AR", "VR", "眼镜", "头显"],
            description="增强现实和虚拟现实设备"
        )
        
        # 初始化AI组件
        ai_parser = ReliableDeepSeekParser(config={'timeout': 60})
        similarity_analyzer = AIThemeSimilarityAnalyzer(ai_parser)
        ai_client = EnhancedAIThemeClient()
        
        # 创建引擎
        engine = EnhancedThemeDiscoveryEngine(
            ai_client=ai_client,
            database_client=db_client,
            similarity_analyzer=similarity_analyzer,
            config={
                'fast_track_threshold': 0.8,
                'review_threshold': 0.6
            }
        )
        
        print(f"✅ 引擎初始化完成: {engine.get_engine_info()['engine_version']}")
        
        # 测试事件
        test_events = [
            {
                "id": "test_engine_001",
                "title": "英伟达发布新一代AI芯片H100",
                "summary": "英伟达发布性能更强的AI芯片H100，算力大幅提升",
                "event_type": "产品发布",
                "impact_industries": ["人工智能", "半导体", "芯片"],
                "theme_directive": {"action": "CREATE_NEW", "confidence": 0.85, "reason": "重大技术突破"}
            }
        ]
        
        # 处理事件
        print("处理测试事件...")
        results = await engine.batch_process_events(test_events)
        
        for result in results:
            print(f"  事件: {result['event_id']}, 状态: {result['status']}")
            if 'ai_decision' in result:
                print(f"    决策: {result['ai_decision'].get('decision')}")
            if 'best_match' in result:
                print(f"    最佳匹配: {result['best_match']['theme_name']} "
                      f"(相似度: {result['best_match']['similarity_score']:.2f})")
        
        # 获取统计信息
        stats = engine.get_stats()
        print(f"\n📊 引擎统计:")
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # 清理资源
        await ai_parser.close()
        await db_manager.disconnect()
        
        print(f"\n✅ 引擎测试完成!")
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    import asyncio
    asyncio.run(test_enhanced_engine())
