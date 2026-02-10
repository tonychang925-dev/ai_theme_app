# news_crawler_service/services/enhanced_news_generator.py
"""
新闻收集服务 - 封装新闻抓取和收集逻辑
"""
import asyncio
import logging
import hashlib
import random
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import json

logger = logging.getLogger(__name__)


class EnhancedNewsGenerator:
    """增强新闻生成器 - 提供模拟新闻数据生成功能"""
    
    def __init__(self, prefix: str = "collector_news"):
        self.prefix = prefix
        
        # 丰富的数据池
        self.stocks = [
            "贵州茅台", "宁德时代", "招商银行", "中国平安", "比亚迪",
            "五粮液", "中国中免", "隆基绿能", "东方财富", "中信证券",
            "药明康德", "迈瑞医疗", "海康威视", "立讯精密", "京东方A",
            "美的集团", "格力电器", "海尔智家", "腾讯控股", "阿里巴巴"
        ]
        
        self.actions = ["大涨", "大跌", "创新高", "突破", "回调", "震荡", "企稳"]
        self.sources = ["新浪财经", "东方财富", "证券时报", "中国证券报", "华尔街见闻"]
        self.keywords_pool = ["AI", "人工智能", "新能源", "芯片", "医药", "消费", "金融"]
        self.markets = ["A股", "港股", "美股", "科创板", "创业板"]
        self.sentiments = ["利好", "利空", "中性", "积极", "谨慎"]
        
        logger.info("📡 增强新闻生成器初始化完成")
    
    async def generate_mock_news(self, count: int = 3, news_type: str = "stock") -> List[Dict[str, Any]]:
        """生成模拟新闻"""
        news_list = []
        
        for i in range(count):
            if news_type == "stock":
                news_data = await self._generate_stock_news(i)
            elif news_type == "market":
                news_data = await self._generate_market_news(i)
            elif news_type == "policy":
                news_data = await self._generate_policy_news(i)
            else:
                news_data = await self._generate_general_news(i)
            
            news_list.append(news_data)
        
        logger.info(f"📝 生成 {len(news_list)} 条{news_type}类模拟新闻")
        return news_list
    
    async def _generate_stock_news(self, sequence: int) -> Dict[str, Any]:
        """生成股票新闻"""
        stock = random.choice(self.stocks)
        action = random.choice(self.actions)
        percent = random.uniform(1, 10)
        
        title = f"{stock}{action}{percent:.1f}%，机构称后市可期"
        
        content = f"今日{stock}股价{action}，收盘{percent:.1f}%。市场分析认为这与{random.choice(['政策面变化', '资金流向', '市场预期调整'])}有关。"
        
        news_id = self._generate_news_id(title, sequence)
        
        news_data = {
            "news_id": news_id,
            "title": title,
            "content": content,
            "source": random.choice(self.sources),
            "publish_date": datetime.now().date().isoformat(),
            "publish_time": (datetime.now() - timedelta(minutes=random.randint(0, 120))).time().isoformat(),
            "market": random.choice(self.markets),
            "keywords": random.sample(self.keywords_pool, random.randint(2, 4)),
            "metadata": {
                "simulation": True,
                "news_type": "stock",
                "sequence": sequence + 1,
                "generator": "EnhancedNewsGenerator",
                "version": "2.0",
                "stocks": [stock],
                "sentiment": random.choice(self.sentiments)
            }
        }
        
        return news_data
    
    async def _generate_market_news(self, sequence: int) -> Dict[str, Any]:
        """生成市场新闻"""
        index = random.choice(["上证指数", "深证成指", "创业板指"])
        action = random.choice(["上涨", "下跌", "震荡"])
        percent = random.uniform(0.5, 3.5)
        
        title = f"{index}{action}{percent:.1f}%，市场交投活跃"
        
        content = f"今日{index}表现{action}，收盘{percent:.1f}%。市场分析认为，{random.choice(['政策预期改善', '资金面相对宽松'])}是主要原因。"
        
        news_id = self._generate_news_id(title, sequence)
        
        news_data = {
            "news_id": news_id,
            "title": title,
            "content": content,
            "source": random.choice(self.sources),
            "publish_date": datetime.now().date().isoformat(),
            "publish_time": (datetime.now() - timedelta(minutes=random.randint(0, 120))).time().isoformat(),
            "market": "A股",
            "keywords": ["市场", index, action, "指数"],
            "metadata": {
                "simulation": True,
                "news_type": "market",
                "sequence": sequence + 1
            }
        }
        
        return news_data
    
    async def _generate_policy_news(self, sequence: int) -> Dict[str, Any]:
        """生成政策新闻"""
        area = random.choice(["货币政策", "财政政策", "产业政策"])
        action = random.choice(["出台", "调整", "优化"])
        
        title = f"{area}{action}，助力经济发展"
        
        content = f"近日，有关部门{action}{area}。该政策将{random.choice(['有利于市场长期健康发展', '提升市场信心'])}。专家表示，政策效果有待观察。"
        
        news_id = self._generate_news_id(title, sequence)
        
        news_data = {
            "news_id": news_id,
            "title": title,
            "content": content,
            "source": "政策研究室",
            "publish_date": datetime.now().date().isoformat(),
            "publish_time": (datetime.now() - timedelta(minutes=random.randint(0, 120))).time().isoformat(),
            "market": "政策",
            "keywords": [area, "政策", action, "经济"],
            "metadata": {
                "simulation": True,
                "news_type": "policy",
                "sequence": sequence + 1,
                "policy_area": area
            }
        }
        
        return news_data
    
    async def _generate_general_news(self, sequence: int) -> Dict[str, Any]:
        """生成一般新闻"""
        topic = random.choice(["经济数据", "公司公告", "行业动态"])
        
        title = f"{topic}最新进展"
        
        content = f"关于{topic}的最新信息显示，市场关注度持续提升。相关专家进行解读分析。"
        
        news_id = self._generate_news_id(title, sequence)
        
        news_data = {
            "news_id": news_id,
            "title": title,
            "content": content,
            "source": random.choice(self.sources),
            "publish_date": datetime.now().date().isoformat(),
            "publish_time": (datetime.now() - timedelta(minutes=random.randint(0, 120))).time().isoformat(),
            "market": random.choice(self.markets),
            "keywords": [topic, "新闻", "分析"],
            "metadata": {
                "simulation": True,
                "news_type": "general",
                "sequence": sequence + 1,
                "topic": topic
            }
        }
        
        return news_data
    
    def _generate_news_id(self, title: str, sequence: int) -> str:
        """生成news_id"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        text = f"{title}_{timestamp}_{sequence}_{random.randint(1000, 9999)}"
        md5_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        return f"{self.prefix}_{md5_hash[:16]}"
    
    async def generate_news_batch(self, batch_size: int = 5, batch_id: Optional[str] = None,
                                 mixed_types: bool = True) -> Dict[str, Any]:
        """生成新闻批次"""
        if batch_id is None:
            batch_id = f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        if mixed_types:
            # 混合类型新闻
            news_list = []
            types = ["stock", "market", "policy", "general"]
            for i in range(batch_size):
                news_type = random.choice(types)
                if news_type == "stock":
                    news_list.append(await self._generate_stock_news(i))
                elif news_type == "market":
                    news_list.append(await self._generate_market_news(i))
                elif news_type == "policy":
                    news_list.append(await self._generate_policy_news(i))
                else:
                    news_list.append(await self._generate_general_news(i))
        else:
            # 单一类型新闻
            news_list = await self.generate_mock_news(batch_size, "stock")
        
        return {
            "batch_id": batch_id,
            "batch_size": len(news_list),
            "generated_at": datetime.now().isoformat(),
            "news_list": news_list,
            "generator": self.__class__.__name__,
            "mixed_types": mixed_types
        }
