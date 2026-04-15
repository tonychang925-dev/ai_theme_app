"""
测试数据夹具
提供测试用的模拟数据
"""

import json
from datetime import datetime, timedelta
from typing import Dict, List, Any
import random

# 测试新闻数据
TEST_NEWS_DATA = [
    {
        "id": f"test_news_{i:03d}",
        "title": f"测试新闻标题 {i} - AI技术突破",
        "content": f"测试新闻内容 {i}。人工智能技术取得重大突破，相关股票可能受益。",
        "source": random.choice(["新浪财经", "腾讯新闻", "网易新闻", "东方财富"]),
        "published_at": (datetime.now() - timedelta(hours=random.randint(0, 24))).isoformat(),
        "url": f"https://example.com/news/{i}",
        "keywords": ["AI", "技术", "突破", "股票"],
        "sentiment": random.uniform(-1.0, 1.0)
    }
    for i in range(1, 21)
]

# 测试Stream消息
TEST_STREAM_MESSAGES = [
    {
        "id": f"test_message_{i:03d}",
        "data": {
            "news_id": f"test_news_{i:03d}",
            "action": "process",
            "timestamp": datetime.now().isoformat()
        }
    }
    for i in range(1, 11)
]

# 测试主题数据
TEST_THEME_DATA = [
    {
        "id": f"test_theme_{i:02d}",
        "name": f"测试主题 {i}",
        "description": f"测试主题描述 {i}",
        "keywords": [f"关键词{i}{j}" for j in range(1, 4)],
        "stocks": [f"stock_{j:04d}" for j in range(1, 6)],
        "strength": random.uniform(0.5, 1.0),
        "trend": random.choice(["rising", "falling", "stable"])
    }
    for i in range(1, 11)
]

# 测试股票数据
TEST_STOCK_DATA = [
    {
        "id": f"stock_{i:04d}",
        "name": f"测试股票 {i}",
        "code": f"{i:06d}",
        "industry": random.choice(["科技", "金融", "医疗", "消费", "能源"]),
        "market_cap": random.randint(1000000000, 100000000000),
        "price": random.uniform(10.0, 100.0),
        "change": random.uniform(-5.0, 5.0),
        "volume": random.randint(1000000, 10000000)
    }
    for i in range(1, 51)
]

# 测试错误数据
TEST_ERROR_DATA = {
    "redis_errors": [
        {
            "code": "REDIS-ERROR-001",
            "message": "Redis连接失败",
            "details": {"host": "localhost", "port": 6379},
            "severity": "ERROR"
        },
        {
            "code": "REDIS-WARNING-002", 
            "message": "Redis内存使用过高",
            "details": {"usage": "85%", "limit": "1GB"},
            "severity": "WARNING"
        }
    ],
    "database_errors": [
        {
            "code": "DATABASE-ERROR-003",
            "message": "数据库查询失败",
            "details": {"query": "SELECT * FROM news", "error": "timeout"},
            "severity": "ERROR"
        }
    ],
    "stream_errors": [
        {
            "code": "STREAM-ERROR-004",
            "message": "Stream消息处理失败",
            "details": {"stream": "news_stream", "message_id": "12345"},
            "severity": "ERROR"
        }
    ]
}

# 测试性能数据
TEST_PERFORMANCE_DATA = {
    "single_processing": {
        "count": 5,
        "total_time": 53.61,
        "avg_time": 10.72,
        "throughput": 0.093
    },
    "batch_processing": [
        {
            "batch_size": 2,
            "count": 20,
            "total_time": 58.85,
            "avg_time": 2.94,
            "throughput": 0.340
        },
        {
            "batch_size": 3,
            "count": 20,
            "total_time": 52.08,
            "avg_time": 2.60,
            "throughput": 0.384
        },
        {
            "batch_size": 5,
            "count": 20,
            "total_time": 45.88,
            "avg_time": 2.29,
            "throughput": 0.436
        },
        {
            "batch_size": 10,
            "count": 20,
            "total_time": 38.08,
            "avg_time": 1.90,
            "throughput": 0.525
        }
    ]
}

