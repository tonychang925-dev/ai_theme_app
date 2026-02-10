from typing import List, Optional, Dict, Any
import asyncio
import json
import random
from datetime import datetime

from ..models.news_event import NewsEvent
from ..database import DatabaseManager

class AIExtractor:
    """AI事件抽取器 - 改进版"""
    
    # 事件类型映射
    EVENT_TYPES = {
        "policy": "政策发布",
        "financial": "财报公告", 
        "merger": "并购重组",
        "tech": "技术创新",
        "market": "市场动态",
        "cooperation": "战略合作",
        "investment": "重大投资",
        "regulation": "监管变化"
    }
    
    # 行业映射
    INDUSTRIES = {
        "科技": ["人工智能", "芯片", "半导体", "云计算", "大数据", "算法", "5G"],
        "新能源": ["新能源", "光伏", "电池", "电动车", "储能", "太阳能", "风电"],
        "金融": ["银行", "证券", "保险", "金融科技", "支付", "信贷"],
        "医疗": ["医疗", "医药", "生物技术", "医疗器械", "医院", "疫苗"],
        "消费": ["零售", "电商", "食品饮料", "家电", "旅游"],
        "制造": ["制造", "工业", "机器人", "自动化", "供应链"]
    }
    
    # 关键词到事件类型的映射
    KEYWORD_TO_EVENT = {
        "政策": "policy",
        "规划": "policy", 
        "支持": "policy",
        "鼓励": "policy",
        "财报": "financial",
        "业绩": "financial",
        "盈利": "financial",
        "收入": "financial",
        "并购": "merger",
        "收购": "merger",
        "重组": "merger",
        "合并": "merger",
        "合作": "cooperation",
        "投资": "investment",
        "融资": "investment",
        "创新": "tech",
        "技术": "tech",
        "突破": "tech"
    }
    
    async def extract_events_from_news(self, news_items: List[Dict]) -> List[NewsEvent]:
        """从新闻列表中提取事件"""
        if not news_items:
            return []
        
        print(f"🔍 开始AI分析: {len(news_items)} 条新闻")
        
        events = []
        
        for i, news in enumerate(news_items):
            try:
                print(f"   📰 [{i+1}/{len(news_items)}] 分析: {news.get('title', '')[:50]}...")
                
                event = await self._analyze_single_news(news)
                if event:
                    events.append(event)
                    print(f"   ✅ 分析完成: {event.event_type}")
                else:
                    print(f"   ⚠️  未提取到有效事件")
                    
            except Exception as e:
                print(f"   ❌ 分析失败: {e}")
        
        print(f"🎯 AI分析完成: {len(events)} 个事件提取成功")
        return events
    
    async def _analyze_single_news(self, news: Dict) -> Optional[NewsEvent]:
        """分析单条新闻"""
        news_hash_id = news.get('news_id', '')
        if not news_hash_id:
            return None
        
        # 获取news_raw.id
        news_db_id = await DatabaseManager.get_news_raw_id(news_hash_id)
        if not news_db_id:
            print(f"   ⚠️  未找到news_raw记录: {news_hash_id[:10]}...")
            return None
        
        # AI分析生成事件数据
        event_data = await self._ai_analysis(news)
        
        # 创建事件对象
        try:
            event = NewsEvent.from_ai_response(
                news_db_id=news_db_id,
                news_hash_id=news_hash_id,
                ai_data=event_data,
                raw_news=news
            )
            return event
        except Exception as e:
            print(f"   ❌ 创建事件失败: {e}")
            return None
    
    async def _ai_analysis(self, news: Dict) -> Dict:
        """AI分析核心逻辑"""
        title = news.get('title', '').lower()
        content = news.get('content', '').lower()
        
        # 1. 确定事件类型
        event_type_key = self._detect_event_type(title, content)
        event_type = self.EVENT_TYPES.get(event_type_key, "行业动态")
        
        # 2. 确定行业
        industry = self._detect_industry(title, content)
        
        # 3. 分析情感和置信度
        sentiment = self._analyze_sentiment(title)
        confidence = self._calculate_confidence(title, content)
        
        # 4. 生成摘要
        summary = self._generate_summary(title, event_type, industry, sentiment)
        
        return {
            "event_type": event_type,
            "industry": industry,
            "summary": summary,
            "sentiment": sentiment,
            "confidence": confidence
        }
    
    def _detect_event_type(self, title: str, content: str) -> str:
        """检测事件类型"""
        combined = f"{title} {content}"
        
        for keyword, event_key in self.KEYWORD_TO_EVENT.items():
            if keyword in combined:
                return event_key
        
        # 默认类型
        default_types = ["policy", "market", "tech", "financial"]
        return random.choice(default_types)
    
    def _detect_industry(self, title: str, content: str) -> str:
        """检测行业"""
        combined = f"{title} {content}"
        
        for industry, keywords in self.INDUSTRIES.items():
            for keyword in keywords:
                if keyword in combined:
                    return industry
        
        return "通用"
    
    def _analyze_sentiment(self, title: str) -> float:
        """分析情感"""
        positive_words = ['增长', '提升', '利好', '上涨', '突破', '成功', '创新', '发展', '支持', '鼓励']
        negative_words = ['下降', '下滑', '风险', '警告', '下跌', '亏损', '危机', '问题', '调查', '处罚']
        
        title_lower = title.lower()
        
        positive_count = sum(1 for word in positive_words if word in title_lower)
        negative_count = sum(1 for word in negative_words if word in title_lower)
        
        if positive_count > negative_count:
            return 0.6 + (positive_count * 0.1)
        elif negative_count > positive_count:
            return -0.4 - (negative_count * 0.1)
        else:
            return 0.0
    
    def _calculate_confidence(self, title: str, content: str) -> float:
        """计算置信度"""
        confidence = 0.7  # 基础置信度
        
        # 标题长度影响
        if len(title) > 20:
            confidence += 0.1
        
        # 内容长度影响
        if len(content) > 100:
            confidence += 0.1
            
        # 包含具体数字
        import re
        if re.search(r'\d+', title):
            confidence += 0.05
            
        return min(confidence, 0.95)  # 最大0.95
    
    def _generate_summary(self, title: str, event_type: str, industry: str, sentiment: float) -> str:
        """生成摘要"""
        sentiment_text = "利好" if sentiment > 0.3 else "利空" if sentiment < -0.3 else "中性"
        
        if industry != "通用":
            return f"{industry}行业{event_type}{sentiment_text}事件：{title[:40]}"
        else:
            return f"{event_type}{sentiment_text}事件：{title[:40]}"

# 单例实例
ai_extractor = AIExtractor()
