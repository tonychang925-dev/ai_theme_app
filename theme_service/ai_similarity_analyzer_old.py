"""
AI主题相似性分析器 - 适配新数据结构版
🚀 修复：适配新的数据结构，正确处理完整原始内容
🔥 简化：移除冗余逻辑，专注于AI分析
"""
import logging
from typing import Dict, List, Any, Optional
import json
import re

logger = logging.getLogger(__name__)

class AIThemeSimilarityAnalyzer:
    """AI主题相似性分析器（适配新数据结构）"""
    
    def __init__(self, llm_parser):
        self.llm_parser = llm_parser
        self.analysis_count = 0
        self.success_count = 0
        logger.info("✅ AIThemeSimilarityAnalyzer初始化完成（适配新数据结构）")
    
    async def analyze_similarity(self,
                                event_data: Dict[str, Any],
                                existing_themes: List[Dict[str, Any]],
                                top_n: int = 5) -> Dict[str, Any]:
        """分析事件与现有主题的相似性"""
        self.analysis_count += 1
        event_id = event_data.get('news_id', event_data.get('id', 'unknown'))
        
        # 调试：显示事件数据结构
        logger.debug(f"事件 {event_id} 数据字段: {list(event_data.keys())}")
        
        if not existing_themes:
            logger.info(f"没有现有主题，事件: {event_id} 将创建新主题")
            return self._get_create_new_result(event_data)
        
        try:
            prompt = self._build_enhanced_prompt(event_data, existing_themes, top_n)
            logger.info(f"开始AI相似性分析，事件: {event_id}, 主题数: {len(existing_themes)}")
            
            analysis_result = await self.llm_parser.parse_content(prompt)
            
            if analysis_result and isinstance(analysis_result, dict):
                self.success_count += 1
                processed_result = self._process_analysis_result(analysis_result, existing_themes)
                logger.info(f"✅ AI分析成功，事件: {event_id}")
                return processed_result
            else:
                logger.warning(f"❌ AI分析返回无效结果，事件: {event_id}")
                return self._get_create_new_result(event_data)
                
        except Exception as e:
            logger.error(f"❌ AI相似性分析失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return self._get_create_new_result(event_data)
    
    def _build_enhanced_prompt(self, 
                              event_data: Dict[str, Any], 
                              existing_themes: List[Dict[str, Any]],
                              top_n: int) -> str:
        """构建增强提示词（适配新数据结构）"""
        # 格式化事件信息（适配新结构）
        event_info = self._format_event_for_ai_new_structure(event_data)
        themes_info = self._format_themes_for_ai(existing_themes)
        
        prompt = f"""
# 🎯 任务：基于完整上下文判断事件与现有主题的相似性

## 📋 已有主题的完整信息
{themes_info}

## 🆕 新事件详情（完整信息）
{event_info}

## 🔍 重要要求
1. 必须基于事件的完整原始内容进行分析，不是只看标题
2. 相似主题应该合并，避免过度细分
3. 必须从现有主题列表中选择，不要创建新主题名称
4. 注意查看事件的行业信息和主题决策（CLUSTER/CREATE_NEW）

## 📊 请输出以下JSON格式：
{{
"most_similar_theme": {{
    "theme_name": "最相似的主题名称（必须从现有主题中选择）",
    "similarity_score": 0.85,
    "similarity_reason": "详细的相似性理由，基于完整内容分析",
    "confidence": 0.9,
    "should_create_new": false
}},
"similar_themes": [],
"analysis_summary": "总体分析摘要",
"recommendation": "MERGE_WITH_EXISTING",
"recommendation_reason": "推荐理由"
}}

请基于完整信息进行详细分析，确保输出有效的JSON格式。
"""
        return prompt
    
    def _format_event_for_ai_new_structure(self, event_data: Dict[str, Any]) -> str:
        """格式化事件信息供AI分析（适配新数据结构）"""
        lines = []
        
        # 🔥 适配新结构：获取news_id
        event_id = event_data.get('news_id', event_data.get('id', 'unknown'))
        lines.append(f"事件ID: {event_id}")
        
        # 🔥 关键：从original_news获取标题和完整内容
        original_title = ""
        full_content = ""
        content_source = "unknown"
        
        if 'original_news' in event_data:
            original_news = event_data['original_news']
            original_title = original_news.get('title', '无标题')
            full_content = original_news.get('content', '')
            content_source = 'original_news'
            lines.append(f"标题: {original_title}")
            
            # 添加内容预览
            if full_content and len(full_content) > 100:
                preview_length = min(1000, len(full_content))
                lines.append(f"\n📖 完整内容预览 ({preview_length}/{len(full_content)}字符):")
                lines.append(f"{full_content[:preview_length]}...")
            elif full_content:
                lines.append(f"\n📖 内容: {full_content}")
            else:
                lines.append(f"\n⚠️  注意：原始内容为空")
                logger.warning(f"事件 {event_id} 的original_news.content为空")
        else:
            lines.append(f"⚠️  警告：缺少original_news字段")
            # 尝试从其他字段获取
            if 'title' in event_data:
                lines.append(f"标题: {event_data.get('title')}")
        
        # 🔥 适配新结构：从event_info获取事件信息
        event_type = "未知"
        impact_industries = []
        direction = "中性"
        event_confidence = 0.5
        
        if 'event_info' in event_data:
            event_info = event_data['event_info']
            event_type = event_info.get('event_type', '未知')
            impact_industries = event_info.get('impact_industries', [])
            direction = event_info.get('direction', '中性')
            event_confidence = event_info.get('event_confidence', 0.5)
        
        lines.append(f"\n事件类型: {event_type}")
        if impact_industries:
            lines.append(f"影响行业: {', '.join(impact_industries)}")
        lines.append(f"市场方向: {direction}")
        lines.append(f"事件置信度: {event_confidence}")
        
        # 🔥 适配新结构：从theme_discovery_directive获取主题决策
        theme_action = "CLUSTER"
        decision_confidence = 0.5
        decision_reason = ""
        
        if 'theme_discovery_directive' in event_data:
            directive = event_data['theme_discovery_directive']
            theme_action = directive.get('action', 'CLUSTER')
            decision_confidence = directive.get('decision_confidence', 0.5)
            decision_reason = directive.get('reason', '')
        
        lines.append(f"\n主题发现决策: {theme_action}")
        lines.append(f"决策置信度: {decision_confidence}")
        if decision_reason and len(decision_reason) > 50:
            lines.append(f"决策理由: {decision_reason[:100]}...")
        elif decision_reason:
            lines.append(f"决策理由: {decision_reason}")
        
        # 🔥 关键：如果有full_context字段，添加它（从related_theme_fetcher传递）
        if 'full_context' in event_data:
            full_ctx = event_data['full_context']
            if full_ctx and len(full_ctx) > 100:
                lines.append(f"\n🎯 AI分析上下文 ({len(full_ctx)}字符):")
                lines.append(f"{full_ctx[:800]}...")
                logger.info(f"事件 {event_id} 使用full_context，长度: {len(full_ctx)}")
        
        # 添加内容来源标记
        lines.append(f"\n📌 内容来源: {content_source}")
        lines.append(f"总内容长度: {len(full_content)}字符")
        
        return "\n".join(lines)
    
    def _format_themes_for_ai(self, themes: List[Dict[str, Any]]) -> str:
        """格式化主题信息供AI分析"""
        if not themes:
            return "暂无现有主题"
        
        formatted = []
        for i, theme in enumerate(themes):
            theme_info = []
            
            # 获取主题名称
            theme_name = self._get_theme_name(theme)
            theme_info.append(f"\n=== 主题{i+1}: {theme_name} ===")
            
            # 获取描述
            description = self._get_theme_description(theme)
            if description:
                if len(description) > 200:
                    theme_info.append(f"描述: {description[:200]}...")
                else:
                    theme_info.append(f"描述: {description}")
            
            # 获取关键词
            keywords = self._get_theme_keywords(theme)
            if keywords:
                keywords_str = ', '.join(keywords[:8])  # 最多显示8个关键词
                if len(keywords) > 8:
                    keywords_str += f"... (共{len(keywords)}个)"
                theme_info.append(f"关键词: {keywords_str}")
            
            # 获取事件数量（如果有）
            event_count = self._get_theme_event_count(theme)
            if event_count:
                theme_info.append(f"相关事件数: {event_count}")
            
            # 获取置信度（如果有）
            confidence = self._get_theme_confidence(theme)
            if confidence:
                theme_info.append(f"置信度: {confidence}")
            
            # 如果有上下文信息，添加
            if 'context' in theme and isinstance(theme['context'], dict):
                ctx = theme['context']
                if 'common_industries' in ctx and ctx['common_industries']:
                    industries = ', '.join(ctx['common_industries'][:3])
                    theme_info.append(f"常见行业: {industries}")
            
            formatted.append("\n".join(theme_info))
        
        return "\n".join(formatted)
    
    def _get_theme_name(self, theme) -> str:
        if hasattr(theme, 'name'):
            return getattr(theme, 'name', '未知主题')
        return theme.get('name', theme.get('theme_name', '未知主题'))
    
    def _get_theme_description(self, theme) -> str:
        if hasattr(theme, 'description'):
            desc = getattr(theme, 'description', '')
        else:
            desc = theme.get('description', theme.get('theme_description', ''))
        
        # 如果没有描述，使用AI描述
        if not desc and 'ai_description' in theme:
            desc = theme.get('ai_description', '')
        
        return desc
    
    def _get_theme_keywords(self, theme) -> list:
        if hasattr(theme, 'keywords'):
            keywords = getattr(theme, 'keywords', [])
        else:
            keywords = theme.get('keywords', [])
        return keywords if isinstance(keywords, list) else []
    
    def _get_theme_event_count(self, theme) -> int:
        if hasattr(theme, 'event_count'):
            return getattr(theme, 'event_count', 0)
        return theme.get('event_count', 0)
    
    def _get_theme_confidence(self, theme) -> float:
        if hasattr(theme, 'confidence'):
            return getattr(theme, 'confidence', 0.5)
        elif hasattr(theme, 'discovery_confidence'):
            return getattr(theme, 'discovery_confidence', 0.5)
        return theme.get('confidence', theme.get('discovery_confidence', 0.5))
    
    def _process_analysis_result(self, raw_result: Dict[str, Any],
                                existing_themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """处理AI分析结果"""
        if not raw_result:
            logger.warning("AI返回结果为空")
            return self._get_create_new_result()
        
        most_similar = raw_result.get('most_similar_theme', {})
        theme_name = most_similar.get('theme_name', '')
        
        # 🔥 验证主题名称是否存在
        if theme_name:
            theme_exists = any(self._get_theme_name(theme) == theme_name for theme in existing_themes)
            if not theme_exists:
                logger.warning(f"AI推荐的主题不存在: {theme_name}")
                # 尝试找到最相似的主题
                if existing_themes:
                    # 使用第一个主题作为后备
                    first_theme = existing_themes[0]
                    backup_name = self._get_theme_name(first_theme)
                    most_similar['theme_name'] = backup_name
                    most_similar['similarity_reason'] = f'AI推荐的主题"{theme_name}"不存在，使用"{backup_name}"'
                    theme_name = backup_name
        
        result = {
            'most_similar_theme': most_similar,
            'similar_themes': raw_result.get('similar_themes', []),
            'analysis_summary': raw_result.get('analysis_summary', ''),
            'recommendation': raw_result.get('recommendation', 'MERGE_WITH_EXISTING'),
            'recommendation_reason': raw_result.get('recommendation_reason', '')
        }
        
        # 🔥 如果没有找到相似主题，使用后备方案
        if not result['most_similar_theme'].get('theme_name') and existing_themes:
            first_theme = existing_themes[0]
            result['most_similar_theme'] = {
                'theme_name': self._get_theme_name(first_theme),
                'similarity_score': 0.5,
                'similarity_reason': '自动选择第一个现有主题',
                'confidence': 0.6,
                'should_create_new': False
            }
            result['recommendation'] = 'MERGE_WITH_EXISTING'
        
        # 🔥 调试信息
        logger.debug(f"处理后的结果 - 推荐主题: {result['most_similar_theme'].get('theme_name')}")
        logger.debug(f"推荐动作: {result.get('recommendation')}")
        
        return result
    
    def _get_create_new_result(self, event_data: Dict[str, Any] = None) -> Dict[str, Any]:
        """获取创建新主题的结果"""
        theme_name = "未分类主题"
        
        if event_data:
            # 🔥 尝试从original_news.title生成主题名
            if 'original_news' in event_data:
                title = event_data['original_news'].get('title', '')
            else:
                title = event_data.get('title', '')
            
            if title:
                # 提取中文关键词
                chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', title)
                if chinese_words:
                    # 取前两个词，但避免重复
                    words = []
                    for word in chinese_words[:2]:
                        if word not in words:
                            words.append(word)
                    theme_name = f"{''.join(words)}相关"
                    logger.info(f"从标题生成主题名: {theme_name} (原标题: {title[:30]}...)")
        
        return {
            'most_similar_theme': {
                'theme_name': theme_name,
                'similarity_score': 0.1,
                'similarity_reason': '没有现有主题或AI分析失败，需要创建新主题',
                'confidence': 0.3,
                'should_create_new': True
            },
            'similar_themes': [],
            'analysis_summary': '没有现有主题可比较，建议创建新主题',
            'recommendation': 'CREATE_NEW',
            'recommendation_reason': '没有现有主题或AI分析失败'
        }
    
    async def get_similarity_metrics(self) -> Dict[str, Any]:
        """获取分析指标"""
        success_rate = self.success_count / self.analysis_count if self.analysis_count > 0 else 0
        return {
            'total_analyses': self.analysis_count,
            'successful_analyses': self.success_count,
            'success_rate': success_rate,
            'parser_provider': getattr(self.llm_parser, 'provider', 'unknown')
        }
    
    async def health_check(self) -> bool:
        """健康检查"""
        if not self.llm_parser:
            return False
        try:
            return await self.llm_parser.health_check()
        except:
            return False