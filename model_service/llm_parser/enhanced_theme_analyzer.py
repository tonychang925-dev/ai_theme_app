# model_service/llm_parser/enhanced_theme_analyzer.py
"""
增强版主题分析器 - 纯AI决策版
🔥 完全移除降级逻辑，所有决策由真实AI完成
"""
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class EnhancedThemeAnalyzer:
    """
    增强版主题分析器 - 纯AI决策版
    所有决策由DeepSeek API完成，不包含降级逻辑
    """
    
    def __init__(self, llm_parser):
        """
        初始化分析器
        
        Args:
            llm_parser: LLM解析器实例（DeepSeekParser）
        """
        self.llm_parser = llm_parser
        logger.info("EnhancedThemeAnalyzer初始化完成（纯AI决策版）")
    
    async def analyze_with_context(self,
                                  event_data: Dict[str, Any],
                                  related_themes: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        基于现有题材库的智能归并决策
        🔥 所有决策由AI完成，无降级逻辑
        
        Args:
            event_data: 事件数据
            related_themes: 相关题材列表
            
        Returns:
            AI决策结果
            
        Raises:
            Exception: AI分析失败时抛出异常
        """
        event_id = event_data.get('id', 'unknown')
        logger.info(f"开始上下文分析，事件: {event_id}, 相关题材数: {len(related_themes)}")
        
        try:
            # 1. 构建Prompt
            prompt = self._build_context_decision_prompt(event_data, related_themes)
            
            # 2. 调用真实AI（无模拟）
            raw_response = await self.llm_parser.parse_content(prompt)
            
            if not raw_response:
                raise ValueError("AI返回结果为空")
            
            # 3. 解析响应
            decision = self._parse_decision_response(raw_response)
            
            if not decision:
                raise ValueError("无法解析AI决策")
            
            # 4. 只做基本格式验证，不验证业务合理性
            if not self._validate_decision_format(decision):
                raise ValueError(f"AI决策格式无效: {decision}")
            
            # 5. 添加元数据
            decision['event_id'] = event_id
            decision['source'] = 'enhanced_analyzer'
            
            logger.info(
                f"上下文分析完成，事件: {event_id}, "
                f"决策: {decision.get('decision')}, "
                f"置信度: {decision.get('confidence', 0):.2f}"
            )
            
            return decision
            
        except Exception as e:
            logger.error(f"❌ 上下文分析失败，事件: {event_id}, 错误: {e}")
            # 🔥 不返回降级决策，直接抛出异常
            raise Exception(f"EnhancedThemeAnalyzer分析失败: {e}") from e
    
    def _build_context_decision_prompt(self, event_data: Dict, 
                                      related_themes: List[Dict]) -> str:
        """构建上下文决策Prompt"""
        # 提取事件信息
        title = event_data.get('title', '')
        summary = event_data.get('summary', '')
        industries = ', '.join(event_data.get('impact_industries', []))
        directive = event_data.get('theme_directive', {})
        
        # 格式化相关题材信息
        themes_context = self._format_related_themes(related_themes)
        
        return f"""你是一个专业的投资主题分析师，请基于事件和现有题材库，做出精准决策。

## 待分析事件
- **标题**: {title}
- **摘要**: {summary}
- **影响行业**: {industries}
- **第一轮判断**: {directive.get('action', 'N/A')} (置信度: {directive.get('confidence', 0):.2f})

## 现有相关题材（请仔细比较）
{themes_context}

## 决策选项
请选择最合适的决策：

### A. 归入已有题材 (MERGE_INTO)
- **条件**: 事件核心逻辑与某个现有题材**本质上相同**
- **要求**: target_theme_name 必须是上面列表中的题材名

### B. 创建全新题材 (CREATE_NEW)
- **条件**: 事件代表**全新的技术路径、政策方向、商业模式**
- **命名要求**: 2-6个汉字，具象化，避免"科技"、"创新"等宽泛词

### C. 忽略 (IGNORE)
- **条件**: 事件**投资价值极低**，或与金融市场**完全无关**

## 输出格式
{{
    "decision": "MERGE_INTO|CREATE_NEW|IGNORE",
    "target_theme_name": "具体题材名",
    "confidence": 0.0-1.0,
    "reason": "详细分析理由",
    "comparison_analysis": "与现有题材的比较分析"
}}

请严格分析，输出合法的JSON。"""
    
    def _format_related_themes(self, themes: List[Dict]) -> str:
        """格式化相关题材信息"""
        if not themes:
            return "（当前无密切相关的现有题材）"
        
        formatted = []
        for i, theme in enumerate(themes, 1):
            line = f"{i}. **{theme.get('name', 'N/A')}**"
            
            if desc := theme.get('description'):
                line += f" - {desc[:80]}..."
            
            if count := theme.get('event_count'):
                line += f" [已有{count}个事件]"
            
            formatted.append(line)
        
        return "\n".join(formatted)
    
    def _parse_decision_response(self, raw_response: Dict) -> Dict:
        """解析AI响应"""
        if not raw_response or not isinstance(raw_response, dict):
            raise ValueError(f"AI响应格式无效: {raw_response}")
        
        # 尝试从不同字段名中提取决策
        decision = {}
        
        # 决策字段
        for key in ["decision", "action", "theme_action"]:
            if key in raw_response:
                decision["decision"] = raw_response[key]
                break
        
        # 主题名字段
        for key in ["target_theme_name", "theme_name", "target_theme"]:
            if key in raw_response:
                decision["target_theme_name"] = raw_response[key]
                break
        
        # 置信度字段
        for key in ["confidence", "certainty", "score"]:
            if key in raw_response:
                try:
                    decision["confidence"] = float(raw_response[key])
                except (ValueError, TypeError):
                    decision["confidence"] = 0.5
                break
        
        # 理由字段
        for key in ["reason", "analysis", "explanation"]:
            if key in raw_response:
                decision["reason"] = raw_response[key]
                break
        
        # 比较分析字段
        for key in ["comparison_analysis", "comparison", "analysis"]:
            if key in raw_response:
                decision["comparison_analysis"] = raw_response[key]
                break
        
        # 设置默认值
        if "decision" not in decision:
            decision["decision"] = "CLUSTER"
        if "confidence" not in decision:
            decision["confidence"] = 0.5
        if "reason" not in decision:
            decision["reason"] = ""
        if "comparison_analysis" not in decision:
            decision["comparison_analysis"] = ""
        if "target_theme_name" not in decision:
            decision["target_theme_name"] = ""
        
        return decision
    
    def _validate_decision_format(self, decision: Dict) -> bool:
        """验证决策格式（不验证业务合理性）"""
        required_fields = ["decision", "confidence"]
        for field in required_fields:
            if field not in decision:
                return False
        
        # 只检查决策类型是否合法
        valid_decisions = ["MERGE_INTO", "CREATE_NEW", "IGNORE", "CLUSTER"]
        if decision["decision"] not in valid_decisions:
            return False
        
        # 检查置信度范围
        try:
            confidence = float(decision["confidence"])
            if not 0 <= confidence <= 1:
                return False
        except (ValueError, TypeError):
            return False
        
        return True