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
            
            # 🔥 记录请求信息
            logger.info(f"📤 发送AI请求 - 事件ID: {event_id}")
            logger.info(f"   新闻标题: {event.get('original_news', {}).get('title', '无标题')}")
            logger.info(f"   新闻内容长度: {len(event.get('original_news', {}).get('content', ''))}字符")
            logger.info(f"   现有主题数: {len(existing_themes)}")
            
            # 2. 调用AI进行分析
            logger.debug(f"发送AI分析请求 - 事件ID: {event_id}")
            ai_response = await self.llm_parser.parse_content(prompt)
            
            # 🔥 记录原始AI响应
            logger.info(f"📥 收到AI响应 - 类型: {type(ai_response)}")
            if isinstance(ai_response, str):
                logger.info(f"   响应前500字符: {str(ai_response)[:500]}...")
            else:
                logger.info(f"   响应内容: {ai_response}")
            
            # 3. 解析AI响应
            analysis_result = self._parse_enhanced_response(ai_response, existing_themes)
            
            # 🔥 修复：只做基本验证，不修改AI生成的主题名
            # 如果AI返回了有效主题名，就使用它
            if not analysis_result.extracted_theme_name:
                raise ValueError("AI没有生成主题名")
            
            # 🔥 修复2：更智能的判断是否需要创建新主题
            analysis_result.should_create_new = self._should_create_new_theme(
                analysis_result, event
            )
            
            # 🔥 修复3：在主题提取结果中添加最终使用的主题名
            # 如果CLUSTER，使用数据库里的名称；如果CREATE_NEW，使用提取的名称
            final_theme_name = (
                analysis_result.extracted_theme_name if analysis_result.should_create_new
                else analysis_result.best_match_theme
            )
            
            # 5. 计算提取置信度
            analysis_result.extraction_confidence = self._calculate_extraction_confidence(
                analysis_result.extracted_theme_name,
                event
            )
            
            # 6. 返回完整结果（添加最终主题名字段）
            result = analysis_result.to_dict()
            result['event_id'] = event_id
            result['final_theme_name'] = final_theme_name  # 🔥 新增字段
            
            logger.info(f"✅ 主题提取完成 - AI生成主题: {analysis_result.extracted_theme_name} ({len(analysis_result.extracted_theme_name)}字)")
            logger.info(f"   相似性分析: 匹配到 '{analysis_result.best_match_theme}', 分数: {analysis_result.similarity_score:.3f}")
            logger.info(f"   最终决策: {'CREATE_NEW' if analysis_result.should_create_new else 'CLUSTER'} -> {final_theme_name}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 主题提取与相似性分析失败: {e}", exc_info=True)
            # 🔥 不返回默认主题名，让上层处理
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
        构建增强版提示词（🔥🔥🔥 必须包含完整的原始新闻内容！）
        """
        # 提取事件信息
        event_info = event.get('event_info', {})
        original_news = event.get('original_news', {})
        
        event_title = original_news.get('title', '无标题')
        event_content = original_news.get('content', '')
        event_industries = event_info.get('impact_industries', [])
        event_type = event_info.get('event_type', '未知类型')
        
        # 🔥🔥🔥 构建主题信息（必须包含完整关联新闻内容）
        themes_info = []
        for i, theme in enumerate(themes, 1):
            theme_info = {
                'id': i,
                'name': theme.get('name', ''),
                'description': theme.get('description', ''),
                'keywords': theme.get('keywords', []),
                'has_complete_news_content': theme.get('has_complete_content', False),
                'related_news_count': len(theme.get('related_news_full_contents', []))
            }
            
            # 🔥🔥🔥 关键修复：添加关联新闻的完整内容
            related_news_contents = []
            for j, news in enumerate(theme.get('related_news_full_contents', [])[:3]):  # 最多取3个
                news_content = {
                    'news_id': news.get('event_id', f'news_{j}'),
                    'title': news.get('title', ''),
                    'full_content': news.get('content', ''),  # 🔥 完整内容！
                    'content_length': news.get('content_length', 0),
                    'date': news.get('date', '')
                }
                related_news_contents.append(news_content)
            
            if related_news_contents:
                theme_info['related_news_full_contents'] = related_news_contents
            
            themes_info.append(theme_info)
        
        prompt = f"""# 投资主题分析任务

        你是一个专业的投资主题分析师。请基于以下新闻事件，完成两个任务：

    ## 任务1：提取核心主题名称
    基于新闻内容，提取一个简洁的投资主题名称（4-10个字）。
    要求：
    1. 体现新闻的核心投资逻辑
    2. 简洁明了，便于理解
    3. 避免通用词汇（如"科技"、"创新"）
    4. 如果是技术突破，体现技术特点
    5. 如果是产品发布，体现产品类型
    6. 如果是政策/采购，体现政策方向
    7. 名称长度4-10字，不能太短也不能太长

    ## 任务2：相似性分析
    将提取的主题与现有主题进行相似性分析，判断是否属于同一投资主题。

    ## 新闻事件信息
    - **标题**: {event_title}
    - **完整内容**: {event_content}
    - **事件类型**: {event_type}
    - **影响行业**: {', '.join(event_industries) if event_industries else '未指定'}

    ## 现有主题列表（共{len(themes)}个）
    每个主题都包含其关联新闻的完整内容：

    ```json
    {json.dumps(themes_info, ensure_ascii=False, indent=2)}
    ```

    ## 🔥 核心判断原则（必须基于完整内容分析）
    ### 1. 投资逻辑一致性原则（基于完整内容判断）
    - 同一个投资主题必须有相同的投资逻辑
    - 技术类主题与政策类主题完全不同
    - 硬件设备主题与软件AI主题完全不同

    ### 2. 具体判断规则
    - **核心原则**：判断是否服务于同一产业链趋势或投资逻辑，而不是比较事件类型。
    - **应该匹配的例子**：
        - "Meta发布智能眼镜"（产品发布）与"Rokid智能眼镜销量大增"（销售进展）→ 同属"消费电子-智能穿戴"产品放量逻辑，应该匹配。
        - "英伟达公开AR眼镜专利"（技术突破）与"索尼发布AR眼镜原型"（产品发布）→ 同属"AR硬件产业链"技术成熟化逻辑，应该匹配。
        - "MicroLED产线投资"（制造）与"AR眼镜采用MicroLED屏幕"（技术应用）→ 同属"下一代显示技术"供应链逻辑，应该匹配。
    - **不应该匹配的例子**：
        - "某市发布AI产业扶持政策"（地方政策）与"某公司推出AI算法"（技术产品）→ 政策驱动与产品驱动逻辑不同，不应匹配。
        - "智能眼镜出海"（市场拓展）与"脑机接口新专利"（全新技术）→ 市场应用与颠覆性技术逻辑不同，不应匹配。
    
    ### 3. 命名注意事项
    - 提取的主题名称要基于新闻事实
    - 相似性分析时要客观对比投资逻辑
    - 如果投资逻辑相同，即使名称表述不同也应该匹配

    ## 🔥 重要指令（必须遵守）：
    1. **必须提取主题名称**：基于新闻完整内容，提取一个具体的投资主题名称
    2. **主题名要求**：
       - 长度：4-10个字
       - 必须具体明确，反映新闻核心投资逻辑
       - **禁止使用**：'未命名主题'、'未知主题'、'新主题'、'其他'、'主题名称'、'新闻主题'等模糊词汇
       - 如果新闻内容模糊，请从标题中提取关键词组成主题名
    
    3. **无效主题名示例（禁止使用）**：
       ❌ "未命名主题"、"未命名"、"未知主题"、"新主题"、"主题名称"、"新闻主题"
       ❌ "其他"、"其他题材"、"其他主题"、"一般主题"
       ❌ 长度小于3个字或大于12个字的名称
    
    4. **有效主题名示例**：
       ✅ "AI拍摄眼镜量产" (6字)
       ✅ "MicroLED产线投资" (6字)  
       ✅ "托卡马克密度突破" (6字)
       ✅ "对日两用物项出口管制" (9字)
       ✅ "低轨卫星批产交付" (6字)
       ✅ "脑机接口精准突破" (6字)

    ## 输出格式
    请严格按照以下JSON格式输出，不要添加任何额外说明：
    {{
        "theme_extraction": {{
            "extracted_name": "基于新闻完整内容提取的主题名称（4-10字）",
            "naming_reason": "提取这个名称的理由（必须基于对完整内容的分析）",
            "content_based_analysis": "基于完整内容的具体分析（说明从内容中提取了哪些关键信息）"
        }},
        "similarity_analysis": {{
            "best_match_theme": "最相似的现有主题名称（如果投资逻辑完全不同，请返回'无匹配主题'）",
            "match_score": 0.85,
            "match_reason": "相似性分析理由（必须详细说明基于完整内容的对比分析）",
            "content_comparison": "具体内容对比分析（对比新事件和现有主题关联新闻的完整内容）",
            "is_same_domain": true
        }}
    }}

    ## 🔥 最终要求
    你的分析质量取决于你对完整新闻内容的深度理解。请仔细阅读：
    1. 新事件的完整内容
    2. 每个现有主题关联新闻的完整内容
    3. 基于完整内容进行投资逻辑分析，而不是只看标题或关键词
    4. **必须返回有效的主题名称，不能返回模糊或无效的名称**

    现在开始基于完整新闻内容的深度分析："""
        
        logger.info(f"🔥 构建增强版提示词完成，主题数: {len(themes)}")
        
        # 记录内容长度供调试
        total_content_length = len(event_content)
        for theme in themes:
            news_contents = theme.get('related_news_full_contents', [])
            if news_contents:
                total_content_length += sum(len(n.get('content', '')) for n in news_contents[:2])
        
        logger.info(f"   总内容长度: {total_content_length} 字符")
        return prompt

    def _parse_enhanced_response(self, 
                            ai_response: Any, 
                            themes: List[Dict[str, Any]]) -> ThemeAnalysisResult:
        """
        解析增强版AI响应 - 添加详细调试
        """
        try:
            # 🔥 第一步：记录原始AI响应
            logger.info(f"🔍 调试：原始AI响应类型: {type(ai_response)}")
            
            # 提取JSON
            response_data = self._extract_json_from_response(ai_response)
            
            # 🔥 第二步：记录提取的JSON数据
            logger.info(f"🔍 调试：提取的JSON数据: {json.dumps(response_data, ensure_ascii=False, indent=2)}")
            
            if not response_data:
                logger.error("❌ 无法从AI响应中提取有效数据")
                raise ValueError("无法从AI响应中提取有效数据")
            
            # 提取主题提取结果
            theme_extraction = response_data.get('theme_extraction', {})
            extracted_name = theme_extraction.get('extracted_name', '').strip()
            naming_reason = theme_extraction.get('naming_reason', '')
            
            # 🔥 第三步：检查主题提取结果
            logger.info(f"🔍 调试：提取的主题名: '{extracted_name}'")
            logger.info(f"🔍 调试：提取主题名长度: {len(extracted_name)} 字")
            logger.info(f"🔍 调试：命名理由: {naming_reason}")
            
            # 🔥 关键检查：如果主题名为空或无效，抛出异常
            banned_names = ['未命名主题', '未命名', '未知主题', '新主题', '主题名称', '新闻主题', '其他', '其他主题', '其他题材']
            if not extracted_name or extracted_name in banned_names:
                logger.error(f"❌ AI返回了无效的主题名: '{extracted_name}'")
                logger.error(f"❌ 完整提取数据: {json.dumps(theme_extraction, ensure_ascii=False)}")
                
                # 提取相似性分析结果（可能还有用）
                similarity_data = response_data.get('similarity_analysis', {})
                best_match_name = similarity_data.get('best_match_theme', '').strip()
                match_score = float(similarity_data.get('match_score', 0.0))
                
                # 抛出详细的异常
                raise ValueError(
                    f"AI返回了无效主题名: '{extracted_name}'\n"
                    f"命名理由: {naming_reason}\n"
                    f"相似匹配: {best_match_name} (得分: {match_score})\n"
                    f"请检查AI提示词和输入内容"
                )
            
            # 🔥 只做基本验证，不修改AI生成的主题名
            extracted_name = self._validate_theme_name_length(extracted_name)
            
            # 🔥 第四步：再次验证
            if not extracted_name or len(extracted_name.strip()) < 3:
                logger.error(f"❌ 验证后的主题名仍然无效: '{extracted_name}'")
                raise ValueError(f"主题名验证失败: '{extracted_name}'")
            
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
            
            logger.info(f"✅ 成功解析AI响应，AI生成主题名: '{extracted_name}'")
            return result
            
        except Exception as e:
            logger.error(f"❌ 解析增强版AI响应失败: {e}", exc_info=True)
            raise

    def _validate_theme_name_length(self, theme_name: str) -> str:
        """验证主题名称长度 - 只验证不生成"""
        if not theme_name:
            raise ValueError("AI没有返回主题名")
        
        theme_name = theme_name.strip()
        length = len(theme_name)
        
        # 检查是否包含禁止词汇
        banned_names = ['未命名主题', '未命名', '未知主题', '新主题', '主题名称', '新闻主题', '其他', '其他主题', '其他题材']
        if theme_name in banned_names:
            raise ValueError(f"AI返回了禁止的主题名: '{theme_name}'")
        
        # 检查长度
        if length < 3:
            logger.warning(f"⚠️  AI返回的主题名太短: '{theme_name}' ({length}字)")
            # 只记录警告，但返回原样（由AI负责）
        
        if length > 20:
            logger.warning(f"⚠️  AI返回的主题名太长: '{theme_name}' ({length}字)")
            # 只记录警告，但返回原样
        
        return theme_name  # 原样返回，不修改！
    
    def _should_create_new_theme(self, analysis_result: ThemeAnalysisResult, event: Dict) -> bool:
        """智能判断是否需要创建新主题"""
        # 🔥 修复1：更严格的默认规则 - 投资主题应该更倾向于聚合
        # 规则1：如果AI明确判断为无匹配，则创建新主题
        if analysis_result.is_no_match:
            logger.info(f"🎯 AI明确判断为无匹配主题，创建新主题")
            return True
        
        # 🔥 修复2：提高相似度阈值 - 投资主题应该更倾向于聚合
        # 相似度低于0.4才考虑创建新主题（原先是0.3）
        if analysis_result.similarity_score < 0.4:
            logger.info(f"🎯 相似度{analysis_result.similarity_score:.2f}低于阈值0.4，创建新主题")
            return True
        
        # 🔥 修复3：优先考虑AI的深度分析结论
        similarity_reason = analysis_result.similarity_reason.lower()
        content_comparison = getattr(analysis_result, 'content_comparison', '').lower()
        
        # 如果AI明确判断为"同一产业链"、"相同投资逻辑"等，即使相似度中等也倾向归并
        if any(keyword in similarity_reason + content_comparison for keyword in 
            ["同一产业链", "相同投资逻辑", "相同投资主题", "同属", "都属于", "类似逻辑"]):
            logger.info(f"🎯 AI深度分析认为属于相同投资逻辑，倾向归并")
            return False
        
        # 🔥 修复4：对于0.4-0.7的中等相似度，更多考虑归并而非新建
        # 投资主题分析中，中等相似度通常也应该归并
        if 0.4 <= analysis_result.similarity_score <= 0.7:
            # 检查是否是明显不同的投资逻辑
            extracted_name = analysis_result.extracted_theme_name.lower()
            best_match = analysis_result.best_match_theme.lower()
            
            # 如果名称中有明显不同的关键词才考虑新建
            tech_keywords = ["技术", "专利", "研发", "算法", "模型"]
            product_keywords = ["产品", "发布", "上市", "量产", "销售"]
            policy_keywords = ["政策", "法规", "规划", "立法", "监管"]
            
            extracted_type = None
            best_match_type = None
            
            if any(kw in extracted_name for kw in tech_keywords):
                extracted_type = "技术"
            if any(kw in best_match for kw in tech_keywords):
                best_match_type = "技术"
            if any(kw in extracted_name for kw in product_keywords):
                extracted_type = "产品"
            if any(kw in best_match for kw in product_keywords):
                best_match_type = "产品"
            if any(kw in extracted_name for kw in policy_keywords):
                extracted_type = "政策"
            if any(kw in best_match for kw in policy_keywords):
                best_match_type = "政策"
            
            # 如果类型不同，再考虑新建
            if extracted_type and best_match_type and extracted_type != best_match_type:
                logger.info(f"⚠️  投资逻辑类型不同: {extracted_type}类 vs {best_match_type}类，考虑新建")
                return True
            else:
                # 类型相同或无法判断，倾向归并
                logger.info(f"🎯 中等相似度{analysis_result.similarity_score:.2f}且投资逻辑类型一致，倾向归并")
                return False
        
        # 🔥 修复5：高相似度(>0.7)一律归并
        if analysis_result.similarity_score > 0.7:
            logger.info(f"🎯 高相似度{analysis_result.similarity_score:.2f}，强制归并")
            return False
        
        # 默认情况：归并
        logger.info(f"🎯 默认决策：归并到现有主题")
        return False
    
    def _calculate_name_similarity(self, name1: str, name2: str) -> float:
        """计算名称相似度（简单实现）"""
        if not name1 or not name2:
            return 0.0
        
        # 转换为字符集合
        set1 = set(name1)
        set2 = set(name2)
        
        if not set1 or not set2:
            return 0.0
        
        # Jaccard相似度
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0

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
        
        # 🔥 名称长度合适（4-10字）
        if 4 <= len(theme_name) <= 10:
            confidence += 0.15  # 增加权重
        elif 3 <= len(theme_name) <= 12:
            confidence += 0.05
        else:
            confidence -= 0.1
        
        # 名称在新闻中出现
        if any(char in news_text for char in theme_name):
            confidence += 0.1
        
        # 不包含无效词
        invalid_words = ['主题', '名称', '标题', '新闻', '事件', '题材']
        if not any(word in theme_name for word in invalid_words):
            confidence += 0.1
        
        # 🔥 名称包含投资相关关键词加分
        investment_keywords = ['投资', '发展', '技术', '创新', '突破', '政策', '规划']
        if any(keyword in theme_name for keyword in investment_keywords):
            confidence += 0.05
        
        return min(max(confidence, 0.1), 1.0)  # 确保在0.1-1.0之间

    def _create_error_response(self, event_id: str, error_msg: str) -> Dict[str, Any]:
        """创建错误响应"""
        return {
            'event_id': event_id,
            'theme_extraction': {
                'extracted_name': 'AI提取失败',
                'confidence': 0.0,
                'naming_reason': f'AI主题提取失败: {error_msg}'
            },
            'similarity_analysis': {
                'best_match_theme': 'AI分析失败',
                'similarity_score': 0.0,
                'similarity_reason': f'AI相似性分析失败: {error_msg}',
                'is_same_domain': False,
                'theme_id': 0
            },
            'recommendation': {
                'action': 'ERROR',
                'suggested_theme_name': 'AI分析失败',
                'confidence': 0.0,
                'reason': f'AI分析失败: {error_msg}'
            },
            'metadata': {
                'analysis_type': 'THEME_EXTRACTION_AND_SIMILARITY',
                'has_match': False,
                'should_create_new': False,
                'error': error_msg
            },
            'final_theme_name': 'AI分析失败'  # 🔥 新增字段
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