# 测试消费者组数据
TEST_CONSUMER_GROUP_DATA = [
    {
        "stream": "stream:test_news",
        "group": "test_consumer_group",
        "consumers": random.randint(0, 3),
        "pending": random.randint(0, 100),
        "last_delivered": f"{random.randint(1000, 2000)}-0",
        "is_protected": False
    },
    {
        "stream": "stream:business_news",
        "group": "news_storage_handlers",
        "consumers": random.randint(1, 5),
        "pending": random.randint(10, 50),
        "last_delivered": f"{random.randint(5000, 10000)}-0",
        "is_protected": True
    },
    {
        "stream": "stream:test_themes",
        "group": "temp_theme_processor",
        "consumers": 0,
        "pending": 0,
        "last_delivered": "0-0",
        "is_protected": False
    }
]

# 工具函数
def create_test_news(count: int = 5) -> List[Dict[str, Any]]:
    """创建测试新闻数据"""
    return [
        {
            "id": f"dynamic_news_{i}",
            "title": f"动态测试新闻 {i}",
            "content": f"这是第 {i} 条动态测试新闻内容。",
            "source": "测试源",
            "published_at": datetime.now().isoformat(),
            "url": f"https://test.com/news/{i}",
            "keywords": ["测试", "动态"],
            "sentiment": 0.0
        }
        for i in range(count)
    ]

def create_test_error(domain: str, severity: str, code: int) -> Dict[str, Any]:
    """创建测试错误数据"""
    return {
        "code": f"{domain}-{severity}-{code:03d}",
        "message": f"{domain} {severity} 测试错误",
        "details": {"test": True, "domain": domain, "severity": severity},
        "severity": severity
    }

def create_performance_metrics(
    operation: str,
    count: int,
    total_time: float
) -> Dict[str, Any]:
    """创建性能指标数据"""
    return {
        "operation": operation,
        "count": count,
        "total_time": total_time,
        "avg_time": total_time / count if count > 0 else 0,
        "throughput": count / total_time if total_time > 0 else 0,
        "timestamp": datetime.now().isoformat()
    }

def get_random_news() -> Dict[str, Any]:
    """获取随机新闻数据"""
    return random.choice(TEST_NEWS_DATA)

def get_random_stock() -> Dict[str, Any]:
    """获取随机股票数据"""
    return random.choice(TEST_STOCK_DATA)

def get_random_theme() -> Dict[str, Any]:
    """获取随机主题数据"""
    return random.choice(TEST_THEME_DATA)

# 数据验证函数
def validate_news_data(news: Dict[str, Any]) -> bool:
    """验证新闻数据格式"""
    required_fields = ["id", "title", "content", "source", "published_at"]
    return all(field in news for field in required_fields)

def validate_error_data(error: Dict[str, Any]) -> bool:
    """验证错误数据格式"""
    required_fields = ["code", "message", "severity"]
    if not all(field in error for field in required_fields):
        return False
    
    # 验证错误编码格式
    parts = error["code"].split("-")
    return len(parts) == 3 and parts[2].isdigit()

# 数据导出函数
def export_test_data(filename: str = "test_data.json"):
    """导出测试数据到JSON文件"""
    data = {
        "news": TEST_NEWS_DATA,
        "stream_messages": TEST_STREAM_MESSAGES,
        "themes": TEST_THEME_DATA,
        "stocks": TEST_STOCK_DATA,
        "errors": TEST_ERROR_DATA,
        "performance": TEST_PERFORMANCE_DATA,
        "consumer_groups": TEST_CONSUMER_GROUP_DATA,
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "counts": {
                "news": len(TEST_NEWS_DATA),
                "themes": len(TEST_THEME_DATA),
                "stocks": len(TEST_STOCK_DATA),
                "errors": sum(len(v) for v in TEST_ERROR_DATA.values())
            }
        }
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return filename

if __name__ == "__main__":
    # 导出测试数据
    export_test_data()
    print("✅ 测试数据已生成")
