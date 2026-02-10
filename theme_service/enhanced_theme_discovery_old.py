#!/usr/bin/env python3
"""
增强版主题发现引擎 - 修复版（在所有路径中加入判重检查）
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)


class EnhancedThemeDiscoveryEngine:
    """
    增强版主题发现引擎 - 修复版
    核心修复：在所有执行路径中都加入判重检查
    1. guided_merge路径中加入判重检查
    2. fast_track_create路径中加入判重检查
    3. 判重检查可以覆盖AI决策
    """
    
    def __init__(self, 
                 ai_client,  # 增强版AIThemeClient
                 db_manager=None,
                 theme_fetcher=None,  # RelatedThemeFetcher实例
                 dedup_engine=None,   # ThemeDeduplicationEngine实例
                 config: Optional[Dict] = None):
        """
        初始化增强引擎（最终修复版）
        """
        self.ai_client = ai_client
        self.db = db_manager
        self.theme_fetcher = theme_fetcher
        
        # 🔥 强制要求提供判重引擎
        if dedup_engine is None:
            logger.warning("⚠️  未提供判重引擎，判重功能将不可用！")
            dedup_engine = self._create_mock_dedup_engine()
        
        self.dedup_engine = dedup_engine
        
        # 配置参数
        self.config = config or {}
        
        # 阈值配置
        self.fast_track_threshold = self.config.get('fast_track_threshold', 0.90)
        self.review_threshold = self.config.get('review_threshold', 0.65)
        self.ignore_threshold = self.config.get('ignore_threshold', 0.3)
        self.dedup_threshold = self.config.get('dedup_threshold', 0.7)
        
        # 状态追踪
        self.processing_stats = defaultdict(int)
        self._reset_stats()
        
        # 功能使用统计
        self.component_usage = {
            'theme_fetcher_used': 0,
            'dedup_engine_used': 0,
            'theme_fetcher_failed': 0,
            'dedup_engine_failed': 0,
            'dedup_checks_in_guided_merge': 0,    # 新增：在guided_merge中的判重检查
            'dedup_checks_in_fast_track': 0,      # 新增：在fast_track_create中的判重检查
            'dedup_overrides_ai_decision': 0      # 新增：判重覆盖AI决策的次数
        }
        
        logger.info(f"EnhancedThemeDiscoveryEngine 初始化完成（最终修复版）")
        logger.info(f"  主题检索器: {'已启用' if theme_fetcher else '未启用'}")
        logger.info(f"  判重引擎: {'已启用' if dedup_engine else '模拟'}")
        logger.info(f"  阈值配置: fast_track={self.fast_track_threshold}, review={self.review_threshold}")
    
    def _create_mock_dedup_engine(self):
        """创建模拟判重引擎"""
        class MockDedupEngine:
            async def check_duplication(self, new_theme_name, event_data, existing_themes):
                logger.info(f"[模拟判重] 检查: {new_theme_name}")
                # 简单模拟：如果名称相似就判为重复
                for theme in existing_themes:
                    existing_name = theme.get('name', '')
                    if existing_name and (existing_name in new_theme_name or new_theme_name in existing_name):
                        return type('Result', (), {
                            'should_merge': True,
                            'target_theme': theme,
                            'similarity_score': 0.8,
                            'match_type': 'mock_inclusion',
                            'reason': f'模拟包含关系: {new_theme_name} ⊆ {existing_name}',
                            'confidence': 0.7
                        })()
                return type('Result', (), {
                    'should_merge': False,
                    'similarity_score': 0.0,
                    'match_type': 'mock_distinct',
                    'reason': '模拟未检测到重复',
                    'confidence': 0.6
                })()
        
        return MockDedupEngine()
    
    def _reset_stats(self):
        """重置统计信息"""
        self.processing_stats.update({
            'total_processed': 0,
            'created': 0,
            'merged': 0,
            'ignored': 0,
            'failed': 0,
            'in_review': 0,
            'auto_merged': 0,
            'duplicate_prevented': 0,
            'guided_create_path': 0,
            'fast_track_create_path': 0,
            'guided_merge_path': 0,
            'guided_merge_with_dedup': 0,      # 新增：经过判重检查的guided_merge
            'fast_track_with_dedup': 0,        # 新增：经过判重检查的fast_track_create
            'ai_decision_overridden': 0        # 新增：AI决策被判重覆盖的次数
        })
    
    async def process_single_event(self, event: Dict[str, Any]) -> Dict[str, Any]:
        """
        处理单个事件（最终修复版）
        🔥 核心修复：在所有执行路径中都加入判重检查
        """
        event_id = event.get('id') or event.get('news_id') or event.get('event_id', 'unknown')
        
        # 确保event中有id字段，供后续使用
        event['id'] = event_id

        logger.info(f"开始处理事件 {event_id}")
        
        self.processing_stats['total_processed'] += 1
        
        # 初始化结果结构
        result = {
            'event_id': event_id,
            'processed_at': datetime.now().isoformat(),
            'status': 'pending',
            'engine_version': 'enhanced_final_fixed_v1',
            'components_used': {
                'theme_fetcher': self.theme_fetcher is not None,
                'dedup_engine': self.dedup_engine is not None
            },
            'deduplication_info': {},
            'ai_decision_overridden': False  # 新增：AI决策是否被判重覆盖
        }
        
        try:
            # === 阶段1：检查事件是否已有指令 ===
            if 'theme_directive' not in event:
                logger.warning(f"事件 {event_id} 缺少theme_directive，添加默认指令")
                event['theme_directive'] = {
                    'action': 'CREATE_NEW',
                    'confidence': 0.75,
                    'reason': '默认指令'
                }
            
            directive = event.get('theme_directive', {})
            directive_action = directive.get('action', 'CLUSTER')
            directive_confidence = directive.get('confidence', 0.5)
            
            # === 阶段2：根据指令决定处理路径 ===
            if directive_action == 'NONE' and directive_confidence > self.ignore_threshold:
                result['status'] = 'ignored'
                result['reason'] = f"第一轮AI建议忽略: {directive.get('reason', '')}"
                self.processing_stats['ignored'] += 1
                return result
            
            # === 阶段3：检索相关题材上下文 ===
            related_themes = await self._fetch_related_themes(event)
            logger.info(f"事件 {event_id} 检索到 {len(related_themes)} 个相关题材")
            result['related_themes_count'] = len(related_themes)
            
            # === 阶段4：增强AI分析 ===
            start_time = datetime.now()
            ai_decision = await self.ai_client.analyze_event_with_context(
                event_data=event,
                related_themes=related_themes
            )
            decision_time = (datetime.now() - start_time).total_seconds() * 1000
            
            result['ai_decision'] = ai_decision
            decision_type = ai_decision.get('decision', 'UNKNOWN')
            decision_confidence = ai_decision.get('confidence', 0)
            
            result['decision_confidence_raw'] = decision_confidence
            
            # === 阶段5：根据置信度决定执行路径 ===
            execution_path = self._determine_execution_path(
                directive_action, directive_confidence,
                decision_type, decision_confidence
            )
            
            result['execution_path'] = execution_path
            
            # 记录路径统计
            if execution_path == 'guided_create':
                self.processing_stats['guided_create_path'] += 1
            elif execution_path == 'fast_track_create':
                self.processing_stats['fast_track_create_path'] += 1
            elif execution_path == 'guided_merge':
                self.processing_stats['guided_merge_path'] += 1
            
            # === 阶段6：执行决策（关键修复：在所有路径中都加入判重检查）===
            final_status = 'unknown'
            execution_result = None
            
            # 🔥 统一的判重检查方法
            async def perform_dedup_and_decide():
                """执行判重检查并返回决策"""
                nonlocal result
                
                # 执行判重检查
                dedup_result = await self._check_duplication(event, ai_decision, related_themes)
                result['deduplication_info'] = dedup_result
                
                if dedup_result.get('should_merge', False):
                    # 判重检查建议合并
                    target_theme = dedup_result.get('target_theme', ai_decision.get('target_theme_name', '未知题材'))
                    exec_result = await self._execute_merge(event, {
                        **ai_decision,
                        'target_theme_name': target_theme
                    })
                    
                    status = 'auto_merged' if execution_path in ['fast_track_create', 'guided_create'] else 'merged'
                    
                    if execution_path == 'fast_track_create':
                        self.processing_stats['fast_track_with_dedup'] += 1
                    elif execution_path == 'guided_merge':
                        self.processing_stats['guided_merge_with_dedup'] += 1
                    
                    self.processing_stats['duplicate_prevented'] += 1
                    
                    # 如果AI决策是CREATE_NEW但判重要求合并，标记为覆盖
                    if decision_type == 'CREATE_NEW':
                        result['ai_decision_overridden'] = True
                        self.processing_stats['ai_decision_overridden'] += 1
                        self.component_usage['dedup_overrides_ai_decision'] += 1
                    
                    return exec_result, status
                else:
                    # 判重检查认为应该创建
                    exec_result = await self._execute_create(event, ai_decision)
                    
                    # 如果AI决策是MERGE_INTO但判重要求创建，标记为覆盖
                    if decision_type == 'MERGE_INTO':
                        result['ai_decision_overridden'] = True
                        self.processing_stats['ai_decision_overridden'] += 1
                        self.component_usage['dedup_overrides_ai_decision'] += 1
                        logger.info(f"🔥 {execution_path}路径：判重检查覆盖AI决策，改为创建")
                    
                    return exec_result, 'created'
            
            if execution_path == 'fast_track_create':
                # 🔥 修复：在fast_track_create路径中加入判重检查
                self.component_usage['dedup_checks_in_fast_track'] += 1
                execution_result, final_status = await perform_dedup_and_decide()
                self.processing_stats['auto_merged' if final_status == 'auto_merged' else 'created'] += 1
                
            elif execution_path == 'guided_merge':
                # 🔥 核心修复：在guided_merge路径中加入判重检查
                self.component_usage['dedup_checks_in_guided_merge'] += 1
                execution_result, final_status = await perform_dedup_and_decide()
                self.processing_stats['merged' if final_status == 'merged' else 'created'] += 1
                
            elif execution_path == 'guided_create':
                # guided_create路径（已有判重检查）
                execution_result, final_status = await perform_dedup_and_decide()
                self.processing_stats['auto_merged' if final_status == 'auto_merged' else 'created'] += 1
                
            elif execution_path == 'review_pool':
                await self._add_to_review_queue(event, ai_decision, related_themes)
                final_status = 'in_review'
                self.processing_stats['in_review'] += 1
                result['review_reason'] = '置信度较低，需要人工审核'
                
            else:
                logger.warning(f"未知执行路径: {execution_path}")
                final_status = 'unknown'
            
            # === 阶段7：更新处理结果 ===
            result['status'] = final_status
            result['execution_result'] = execution_result
            result['decision_time_ms'] = decision_time
            
            logger.info(f"✅ 事件 {event_id} 处理完成")
            logger.info(f"  状态: {final_status}, 路径: {execution_path}")
            logger.info(f"  决策: {decision_type}, 置信度: {decision_confidence:.2f}")
            
            # 记录判重检查情况
            if result.get('deduplication_info'):
                dedup_info = result['deduplication_info']
                if dedup_info.get('should_merge', False):
                    logger.info(f"  🔍 判重结果: 合并到 {dedup_info.get('target_theme', '未知')}")
                else:
                    logger.info(f"  🔍 判重结果: 未检测到重复")
            
            if result.get('ai_decision_overridden', False):
                logger.info(f"  🔥 AI决策被判重检查覆盖！")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 事件 {event_id} 处理失败: {e}", exc_info=True)
            self.processing_stats['failed'] += 1
            
            result['status'] = 'failed'
            result['error'] = str(e)
            result['error_type'] = type(e).__name__
            
            return result
    
    async def _check_duplication(self, event: Dict, ai_decision: Dict, 
                               related_themes: List[Dict]) -> Dict:
        """执行判重检查"""
        self.component_usage['dedup_engine_used'] += 1
        
        new_theme_name = ai_decision.get('target_theme_name', event.get('title', '新题材'))
        
        try:
            dedup_result = await self.dedup_engine.check_duplication(
                new_theme_name=new_theme_name,
                event_data=event,
                existing_themes=related_themes
            )
            
            return {
                'should_merge': dedup_result.should_merge,
                'target_theme': dedup_result.target_theme.get('name') if dedup_result.target_theme else '',
                'similarity': dedup_result.similarity_score,
                'match_type': dedup_result.match_type,
                'reason': dedup_result.reason,
                'confidence': dedup_result.confidence
            }
        except Exception as e:
            logger.error(f"判重检查失败: {e}")
            self.component_usage['dedup_engine_failed'] += 1
            return {'should_merge': False, 'error': str(e)}
    
    async def _fetch_related_themes(self, event: Dict) -> List[Dict]:
        """检索相关题材"""
        if self.theme_fetcher:
            try:
                self.component_usage['theme_fetcher_used'] += 1
                themes = await self.theme_fetcher.fetch_related_themes(
                    event_data=event,
                    limit=5
                )
                return themes
            except Exception as e:
                self.component_usage['theme_fetcher_failed'] += 1
                logger.error(f"theme_fetcher检索失败: {e}")
        
        # 降级：返回模拟数据
        return self._get_mock_related_themes(event)
    
    def _get_mock_related_themes(self, event: Dict) -> List[Dict]:
        """获取模拟相关题材"""
        industries = event.get('impact_industries', [])
        mock_themes = []
        
        base_themes = [
            {"id": 1, "name": "人工智能", "keywords": "AI,人工智能", "event_count": 50},
            {"id": 2, "name": "AI眼镜", "keywords": "眼镜,AI,智能穿戴", "event_count": 8},
            {"id": 3, "name": "新能源汽车", "keywords": "电动车,新能源", "event_count": 45},
            {"id": 4, "name": "半导体芯片", "keywords": "芯片,半导体", "event_count": 35},
            {"id": 5, "name": "消费电子", "keywords": "消费电子,智能设备", "event_count": 60}
        ]
        
        for theme in base_themes:
            keywords = theme.get('keywords', '').split(',')
            for industry in industries:
                if any(industry in kw for kw in keywords) or any(kw in industry for kw in keywords):
                    mock_themes.append(theme)
                    break
        
        return mock_themes[:5]
    
    def _determine_execution_path(self, 
                                 directive_action: str,
                                 directive_confidence: float,
                                 decision_type: str,
                                 decision_confidence: float) -> str:
        """
        根据两阶段结果决定执行路径
        """
        logger.debug(f"路径决策: type={decision_type}, conf={decision_confidence:.2f}")
        
        if decision_type == 'IGNORE' and decision_confidence > self.ignore_threshold:
            return 'skip'
        
        if decision_type == 'CREATE_NEW':
            if decision_confidence >= self.fast_track_threshold:
                return 'fast_track_create'
            elif decision_confidence >= self.review_threshold:
                logger.info(f"🎯 CREATE_NEW决策进入guided_create路径 (置信度: {decision_confidence:.2f})")
                return 'guided_create'
            else:
                return 'review_pool'
        
        elif decision_type == 'MERGE_INTO':
            if decision_confidence >= self.review_threshold:
                return 'guided_merge'
            else:
                return 'review_pool'
        
        elif decision_type == 'CLUSTER':
            if directive_action == 'CREATE_NEW' and directive_confidence > 0.7:
                return 'guided_create'
            else:
                return 'review_pool'
        
        else:
            return 'review_pool'
    
    async def _execute_merge(self, event: Dict, ai_decision: Dict) -> Dict:
        """执行归并操作"""
        target_theme = ai_decision.get('target_theme_name', '未知题材')
        return {
            'action': 'merge',
            'target_theme_name': target_theme,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _execute_create(self, event: Dict, ai_decision: Dict) -> Dict:
        """执行创建新题材操作"""
        new_theme_name = ai_decision.get('target_theme_name', '新题材')
        return {
            'action': 'create',
            'new_theme_name': new_theme_name,
            'timestamp': datetime.now().isoformat()
        }
    
    async def _add_to_review_queue(self, event: Dict, ai_decision: Dict, related_themes: List[Dict]):
        """添加到审查队列"""
        logger.info(f"事件 {event.get('id')} 进入审查队列")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取处理统计信息"""
        return {
            **dict(self.processing_stats),
            'component_usage': dict(self.component_usage)
        }
    
    def get_engine_info(self) -> Dict[str, Any]:
        """获取引擎信息"""
        return {
            'engine_version': 'enhanced_final_fixed_v1',
            'components_available': {
                'theme_fetcher': self.theme_fetcher is not None,
                'dedup_engine': self.dedup_engine is not None,
                'db_manager': self.db is not None
            },
            'thresholds': {
                'fast_track_threshold': self.fast_track_threshold,
                'review_threshold': self.review_threshold,
                'ignore_threshold': self.ignore_threshold,
                'dedup_threshold': self.dedup_threshold
            },
            'paths_triggered': {
                'guided_create': self.processing_stats['guided_create_path'],
                'fast_track_create': self.processing_stats['fast_track_create_path'],
                'guided_merge': self.processing_stats['guided_merge_path']
            },
            'dedup_coverage': {
                'guided_merge_with_dedup': self.processing_stats['guided_merge_with_dedup'],
                'fast_track_with_dedup': self.processing_stats['fast_track_with_dedup'],
                'ai_decision_overridden': self.processing_stats['ai_decision_overridden']
            }
        }


