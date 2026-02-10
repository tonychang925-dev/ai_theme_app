"""
增强版AI主题客户端 - 适配新数据结构版
🔥 适配修复后的数据结构，正确处理完整原始内容
"""
import logging
from typing import Dict, List, Any, Optional
import re

logger = logging.getLogger(__name__)


class EnhancedAIThemeClient:
    """
    增强版AI主题客户端 - 适配新数据结构
    
    🔥 关键修复：
    1. 适配新数据结构：event_info + theme_discovery_directive + original_news
    2. 正确处理完整原始内容：original_news.content
    3. 移除旧字段访问：summary, id等
    """
    
    def __init__(self, llm_parser=None):
        """
        初始化AI客户端
        
        Args:
            llm_parser: LLMParser实例，如果为None则自动创建
        """
        if llm_parser is None:
            try:
                from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
                self.llm_parser = ReliableDeepSeekParser(
                    config={
                        'max_retries': 3,
                        'timeout': 45,
                        'temperature': 0.1,
                        'enable_cache': True
                    }
                )
            except ImportError:
                # 后备方案：使用基础解析器
                from model_service.llm_parser.deepseek_parser_0203 import DeepSeekParser
                self.llm_parser = DeepSeekParser()
        else:
            self.llm_parser = llm_parser
        
        # 创建主题分析器
        try:
            from theme_service.ai_similarity_analyzer import AIThemeSimilarityAnalyzer
            self.theme_analyzer = AIThemeSimilarityAnalyzer(self.llm_parser)
        except ImportError as e:
            logger.error(f"❌ 无法导入AIThemeSimilarityAnalyzer: {e}")
            self.theme_analyzer = None
        
        logger.info("✅ EnhancedAIThemeClient初始化完成（适配新数据结构）")
    
    async def analyze_theme_context(self,
                                   event_data: Dict[str, Any],
                                   related_themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        🚀 分析主题上下文 - 适配新数据结构
        
        基于事件和现有主题信息，做出主题决策
        
        Args:
            event_data: 事件数据（新结构）
            related_themes: 相关主题列表
            
        Returns:
            AI决策结果
        """
        # 🔥 适配新结构：获取news_id
        event_id = event_data.get('news_id', event_data.get('id', 'unknown'))
        
        logger.info(f"开始上下文分析，事件: {event_id}, 相关题材数: {len(related_themes)}")
        
        try:
            # 检查是否有主题分析器
            if not self.theme_analyzer:
                logger.error("❌ 主题分析器未初始化")
                return self._get_default_decision_new_structure(event_data)
            
            # 使用AI相似性分析器进行分析
            similarity_result = await self.theme_analyzer.analyze_similarity(
                event_data=event_data,
                existing_themes=related_themes,
                top_n=min(5, len(related_themes))
            )
            
            # 提取最相似主题
            most_similar = similarity_result.get('most_similar_theme', {})
            similar_themes = similarity_result.get('similar_themes', [])
            
            # 构建决策结果
            decision = self._make_decision_from_analysis(
                most_similar, 
                similar_themes, 
                similarity_result.get('recommendation', 'CREATE_NEW')
            )
            
            # 添加分析摘要
            decision['analysis_summary'] = similarity_result.get('analysis_summary', '')
            decision['similarity_analysis'] = similarity_result
            
            logger.info(f"上下文分析完成，事件: {event_id}, 决策: {decision.get('decision')}, 置信度: {decision.get('confidence', 0)}")
            
            return decision
            
        except Exception as e:
            logger.error(f"❌ 上下文分析失败，事件: {event_id}, 错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 返回默认决策
            return self._get_default_decision_new_structure(event_data)
    
    def _make_decision_from_analysis(self,
                                   most_similar: Dict[str, Any],
                                   similar_themes: List[Dict[str, Any]],
                                   recommendation: str) -> Dict[str, Any]:
        """
        从分析结果中生成决策
        """
        theme_name = most_similar.get('theme_name', '')
        similarity_score = most_similar.get('similarity_score', 0)
        confidence = most_similar.get('confidence', similarity_score)
        should_create_new = most_similar.get('should_create_new', False)
        
        # 如果AI明确要求创建新主题
        if should_create_new:
            return {
                'decision': 'CREATE_NEW',
                'target_theme_name': self._generate_theme_name_from_analysis(most_similar),
                'confidence': confidence,
                'reason': most_similar.get('similarity_reason', 'AI建议创建新主题')
            }
        
        # 根据相似度分数和推荐决定
        if not theme_name or similarity_score < 0.3:
            # 没有相似主题或相似度很低，创建新主题
            return {
                'decision': 'CREATE_NEW',
                'target_theme_name': self._generate_theme_name_from_analysis(most_similar),
                'confidence': max(0.3, confidence),
                'reason': f'未找到相似主题或相似度过低 ({similarity_score:.2f})'
            }
        elif similarity_score >= 0.7:
            # 高度相似，合并到现有主题
            return {
                'decision': 'MERGE_WITH_EXISTING',
                'target_theme_name': theme_name,
                'confidence': confidence,
                'reason': f'高度相似 ({similarity_score:.2f})，建议合并'
            }
        elif similarity_score >= 0.5:
            # 中度相似，可以合并
            return {
                'decision': 'MERGE_WITH_EXISTING',
                'target_theme_name': theme_name,
                'confidence': confidence * 0.8,  # 降低置信度
                'reason': f'中度相似 ({similarity_score:.2f})，可考虑合并'
            }
        else:
            # 低相似度，根据推荐决定
            if recommendation == 'CLUSTER' and theme_name:
                return {
                    'decision': 'MERGE_WITH_EXISTING',
                    'target_theme_name': theme_name,
                    'confidence': confidence * 0.6,
                    'reason': f'低相似度但AI建议合并 ({similarity_score:.2f})'
                }
            else:
                return {
                    'decision': 'CREATE_NEW',
                    'target_theme_name': self._generate_theme_name_from_analysis(most_similar),
                    'confidence': 0.5,
                    'reason': f'相似度不足 ({similarity_score:.2f})，创建新主题'
                }
    
    def _generate_theme_name_from_analysis(self, analysis_result: Dict[str, Any]) -> str:
        """从分析结果中生成主题名称"""
        # 如果有相似主题，基于它生成
        theme_name = analysis_result.get('theme_name', '')
        if theme_name and theme_name != "未分类主题":
            # 添加"新"前缀表示新主题
            if not theme_name.startswith('新'):
                return f"新{theme_name}"
            return theme_name
        
        # 从相似性理由中提取关键词
        reason = analysis_result.get('similarity_reason', '')
        if reason:
            # 简单提取：找最长的中文词
            chinese_words = re.findall(r'[\u4e00-\u9fff]{2,}', reason)
            if chinese_words:
                # 取最长的词作为主题基础
                longest_word = max(chinese_words, key=len)
                return f"{longest_word}相关主题"
        
        # 默认名称
        return "未分类主题"
    
    def _get_default_decision_new_structure(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """获取默认决策 - 适配新结构"""
        # 🔥 适配新结构：从original_news获取标题
        title = ''
        if 'original_news' in event_data:
            original_news = event_data['original_news']
            if isinstance(original_news, dict):
                title = original_news.get('title', '')
        
        # 如果original_news中没有，尝试从其他字段获取
        if not title:
            title = event_data.get('title', '')
        
        # 从标题中提取主题名称
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
        
        if chinese_words:
            theme_name = chinese_words[0] + "相关"
        else:
            # 尝试从impact_industries获取
            event_info = event_data.get('event_info', {})
            industries = event_info.get('impact_industries', [])
            if industries:
                theme_name = industries[0] + "相关"
            else:
                theme_name = "未分类"
        
        return {
            'decision': 'CREATE_NEW',
            'target_theme_name': theme_name,
            'confidence': 0.5,
            'reason': 'AI分析失败，使用默认决策',
            'theme_description': f'关于{theme_name}的事件主题',
            'is_default': True
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        try:
            return await self.llm_parser.health_check()
        except:
            return False
    
    async def get_client_info(self) -> Dict[str, Any]:
        """获取客户端信息"""
        try:
            ai_health = await self.health_check()
            parser_info = self.llm_parser.get_parser_info() if hasattr(self.llm_parser, 'get_parser_info') else {}
            
            return {
                'client_name': 'EnhancedAIThemeClient',
                'ai_healthy': ai_health,
                'parser_info': parser_info,
                'has_theme_analyzer': self.theme_analyzer is not None,
                'data_structure': '适配新结构',
                'version': '1.1.0'
            }
        except:
            return {
                'client_name': 'EnhancedAIThemeClient',
                'ai_healthy': False,
                'data_structure': '适配新结构',
                'version': '1.1.0'
            }
    
    # 🚀 适配新结构的兼容方法
    
    async def analyze_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        向后兼容：分析事件（适配新结构）
        
        Args:
            event_data: 事件数据（新结构）
            
        Returns:
            分析结果
        """
        logger.warning("⚠️ 使用旧接口analyze_event，建议使用analyze_theme_context")
        
        # 模拟相关主题（为了兼容性）
        related_themes = []
        
        # 适配新结构的数据
        adapted_event = self._adapt_event_to_new_structure(event_data)
        
        return await self.analyze_theme_context(adapted_event, related_themes)
    
    async def make_theme_decision(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        向后兼容：做出主题决策（适配新结构）
        
        Args:
            event_data: 事件数据（新结构）
            
        Returns:
            决策结果
        """
        logger.warning("⚠️ 使用旧接口make_theme_decision，建议使用analyze_theme_context")
        
        # 适配新结构的数据
        adapted_event = self._adapt_event_to_new_structure(event_data)
        
        # 调用analyze_theme_context，但传递空的相关主题
        return await self.analyze_theme_context(adapted_event, [])
    
    def _adapt_event_to_new_structure(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """将事件数据适配为新结构"""
        # 如果已经使用新结构，直接返回
        if 'event_info' in event_data and 'original_news' in event_data:
            return event_data
        
        # 否则尝试转换
        adapted = {}
        
        # 保留news_id
        adapted['news_id'] = event_data.get('news_id', event_data.get('id', 'unknown'))
        
        # 构建event_info
        adapted['event_info'] = {
            'event_type': event_data.get('event_type', '未知'),
            'impact_industries': event_data.get('impact_industries', []),
            'direction': event_data.get('direction', '中性'),
            'event_confidence': event_data.get('confidence', 0.5)
        }
        
        # 构建original_news
        adapted['original_news'] = {
            'title': event_data.get('title', ''),
            'content': event_data.get('content', event_data.get('summary', '')),
            'content_length': len(event_data.get('content', event_data.get('summary', ''))),
            'date': event_data.get('date', '')
        }
        
        # 构建theme_discovery_directive（如果有）
        if 'theme_directive' in event_data:
            adapted['theme_discovery_directive'] = {
                'action': event_data['theme_directive'].get('action', 'CLUSTER'),
                'decision_confidence': event_data['theme_directive'].get('confidence', 0.5),
                'reason': event_data['theme_directive'].get('reason', '')
            }
        
        return adapted
    
    async def analyze_event_with_themes(self,
                                       event_data: Dict[str, Any],
                                       existing_themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        🚀 新方法：基于事件和现有主题分析
        
        Args:
            event_data: 事件数据（新结构）
            existing_themes: 现有主题列表
            
        Returns:
            完整分析结果
        """
        # 适配新结构
        adapted_event = self._adapt_event_to_new_structure(event_data)
        
        # 分析主题上下文
        analysis_result = await self.analyze_theme_context(adapted_event, existing_themes)
        
        # 添加事件信息
        analysis_result['event_info'] = {
            'news_id': adapted_event.get('news_id'),
            'event_type': adapted_event.get('event_info', {}).get('event_type'),
            'industries': adapted_event.get('event_info', {}).get('impact_industries', [])
        }
        
        return analysis_result