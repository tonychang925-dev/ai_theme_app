# theme_service/ai_similarity_analyzer.py
"""
AI主题相似性分析器 - 增强版
🔥 一次调用完成：主题提取 + 相似性分析
"""
import json
import logging
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ThemeAnalysisResult:
    """主题分析结果"""
    extracted_theme_name: str
    best_match_theme: str
    similarity_score: float
    similarity_reason: str
    is_same_domain: bool
    matched_theme_id: int = 0
    is_no_match: bool = False
    should_create_new: bool = False
    extraction_confidence: float = 0.8
    naming_reason: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'theme_extraction': {
                'extracted_name': self.extracted_theme_name,
                'confidence': self.extraction_confidence,
                'naming_reason': self.naming_reason
            },
            'similarity_analysis': {
                'best_match_theme': self.best_match_theme,
                'similarity_score': self.similarity_score,
                'similarity_reason': self.similarity_reason,
                'is_same_domain': self.is_same_domain,
                'theme_id': self.matched_theme_id
            },
            'recommendation': {
                'action': 'CREATE_NEW' if self.should_create_new else 'CLUSTER',
                'suggested_theme_name': self.extracted_theme_name if self.should_create_new else self.best_match_theme,
                'confidence': 1.0 - self.similarity_score if self.should_create_new else self.similarity_score,
                'reason': self._generate_recommendation_reason()
            },
            'metadata': {
                'analysis_type': 'THEME_EXTRACTION_AND_SIMILARITY',
                'has_match': not self.is_no_match,
                'should_create_new': self.should_create_new
            }
        }
    
    def _generate_recommendation_reason(self) -> str:
        """生成推荐理由"""
        if self.should_create_new:
            return f"新闻事件与现有主题相似度低({self.similarity_score:.2f})，建议创建新主题：'{self.extracted_theme_name}'"
        else:
            return f"新闻事件与现有主题'{self.best_match_theme}'高度相似({self.similarity_score:.2f})，建议归并"


