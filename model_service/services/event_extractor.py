# model_service/service/event_extractor.py
"""
事件提取器 - 精简版，移除所有冗余数据
🔥 仅保存核心业务数据：事件信息、主题决策、原始内容
"""
import logging
from typing import Dict, Optional
import json
from datetime import datetime

from model_service.llm_parser.factory import LLMParserFactory
from model_service.llm_parser.base import LLMParser

logger = logging.getLogger(__name__)

class AIEventExtractor:
    """基于LLMParser的事件提取器 - 精简数据结构"""
    
    def __init__(self, llm_parser: Optional[LLMParser] = None):
        """
        初始化事件提取器
        """
        self.llm_parser = llm_parser or LLMParserFactory.create_parser_from_env()
        logger.info(f"AI事件提取器已初始化，使用 {getattr(self.llm_parser, 'provider', getattr(self.llm_parser, 'model_name', type(self.llm_parser).__name__))} 提供商")
    
    async def extract_event(self, news_data: Dict) -> Optional[Dict]:
        """
        从新闻数据中提取结构化事件。
        🔥 精简数据结构：仅保留核心业务字段，移除所有冗余
        """
        title = news_data.get('title', '')
        content = news_data.get('content', '')
        news_id = news_data.get('news_id')
        
        if not title or not content:
            logger.warning(f"新闻数据不完整，跳过处理。news_id: {news_id}")
            return None
        
        start_time = datetime.now()
        
        # 调用LLM解析器
        parsed_result = await self.llm_parser.parse_news(title, content)
        
        if not parsed_result:
            logger.warning(f"LLM解析失败，未提取到事件。news_id: {news_id}")
            return None
        
        # 从AI响应中提取信息
        event_info = parsed_result.get("event_info", {})
        theme_directive = parsed_result.get("theme_discovery_directive", {
            "action": "CLUSTER",
            "decision_confidence": 0.5,
            "reason": ""
        })
        
        # 处理行业字段：确保是列表
        impact_industries = event_info.get("impact_industries", [])
        if isinstance(impact_industries, str):
            try:
                impact_industries = json.loads(impact_industries)
            except (json.JSONDecodeError, TypeError):
                if ',' in impact_industries:
                    impact_industries = [item.strip() for item in impact_industries.split(',') if item.strip()]
                else:
                    impact_industries = [impact_industries] if impact_industries else []
        
        # 处理事件置信度
        event_confidence = event_info.get('event_confidence', event_info.get('confidence', 0.5))
        if isinstance(event_confidence, (int, float)):
            if event_confidence > 1 and event_confidence <= 100:
                event_confidence = event_confidence / 100.0
            event_confidence = float(event_confidence)
        else:
            event_confidence = 0.5
        event_confidence = max(0.0, min(1.0, event_confidence))
        
        # 处理方向
        direction = event_info.get('direction', 'neutral')
        direction_map = {
            'positive': '利好',
            'negative': '利空', 
            'neutral': '中性',
            '利好': '利好',
            '利空': '利空',
            '中性': '中性'
        }
        direction = direction_map.get(direction.lower() if isinstance(direction, str) else direction, '中性')
        
        # 主题决策置信度
        decision_confidence = theme_directive.get('decision_confidence', theme_directive.get('confidence', 0.5))
        if isinstance(decision_confidence, (int, float)):
            decision_confidence = float(decision_confidence)
        else:
            decision_confidence = 0.5
        decision_confidence = max(0.0, min(1.0, decision_confidence))
        
        # 🔥 构建精简的事件数据结构
        event_result = {
            'news_id': news_id,
            
            # 第一阶段：事件基础信息
            'event_info': {
                'event_type': event_info.get('event_type', 'unknown'),
                'impact_industries': impact_industries,
                'direction': direction,
                'event_confidence': event_confidence
            },
            
            # 第二阶段：主题发现决策
            'theme_discovery_directive': {
                'action': theme_directive.get('action', 'CLUSTER'),
                'decision_confidence': decision_confidence,
                'reason': theme_directive.get('reason', '')
            },
            
            # 🔥 完整原始数据（供后续AI分析使用）
            'original_news': {
                'title': title,
                'content': content,  # 完整原始内容
                'content_length': len(content) if content else 0,
                'date': news_data.get('date')  # 只保留真正有用的原始信息
            }
            
            # ❌ 已移除：summary、raw_ai_response、ai_response、data_integrity、extraction_metadata
        }
        
        processing_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"✅ 事件提取完成: news_id={news_id}, "
                    f"原始内容长度={len(content)}, "
                    f"事件置信度={event_confidence:.2f}, "
                    f"决策={theme_directive.get('action')}({decision_confidence:.2f}), "
                    f"耗时={processing_time:.2f}s")
        
        return event_result
    
    async def health_check(self) -> bool:
        """检查提取器健康状态"""
        if not self.llm_parser:
            return False
        return await self.llm_parser.health_check()
    
    async def close(self):
        """清理资源"""
        if self.llm_parser:
            await self.llm_parser.close()
            logger.info("AI事件提取器资源已释放")


# 保持向后兼容的Mock提取器（供测试使用）
class MockEventExtractor:
    """模拟事件提取器，用于测试"""
    
    async def extract_event(self, news_data: Dict) -> Optional[Dict]:
        import random
        from datetime import datetime
        
        event_types = ["政策发布", "技术突破", "产品发布", "业绩预告", "战略合作"]
        industries = ["人工智能", "新能源汽车", "芯片半导体", "医药生物", "金融服务"]
        directions = ["利好", "利空", "中性"]
        
        # 🔥 模拟重大事件判断
        is_major = random.random() > 0.7  # 30%的概率是重大事件
        
        return {
            'news_id': news_data.get('news_id', 'mock_001'),
            'event_info': {
                'event_type': random.choice(event_types),
                'impact_industries': random.sample(industries, k=random.randint(1, 3)),
                'direction': random.choice(directions),
                'event_confidence': round(random.uniform(0.7, 0.95), 2)
            },
            'theme_discovery_directive': {
                'action': "CREATE_NEW" if is_major else "CLUSTER",
                'decision_confidence': round(random.uniform(0.8, 0.95), 2) if is_major else round(random.uniform(0.3, 0.6), 2),
                'reason': "模拟重大事件理由" if is_major else "模拟常规事件理由"
            },
            'original_news': {
                'title': news_data.get('title', '模拟新闻标题'),
                'content': news_data.get('content', '模拟新闻内容'),
                'content_length': len(news_data.get('content', '')),
                'date': news_data.get('date', datetime.now().strftime('%Y-%m-%d'))
            }
        }
    
    async def health_check(self) -> bool:
        return True
    
    async def close(self):
        pass