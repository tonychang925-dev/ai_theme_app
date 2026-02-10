# model_service/llm_parser/theme_analyzer.py
"""
题材分析扩展 - 向后兼容的扩展，为theme_service提供专用的AI分析能力。
严格遵循3.10方案中的“AI深度事件理解”要求。
"""
import json
import logging
from typing import Dict, Any, List, Optional
from .base_parser import BaseLLMParser  # 假设您已有此抽象基类

logger = logging.getLogger(__name__)

class ThemeAnalyzer:
    """题材分析器 - 包装现有的LLM解析器，提供面向题材发现的深度分析"""

    def __init__(self, llm_parser: BaseLLMParser):
        self.llm_parser = llm_parser
        logger.info("ThemeAnalyzer initialized.")

    async def analyze_for_theme_discovery(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析事件以发现题材（核心方法）
        对应方案中的“语义理解层”和“市场映射层”。
        """
        prompt = self._build_theme_analysis_prompt(event_data)
        logger.debug(f"Generated theme discovery prompt for event: {event_data.get('id')}")

        raw_result = await self.llm_parser.parse_content(prompt)
        parsed_result = self._parse_theme_analysis(raw_result)

        # 记录并返回
        if parsed_result.get("potential_themes"):
            logger.info(f"Event {event_data.get('id')} analyzed. Potential themes: {parsed_result['potential_themes']}")
        return parsed_result

    def _build_theme_analysis_prompt(self, event_data: Dict) -> str:
        """构建符合资深分析师思维的提示词"""
        industries = ', '.join(event_data.get('impact_industries', []))
        return f"""作为资深A股/美股投资分析师，请深度剖析以下财经事件，识别其可能催生或关联的投资主题：

**事件标题**：{event_data.get('title', '')}
**事件摘要**：{event_data.get('summary', '')}
**事件类型**：{event_data.get('event_type', '')}
**影响行业**：{industries}

请从以下专业维度进行思考：
1.  **核心投资逻辑**：这件事最本质的投资故事或主线是什么？（例如：技术突破、政策红利、供需格局改变）
2.  **潜在题材概念**：根据当前市场习惯，可能形成什么新的市场概念或归类到哪些已有概念？（如“AI眼镜”、“固态电池”、“高速连接器”）
3.  **题材强度评估**：此事件对相关题材的催化强度如何？（1-10分，10分为最强）
4.  **产业链映射**：哪些具体的产业链环节（上游、中游、下游）会最受益？
5.  **市场情绪与阶段**：市场对此事件的普遍预期是乐观、悲观还是中性？事件可能处于主题炒作的哪个阶段（朦胧期、发酵期、高潮期）？

请以严格的JSON格式返回分析结果：
{{
    "core_investment_logic": "简洁的投资逻辑描述",
    "potential_themes": ["题材概念1", "题材概念2"],
    "theme_strength": {{"score": 8, "reason": "得分理由，如：龙头公司明确、事件新颖性高"}},
    "related_industries": ["细分行业A", "细分行业B"],
    "market_sentiment": {{"direction": "positive|neutral|negative", "intensity": 7}},
    "certainty": 0.85
}}
"""

    def _parse_theme_analysis(self, raw_result: Dict) -> Dict:
        """解析并清洗AI返回的JSON结果，确保数据格式稳定"""
        default_result = {
            "core_investment_logic": "",
            "potential_themes": [],
            "theme_strength": {"score": 5, "reason": "默认分数"},
            "related_industries": [],
            "market_sentiment": {"direction": "neutral", "intensity": 5},
            "certainty": 0.5
        }

        if not raw_result:
            logger.warning("AI analysis returned empty result.")
            return default_result

        # 处理可能的字符串响应
        if isinstance(raw_result, str):
            try:
                raw_result = json.loads(raw_result)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse AI response as JSON: {raw_result[:200]}")
                return default_result

        # 安全地提取字段，确保类型正确
        result = default_result.copy()
        try:
            result["core_investment_logic"] = str(raw_result.get("core_investment_logic", ""))
            result["potential_themes"] = list(raw_result.get("potential_themes", []))
            result["theme_strength"] = {
                "score": int(raw_result.get("theme_strength", {}).get("score", 5)),
                "reason": str(raw_result.get("theme_strength", {}).get("reason", ""))
            }
            result["related_industries"] = list(raw_result.get("related_industries", []))
            result["market_sentiment"] = {
                "direction": str(raw_result.get("market_sentiment", {}).get("direction", "neutral")),
                "intensity": int(raw_result.get("market_sentiment", {}).get("intensity", 5))
            }
            result["certainty"] = float(raw_result.get("certainty", 0.5))
        except (ValueError, TypeError, AttributeError) as e:
            logger.error(f"Error parsing specific fields from AI result: {e}. Raw: {raw_result}")

        return result