class AIThemeSimilarityAnalyzer:
    """AI主题相似性分析器 - 增强版（主题提取 + 相似性分析）"""
    
    def __init__(self, llm_parser):
        """
        初始化分析器
        
        Args:
            llm_parser: LLM解析器实例
        """
        self.llm_parser = llm_parser
        logger.info("✅ AI主题相似性分析器初始化完成（增强版：主题提取+相似性分析）")
    
    async def analyze_with_theme_extraction(self, 
                                           event: Dict[str, Any], 
                                           existing_themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        🔥 增强版分析：一次调用完成主题提取和相似性分析
        
        Args:
            event: 事件数据
            existing_themes: 现有主题列表
            
        Returns:
            包含主题提取和相似性分析的完整结果
        """
        event_id = event.get('news_id', 'unknown')
        logger.info(f"🔍 开始主题提取与相似性分析 - 事件ID: {event_id}")
        logger.info(f"现有主题数: {len(existing_themes)}")
        
        try:
            # 1. 构建提示词（主题提取 + 相似性分析）
            prompt = self._build_enhanced_prompt(event, existing_themes)
            
            # 2. 调用AI进行分析
            logger.debug(f"发送AI分析请求 - 事件ID: {event_id}")
            ai_response = await self.llm_parser.parse_content(prompt)
            
            # 3. 解析AI响应
            analysis_result = self._parse_enhanced_response(ai_response, existing_themes)
            
            # 4. 确定是否应该创建新主题
            analysis_result.should_create_new = (
                analysis_result.is_no_match or 
                analysis_result.similarity_score < 0.3
            )
            
            # 5. 计算提取置信度
            analysis_result.extraction_confidence = self._calculate_extraction_confidence(
                analysis_result.extracted_theme_name,
                event
            )
            
            # 6. 返回完整结果
            result = analysis_result.to_dict()
            result['event_id'] = event_id
            
            logger.info(f"✅ 主题提取完成 - 提取名称: {analysis_result.extracted_theme_name}")
            logger.info(f"   相似性分析: 匹配到 '{analysis_result.best_match_theme}', 分数: {analysis_result.similarity_score:.3f}")
            logger.info(f"   推荐操作: {'CREATE_NEW' if analysis_result.should_create_new else 'CLUSTER'}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 主题提取与相似性分析失败: {e}", exc_info=True)
            return self._create_error_response(event_id, str(e))
    
    async def analyze_similarity(self, 
                                event: Dict[str, Any], 
                                existing_themes: List[Dict[str, Any]],
                                top_n: Optional[int] = None) -> Dict[str, Any]:
        """
        向后兼容：只做相似性分析
        """
        # 使用新方法但只返回相似性部分
        full_result = await self.analyze_with_theme_extraction(event, existing_themes)
        
        # 只返回相似性分析部分（兼容旧接口）
        return {
            'event_id': full_result['event_id'],
            'similarity_analysis': full_result['similarity_analysis'],
            'metadata': {
                'analysis_type': 'AI_SIMILARITY_ANALYSIS',
                'analysis_complete': True,
                'has_valid_match': not full_result['metadata']['should_create_new']
            }
        }
    
    def _build_enhanced_prompt(self, 
                              event: Dict[str, Any], 
                              themes: List[Dict[str, Any]]) -> str:
        """
        构建增强版提示词（主题提取 + 相似性分析）
        """
        # 提取事件信息
        event_info = event.get('event_info', {})
        original_news = event.get('original_news', {})
        
        event_title = original_news.get('title', '无标题')
        event_content = original_news.get('content', '')
        event_industries = event_info.get('impact_industries', [])
        event_type = event_info.get('event_type', '未知类型')
        
        # 构建主题信息
        themes_info = []
        for i, theme in enumerate(themes, 1):
            themes_info.append({
                'id': i,
                'name': theme.get('name', ''),
                'description': theme.get('description', ''),
                'keywords': theme.get('keywords', [])
            })
        
        prompt = f"""# 投资主题分析任务

        你是一个专业的投资主题分析师。请基于以下新闻事件，完成两个任务：

        ## 任务1：提取核心主题名称
        基于新闻内容，提取一个简洁的投资主题名称（2-6个字）。
        要求：
        1. 体现新闻的核心投资逻辑
        2. 简洁明了，便于理解
        3. 避免通用词汇（如"科技"、"创新"）
        4. 如果是技术突破，体现技术特点
        5. 如果是产品发布，体现产品类型
        6. 如果是政策/采购，体现政策方向

        ## 任务2：相似性分析
        将提取的主题与现有主题进行相似性分析，判断是否属于同一领域。

        ## 新闻事件信息
        - **标题**: {event_title}
        - **内容**: {event_content[:300]}{'...' if len(event_content) > 300 else ''}
        - **事件类型**: {event_type}
        - **影响行业**: {', '.join(event_industries) if event_industries else '未指定'}

        ## 现有主题列表（共{len(themes)}个）
        ```json
        {json.dumps(themes_info, ensure_ascii=False, indent=2)}

        特别注意事项
        🔥 国防航天事件
        如果新闻涉及：导弹、卫星、太空军、国防、军事、军工、安全、预警等
        应该提取国防航天相关的主题名
        与消费电子、人工智能、半导体等民用主题完全不同
        相似度应该很低（<0.3）

        🔥 民用技术事件
        如果新闻涉及：芯片、半导体、智能眼镜、消费电子等
        与相应领域的现有主题对比
        同领域相似度较高（>0.6）

        🔥 特别关键：国防航天事件的匹配原则
        绝对禁止：国防航天事件（导弹卫星、军事采购、国家安全）不能匹配到消费电子、人工智能、半导体等民用主题
        领域本质：国防航天属于国家安全领域，与民用科技领域有本质区别
        正确做法：当事件是国防航天时，应该返回"无匹配主题"，相似度 < 0.3

        匹配决策流程
        1.首先判断事件核心领域

        2.如果是国防航天、军事、国家安全领域：
        与现有民用主题对比
        如果现有主题都是民用领域 → 返回"无匹配主题"，相似度 < 0.3

        3.如果是民用技术领域：
        寻找相同或相近领域的主题
        给出合理的相似度分数

        评分与匹配规则
        相似度 < 0.3: 领域完全不同 → 返回"无匹配主题"
        相似度 0.3-0.6: 部分相关但差异明显 → 可以匹配但需说明差异
        相似度 > 0.6: 同一领域或高度相关 → 正常匹配

        输出格式
        请严格按照以下JSON格式输出，不要添加任何额外说明：
        {{
            "theme_extraction": {{
                "extracted_name": "基于新闻提取的主题名称",
                "naming_reason": "提取这个名称的理由（1-2句话）"
            }},
            "similarity_analysis": {{
                "best_match_theme": "最相似的现有主题名称（如果都不相似，请返回'无匹配主题'）",
                "match_score": 0.85,
                "match_reason": "相似性分析理由（至少包含3个具体点）",
                "is_same_domain": true
            }}
        }}

        重要提示
        主题名称不要包含"主题"、"题材"等冗余词
        相似度分数要客观反映领域相似性
        如果事件标题或内容包含：导弹、卫星、太空军、国防、军事、军工、安全、预警、跟踪、防御 等关键词，
        且现有主题都是消费电子、人工智能、半导体等民用主题，请直接返回：
        best_match_theme: "无匹配主题"
        match_score: < 0.3
        match_reason: 说明国防航天与民用领域的本质区别
        is_same_domain: false

        现在开始分析："""
        logger.debug(f"构建增强版提示词完成，主题数: {len(themes)}")
        return prompt

    def _parse_enhanced_response(self, 
                            ai_response: Any, 
                            themes: List[Dict[str, Any]]) -> ThemeAnalysisResult:
        """
        解析增强版AI响应
        """
        try:
            # 提取JSON
            response_data = self._extract_json_from_response(ai_response)
            
            if not response_data:
                raise ValueError("无法从AI响应中提取有效数据")
            
            # 提取主题提取结果
            theme_extraction = response_data.get('theme_extraction', {})
            extracted_name = theme_extraction.get('extracted_name', '').strip()
            naming_reason = theme_extraction.get('naming_reason', '')
            
            # 验证提取的主题名
            if not extracted_name or len(extracted_name) < 2:
                logger.warning("AI提取的主题名称无效")
                extracted_name = self._generate_fallback_theme_name()
            
            # 提取相似性分析结果
            similarity_data = response_data.get('similarity_analysis', {})
            best_match_name = similarity_data.get('best_match_theme', '').strip()
            match_score = float(similarity_data.get('match_score', 0.0))
            match_reason = similarity_data.get('match_reason', '')
            is_same_domain = similarity_data.get('is_same_domain', False)
            
            # 判断是否无匹配
            is_no_match = best_match_name in ["无匹配主题", "无匹配", "不匹配", "无相关主题"]
            
            # 查找匹配的主题ID
            matched_theme_id = 0
            if not is_no_match and best_match_name:
                for theme in themes:
                    if theme.get('name') == best_match_name:
                        matched_theme_id = theme.get('id', 0)
                        break
            
            # 创建结果对象
            result = ThemeAnalysisResult(
                extracted_theme_name=extracted_name,
                best_match_theme=best_match_name,
                similarity_score=match_score,
                similarity_reason=match_reason,
                is_same_domain=is_same_domain,
                matched_theme_id=matched_theme_id,
                is_no_match=is_no_match,
                naming_reason=naming_reason
            )
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 解析增强版AI响应失败: {e}")
            raise

    def _extract_json_from_response(self, ai_response: Any) -> Dict[str, Any]:
        """从AI响应中提取JSON"""
        if isinstance(ai_response, dict):
            return ai_response
        
        if isinstance(ai_response, str):
            # 尝试直接解析
            try:
                return json.loads(ai_response)
            except json.JSONDecodeError:
                # 尝试从markdown代码块中提取
                json_match = re.search(r'```json\s*(.*?)\s*```', ai_response, re.DOTALL)
                if json_match:
                    return json.loads(json_match.group(1))
                else:
                    # 尝试查找JSON对象
                    json_pattern = r'\{.*?"(theme_extraction|similarity_analysis)".*?\}'
                    match = re.search(json_pattern, ai_response, re.DOTALL)
                    if match:
                        return json.loads(match.group())
        
        raise ValueError("无法从AI响应中提取JSON数据")

    def _calculate_extraction_confidence(self, theme_name: str, event: Dict[str, Any]) -> float:
        """计算主题提取置信度"""
        # 基于名称质量和与新闻的相关性
        title = event.get('original_news', {}).get('title', '').lower()
        content = event.get('original_news', {}).get('content', '').lower()
        news_text = title + content
        
        confidence = 0.7  # 基础置信度
        
        # 名称长度合适
        if 2 <= len(theme_name) <= 8:
            confidence += 0.1
        
        # 名称在新闻中出现
        if any(char in news_text for char in theme_name):
            confidence += 0.1
        
        # 不包含无效词
        invalid_words = ['主题', '名称', '标题', '新闻', '事件', '题材']
        if not any(word in theme_name for word in invalid_words):
            confidence += 0.1
        
        return min(confidence, 1.0)

    def _generate_fallback_theme_name(self) -> str:
        """生成备选主题名"""
        return "新投资主题"

    def _create_error_response(self, event_id: str, error_msg: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            'event_id': event_id,
            'theme_extraction': {
                'extracted_name': '分析失败',
                'confidence': 0.0,
                'naming_reason': f'主题提取失败: {error_msg}'
            },
            'similarity_analysis': {
                'best_match_theme': '分析失败',
                'similarity_score': 0.0,
                'similarity_reason': f'相似性分析失败: {error_msg}',
                'is_same_domain': False,
                'theme_id': 0
            },
            'recommendation': {
                'action': 'ERROR',
                'suggested_theme_name': '分析失败',
                'confidence': 0.0,
                'reason': f'分析失败: {error_msg}'
            },
            'metadata': {
                'analysis_type': 'THEME_EXTRACTION_AND_SIMILARITY',
                'has_match': False,
                'should_create_new': False,
                'error': error_msg
            }
        }

    async def health_check(self) -> bool:
        """健康检查"""
        try:
            if hasattr(self.llm_parser, 'health_check'):
                return await self.llm_parser.health_check()
            return True
        except Exception as e:
            logger.error(f"❌ 健康检查失败: {e}")
            return False
        
class AIThemeSimilarityAnalyzerFactory:
    """AI相似性分析器工厂"""
    @staticmethod
    async def create() -> AIThemeSimilarityAnalyzer:
        """创建分析器实例"""
        try:
            from model_service.llm_parser.reliable_deepseek_parser import ReliableDeepSeekParser
            
            # 使用可靠的DeepSeek解析器
            llm_parser = ReliableDeepSeekParser(
                model_name="deepseek-chat",
                config={
                    'max_retries': 3,
                    'timeout': 60,
                    'temperature': 0.1  # 低温度确保分析一致性
                }
            )
            
            # 健康检查
            if await llm_parser.health_check():
                analyzer = AIThemeSimilarityAnalyzer(llm_parser)
                logger.info("✅ AI相似性分析器创建成功")
                return analyzer
            else:
                raise RuntimeError("AI解析器健康检查失败")
                
        except ImportError as e:
            logger.error(f"❌ 无法导入LLM解析器: {e}")
            raise
        except Exception as e:
            logger.error(f"❌ 创建分析器失败: {e}")
            raise
    
    async def create_ai_similarity_analyzer(config: Optional[Dict[str, Any]] = None) -> AIThemeSimilarityAnalyzer:
        """
        快捷创建AI相似性分析器
        Args:
        config: 可选配置参数
        
        Returns:
            AIThemeSimilarityAnalyzer实例
        """
        return await AIThemeSimilarityAnalyzerFactory.create(config)
    
    def create_ai_similarity_analyzer_sync(config: Optional[Dict[str, Any]] = None) -> AIThemeSimilarityAnalyzer:
        """
        同步创建AI相似性分析器
        Args:
        config: 可选配置参数
    
        Returns:
            AIThemeSimilarityAnalyzer实例
        """
        import asyncio

        # 获取或创建事件循环
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        # 同步调用异步创建函数
        return loop.run_until_complete(AIThemeSimilarityAnalyzerFactory.create(config))