# 测试函数
async def test_final_fixed_engine():
    """测试最终修复版引擎"""
    print("🧪 测试最终修复版EnhancedThemeDiscoveryEngine...")
    
    # 创建模拟AI客户端
    class MockAIClient:
        async def analyze_event_with_context(self, event_data, related_themes):
            event_id = event_data.get('id', '')
            
            # 根据事件ID返回不同的决策
            if 'duplicate' in event_id:
                return {
                    "decision": "MERGE_INTO",
                    "target_theme_name": "人工智能",
                    "confidence": 0.78,
                    "reason": "测试重复事件",
                    "source": "test_mock"
                }
            else:
                return {
                    "decision": "CREATE_NEW",
                    "target_theme_name": event_data.get('title', '新题材'),
                    "confidence": 0.88,
                    "reason": "测试独特事件",
                    "source": "test_mock"
                }
    
    # 创建模拟判重引擎
    class MockDedupEngine:
        async def check_duplication(self, new_theme_name, event_data, existing_themes):
            print(f"[判重测试] 检查: {new_theme_name}")
            
            # 模拟判重逻辑
            for theme in existing_themes:
                existing_name = theme.get('name', '')
                if existing_name and existing_name in new_theme_name:
                    print(f"[判重测试] 🔍 检测到包含关系重复: {new_theme_name} -> {existing_name}")
                    return type('Result', (), {
                        'should_merge': True,
                        'target_theme': theme,
                        'similarity_score': 0.85,
                        'match_type': 'inclusion',
                        'reason': f'包含关系: {existing_name} ⊆ {new_theme_name}',
                        'confidence': 0.8
                    })()
                elif existing_name and new_theme_name in existing_name:
                    print(f"[判重测试] 🔍 检测到被包含关系重复: {new_theme_name} -> {existing_name}")
                    return type('Result', (), {
                        'should_merge': True,
                        'target_theme': theme,
                        'similarity_score': 0.75,
                        'match_type': 'inclusion',
                        'reason': f'被包含关系: {new_theme_name} ⊆ {existing_name}',
                        'confidence': 0.7
                    })()
            
            print(f"[判重测试] ✅ 未检测到重复: {new_theme_name}")
            return type('Result', (), {
                'should_merge': False,
                'similarity_score': 0.3,
                'match_type': 'distinct',
                'reason': '未检测到重复',
                'confidence': 0.6
            })()
    
    # 创建测试事件
    test_events = [
        {
            "id": "test_exact_duplicate",
            "title": "人工智能",  # 精确重复
            "summary": "人工智能事件",
            "event_type": "技术",
            "impact_industries": ["人工智能"],
            "theme_directive": {"action": "CREATE_NEW", "confidence": 0.75, "reason": "测试"}
        },
        {
            "id": "test_inclusion_duplicate",
            "title": "人工智能芯片技术",  # 包含关系重复
            "summary": "人工智能芯片技术",
            "event_type": "技术突破",
            "impact_industries": ["人工智能", "半导体"],
            "theme_directive": {"action": "CREATE_NEW", "confidence": 0.78, "reason": "测试"}
        },
        {
            "id": "test_unique",
            "title": "量子计算突破",  # 独特事件
            "summary": "量子计算突破",
            "event_type": "技术突破",
            "impact_industries": ["量子计算"],
            "theme_directive": {"action": "CREATE_NEW", "confidence": 0.85, "reason": "测试"}
        }
    ]
    
    # 创建引擎
    ai_client = MockAIClient()
    dedup_engine = MockDedupEngine()
    
    engine = EnhancedThemeDiscoveryEngine(
        ai_client=ai_client,
        dedup_engine=dedup_engine,
        config={
            'fast_track_threshold': 0.85,
            'review_threshold': 0.65,
            'ignore_threshold': 0.3
        }
    )
    
    # 处理事件
    results = []
    for event in test_events:
        print(f"\n{'='*60}")
        result = await engine.process_single_event(event)
        results.append(result)
    
    # 显示统计
    print(f"\n📊 引擎统计:")
    stats = engine.get_stats()
    for key, value in stats.items():
        if key != 'component_usage':
            print(f"  {key}: {value}")
    
    print(f"\n🔧 组件使用:")
    for component, count in stats.get('component_usage', {}).items():
        print(f"  {component}: {count}")
    
    print(f"\n✅ 测试完成!")
    return results


if __name__ == "__main__":
    asyncio.run(test_final_fixed_engine())