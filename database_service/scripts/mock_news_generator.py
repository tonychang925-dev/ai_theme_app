# scripts/mock_news_generator.py
"""
模拟新闻生成器 - 用于集成测试
"""
import asyncio
import hashlib
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any

class MockNewsGenerator:
    """模拟新闻生成器"""
    
    def __init__(self, prefix: str = "mock"):
        self.prefix = prefix
        
        # 数据池
        self.stocks = ["贵州茅台", "宁德时代", "招商银行", "中国平安", "比亚迪"]
        self.actions = ["大涨", "大跌", "创新高", "突破", "回调"]
        self.sources = ["新浪财经", "东方财富", "证券时报"]
        self.keywords_pool = ["AI", "人工智能", "大数据", "云计算", "区块链"]
    
    async def generate_mock_news(self, count: int = 3) -> List[Dict[str, Any]]:
        """生成模拟新闻"""
        news_list = []
        
        for i in range(count):
            # 生成基本数据
            stock = random.choice(self.stocks)
            action = random.choice(self.actions)
            title = f"【{self.prefix}】{stock}{action}{random.randint(1, 10)}%"
            
            # 生成news_id
            news_id = self._generate_news_id(title)
            
            # 构建新闻数据
            news_data = {
                "news_id": news_id,
                "title": title,
                "content": f"这是第{i+1}条模拟新闻内容。生成时间: {datetime.now().isoformat()}",
                "source": random.choice(self.sources),
                "publish_date": datetime.now().date().isoformat(),
                "publish_time": datetime.now().time().isoformat(),
                "market": "A股",
                "keywords": random.sample(self.keywords_pool, 2),
                "metadata": {
                    "simulation": True,
                    "batch": f"batch_{int(datetime.now().timestamp())}",
                    "sequence": i + 1
                }
            }
            
            news_list.append(news_data)
        
        print(f"📝 生成 {len(news_list)} 条模拟新闻")
        return news_list
    
    def _generate_news_id(self, title: str) -> str:
        """生成news_id"""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        text = f"{title}_{timestamp}_{random.randint(1000, 9999)}"
        md5_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        return f"{self.prefix}_news_{md5_hash[:12]}"