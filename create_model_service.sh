#!/bin/bash
# 创建model_service完整项目的脚本

echo "🚀 开始创建model_service项目结构..."

# 创建目录
mkdir -p model_service/{models,services,api}

# 1. 创建 __init__.py
cat > model_service/__init__.py << 'EOF'
"""
AI事件抽取服务模块
"""
__version__ = "1.0.0"
EOF

# 2. 创建 config.py
cat > model_service/config.py << 'EOF'
import os
from typing import Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from functools import lru_cache

class ModelServiceSettings(BaseSettings):
    """模型服务配置"""
    
    # 数据库配置
    DATABASE_URL: str = Field(
        default="postgresql://postgres:zxbzj~925@localhost/stock_data",
        description="PostgreSQL数据库连接URL"
    )
    
    # AI服务配置
    OPENAI_API_KEY: Optional[str] = Field(default=None, description="OpenAI API密钥")
    DEEPSEEK_API_KEY: Optional[str] = Field(default=None, description="DeepSeek API密钥")
    AI_MODEL: str = Field(default="gpt-3.5-turbo", description="使用的AI模型")
    
    # 处理配置
    BATCH_SIZE: int = Field(default=5, description="批量处理大小")
    MAX_RETRIES: int = Field(default=3, description="最大重试次数")
    REQUEST_TIMEOUT: int = Field(default=30, description="API请求超时时间")
    
    # 服务配置
    HOST: str = Field(default="0.0.0.0", description="服务监听地址")
    PORT: int = Field(default=8001, description="服务监听端口")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

@lru_cache()
def get_settings() -> ModelServiceSettings:
    return ModelServiceSettings()

settings = get_settings()
EOF

# 3. 创建 models/news_event.py
cat > model_service/models/news_event.py << 'EOF'
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import hashlib

class NewsEvent(BaseModel):
    """结构化事件模型"""
    news_id: str = Field(..., description="关联的新闻ID")
    event_type: str = Field(..., description="事件类型")
    industry: str = Field(..., description="所属行业")
    summary: str = Field(..., description="事件摘要")
    sentiment: float = Field(..., ge=-1.0, le=1.0, description="情感分数")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    raw_news_title: str = Field(..., description="原始新闻标题")
    raw_news_content: str = Field(..., description="原始新闻内容")
    source: str = Field(..., description="数据源")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    
    # 自动生成事件ID
    event_id: Optional[str] = None
    
    def __init__(self, **data):
        super().__init__(**data)
        if not self.event_id:
            self.event_id = self._generate_event_id()
    
    def _generate_event_id(self):
        """生成事件唯一ID"""
        unique_str = f"{self.news_id}{self.event_type}{self.summary[:50]}"
        return hashlib.md5(unique_str.encode()).hexdigest()
    
    class Config:
        from_attributes = True
EOF

# 4. 创建 database.py
cat > model_service/database.py << 'EOF'
import asyncpg
from typing import List, Optional
import logging
from contextlib import asynccontextmanager

from .models.news_event import NewsEvent
from .config import settings

logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库管理器"""
    
    _pool: Optional[asyncpg.Pool] = None
    
    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        if cls._pool is None:
            await cls.initialize()
        return cls._pool
    
    @classmethod
    async def initialize(cls):
        """初始化数据库连接和表"""
        try:
            cls._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=1,
                max_size=5,
            )
            logger.info("model_service 数据库连接池初始化成功")
            
            await cls._ensure_tables()
            
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise
    
    @classmethod
    async def _ensure_tables(cls):
        """确保news_event表存在"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS news_event (
            id SERIAL PRIMARY KEY,
            event_id VARCHAR(64) UNIQUE NOT NULL,
            news_id VARCHAR(64) NOT NULL,
            event_type VARCHAR(50) NOT NULL,
            industry VARCHAR(50) NOT NULL,
            summary TEXT NOT NULL,
            sentiment DECIMAL(3,2) NOT NULL,
            confidence DECIMAL(3,2) NOT NULL,
            raw_news_title TEXT NOT NULL,
            raw_news_content TEXT,
            source VARCHAR(50) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            
            -- 索引
            INDEX idx_event_id (event_id),
            INDEX idx_news_id (news_id),
            INDEX idx_event_type (event_type),
            INDEX idx_industry (industry),
            INDEX idx_created_at (created_at)
        );
        """
        
        async with cls._pool.acquire() as conn:
            await conn.execute(create_table_sql)
            logger.info("news_event表验证/创建完成")
    
    @classmethod
    async def save_events(cls, events: List[NewsEvent]) -> int:
        """保存事件列表到数据库"""
        if not events:
            return 0
        
        saved_count = 0
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            async with conn.transaction():
                for event in events:
                    try:
                        await conn.execute("""
                            INSERT INTO news_event 
                            (event_id, news_id, event_type, industry, summary, 
                             sentiment, confidence, raw_news_title, raw_news_content, source)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                            ON CONFLICT (event_id) DO NOTHING
                        """,
                            event.event_id, event.news_id, event.event_type,
                            event.industry, event.summary, event.sentiment,
                            event.confidence, event.raw_news_title,
                            event.raw_news_content, event.source
                        )
                        saved_count += 1
                        
                    except Exception as e:
                        print(f"保存事件失败 {event.event_id}: {e}")
        
        print(f"保存事件: 总计{len(events)}条, 成功{saved_count}条")
        return saved_count
    
    @classmethod
    async def close(cls):
        if cls._pool:
            await cls._pool.close()
            cls._pool = None

@asynccontextmanager
async def get_db_connection():
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        yield conn

async def init_database():
    await DatabaseManager.initialize()

async def close_database():
    await DatabaseManager.close()
EOF

# 5. 创建 services/ai_extractor.py
cat > model_service/services/ai_extractor.py << 'EOF'
from typing import List, Optional, Dict, Any
import asyncio
import json
from datetime import datetime

from ..models.news_event import NewsEvent
from ..config import settings

class AIExtractor:
    """AI事件抽取器"""
    
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY or settings.OPENAI_API_KEY
        self.model = settings.AI_MODEL
        self.timeout = settings.REQUEST_TIMEOUT
        self.max_retries = settings.MAX_RETRIES
    
    async def extract_events_from_news(self, news_items: List[Dict]) -> List[NewsEvent]:
        """从新闻列表中提取事件"""
        if not news_items:
            return []
        
        print(f"🔍 开始AI事件抽取: {len(news_items)} 条新闻")
        
        events = []
        batch_size = settings.BATCH_SIZE
        
        for i in range(0, len(news_items), batch_size):
            batch = news_items[i:i + batch_size]
            print(f"  处理批次 {i//batch_size + 1}: {len(batch)} 条")
            
            batch_events = await self._process_batch(batch)
            events.extend(batch_events)
            
            if i + batch_size < len(news_items):
                await asyncio.sleep(1)
        
        print(f"✅ AI事件抽取完成: {len(events)} 个事件")
        return events
    
    async def _process_batch(self, batch: List[Dict]) -> List[NewsEvent]:
        """处理一个批次的新闻"""
        tasks = [self._extract_single_news(news) for news in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        events = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"   ❌ 处理失败 ({i}): {result}")
                continue
            if result:
                events.append(result)
        
        return events
    
    async def _extract_single_news(self, news: Dict) -> Optional[NewsEvent]:
        """提取单条新闻的事件"""
        try:
            # 构建prompt
            prompt = self._build_extraction_prompt(news)
            
            # 调用AI API（模拟）
            response = await self._call_ai_api(prompt)
            
            # 解析响应
            event_data = self._parse_ai_response(response)
            
            if event_data:
                return NewsEvent(
                    news_id=news.get('news_id', ''),
                    event_type=event_data.get('event_type', '未知'),
                    industry=event_data.get('industry', '通用'),
                    summary=event_data.get('summary', ''),
                    sentiment=event_data.get('sentiment', 0.0),
                    confidence=event_data.get('confidence', 0.5),
                    raw_news_title=news.get('title', '')[:500],
                    raw_news_content=news.get('content', '')[:2000],
                    source=news.get('source', 'unknown')
                )
                
        except Exception as e:
            print(f"  提取事件失败 {news.get('news_id', 'unknown')}: {e}")
        
        return None
    
    def _build_extraction_prompt(self, news: Dict) -> str:
        """构建AI提示词"""
        return f"""
请分析以下财经新闻，提取结构化事件信息：

标题：{news.get('title', '')}
内容：{news.get('content', '')[:1000]}
来源：{news.get('source', '')}
发布时间：{news.get('publish_date', '')}

请以JSON格式返回以下信息：
1. event_type: 事件类型（政策发布、财报公告、并购重组、产品发布、行业动态、市场数据、其他）
2. industry: 所属行业（科技、金融、医疗、新能源、消费、制造、房地产、其他）
3. summary: 事件摘要（50字以内）
4. sentiment: 情感倾向（-1到1之间的小数）
5. confidence: 分析置信度（0到1之间的小数）

只返回JSON对象，不要有其他文本。
"""
    
    async def _call_ai_api(self, prompt: str) -> str:
        """调用AI API（模拟版本）"""
        await asyncio.sleep(0.5)
        
        # 返回模拟数据
        return json.dumps({
            "event_type": "政策发布",
            "industry": "科技",
            "summary": "这是一个示例事件摘要",
            "sentiment": 0.3,
            "confidence": 0.85
        })
    
    def _parse_ai_response(self, response: str) -> Optional[Dict]:
        """解析AI响应"""
        try:
            data = json.loads(response)
            required_fields = ['event_type', 'industry', 'summary', 'sentiment', 'confidence']
            if all(field in data for field in required_fields):
                return data
        except json.JSONDecodeError:
            print(f"   JSON解析失败: {response[:100]}...")
        
        return None

# 单例实例
ai_extractor = AIExtractor()
EOF

# 6. 创建 services/event_mapper.py
cat > model_service/services/event_mapper.py << 'EOF'
"""
事件到题材的映射服务
"""
from typing import List, Dict, Any

async def map_events_to_themes(events: List[Dict]) -> List[Dict]:
    """
    将事件映射到题材
    这里可以调用theme_service或使用本地规则
    """
    # 暂时返回空列表，后续集成theme_service
    return []
EOF

# 7. 创建 app.py（主应用）
cat > model_service/app.py << 'EOF'
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
import uvicorn

from .config import settings
from .database import init_database, close_database, DatabaseManager
from .services.ai_extractor import ai_extractor

# 数据结构
class NewsItem(BaseModel):
    news_id: str
    title: str
    content: str
    source: str
    publish_date: str

class ProcessNewsRequest(BaseModel):
    news_list: List[NewsItem]

class ProcessNewsResponse(BaseModel):
    status: str
    message: str
    news_count: int
    event_count: int = 0

# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 启动 model_service...")
    await init_database()
    print("✅ 数据库初始化完成")
    yield
    print("🛑 关闭 model_service...")
    await close_database()

# 创建FastAPI应用
app = FastAPI(
    title="AI事件抽取服务",
    description="从财经新闻中提取结构化事件的AI服务",
    version="1.0.0",
    lifespan=lifespan
)

# CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "service": "AI事件抽取服务",
        "status": "运行中",
        "endpoints": {
            "健康检查": "/health",
            "处理新闻": "POST /api/process-news",
            "统计信息": "GET /api/stats"
        }
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "model_service"
    }

@app.post("/api/process-news", response_model=ProcessNewsResponse)
async def process_news(
    request: ProcessNewsRequest,
    background_tasks: BackgroundTasks
):
    if not request.news_list:
        raise HTTPException(status_code=400, detail="新闻列表不能为空")
    
    print(f"📥 收到处理请求: {len(request.news_list)} 条新闻")
    
    # 转换为字典列表
    news_dicts = [item.dict() for item in request.news_list]
    
    # 在后台处理
    background_tasks.add_task(process_news_batch, news_dicts)
    
    return ProcessNewsResponse(
        status="processing",
        message=f"已开始处理 {len(request.news_list)} 条新闻",
        news_count=len(request.news_list)
    )

async def process_news_batch(news_list: List[Dict]):
    """批量处理新闻（后台任务）"""
    try:
        # 1. AI事件抽取
        events = await ai_extractor.extract_events_from_news(news_list)
        
        if events:
            # 2. 保存到数据库
            saved_count = await DatabaseManager.save_events(events)
            
            print(f"🎯 处理完成: {len(events)} 个事件，保存 {saved_count} 条")
            
            # 3. 触发下游处理
            await trigger_downstream_processing(events)
        else:
            print("⚠️ 未提取到有效事件")
            
    except Exception as e:
        print(f"❌ 批处理失败: {e}")
        import traceback
        traceback.print_exc()

async def trigger_downstream_processing(events):
    """触发下游theme_service处理"""
    print(f"🚀 触发下游处理: {len(events)} 个事件")
    for event in events[:3]:
        print(f"  事件: [{event.event_type}] {event.summary[:50]}...")
    print("📤 准备发送到theme_service...")

@app.get("/api/stats")
async def get_stats():
    """获取统计信息"""
    try:
        async with (await DatabaseManager.get_pool()).acquire() as conn:
            # 事件统计
            event_stats = await conn.fetchrow("""
                SELECT 
                    COUNT(*) as total_events,
                    COUNT(DISTINCT news_id) as unique_news,
                    COUNT(DISTINCT event_type) as event_types,
                    COUNT(DISTINCT industry) as industries
                FROM news_event
            """)
            
            # 按类型分布
            type_dist = await conn.fetch("""
                SELECT event_type, COUNT(*) as count
                FROM news_event
                GROUP BY event_type
                ORDER BY count DESC
                LIMIT 5
            """)
            
            return {
                "event_statistics": dict(event_stats) if event_stats else {},
                "event_type_distribution": [
                    {"event_type": row['event_type'], "count": row['count']}
                    for row in type_dist
                ]
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
EOF

# 8. 创建启动脚本
cat > start_model_service.py << 'EOF'
#!/usr/bin/env python3
"""
启动 AI事件抽取服务
"""
import uvicorn
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from model_service.config import settings

if __name__ == "__main__":
    print(f"🚀 启动 AI事件抽取服务")
    print(f"   地址: http://{settings.HOST}:{settings.PORT}")
    print(f"   API文档: http://{settings.HOST}:{settings.PORT}/docs")
    print("   按 Ctrl+C 停止")
    print("-" * 50)
    
    uvicorn.run(
        "model_service.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
EOF

# 9. 创建测试脚本
cat > test_model_service.py << 'EOF'
#!/usr/bin/env python3
"""
测试 model_service
"""
import asyncio
import aiohttp
import json

async def test_model_service():
    """测试model_service API"""
    test_news = [
        {
            "news_id": "test_001",
            "title": "国家发布人工智能发展规划",
            "content": "近日，国家发布人工智能发展规划，计划在未来五年投入千亿资金支持AI产业发展...",
            "source": "akshare_cls",
            "publish_date": "2024-01-05"
        },
        {
            "news_id": "test_002", 
            "title": "新能源汽车销量大幅增长",
            "content": "据统计，今年新能源汽车销量同比增长120%，市场需求持续旺盛...",
            "source": "akshare_cls",
            "publish_date": "2024-01-05"
        }
    ]
    
    url = "http://localhost:8001/api/process-news"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"news_list": test_news},
                timeout=10
            ) as response:
                result = await response.json()
                print("✅ API测试成功:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
    except Exception as e:
        print(f"❌ 测试失败: {e}")

async def test_health():
    """测试健康检查"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8001/health",
                timeout=5
            ) as response:
                result = await response.json()
                print("🩺 健康检查:")
                print(json.dumps(result, indent=2, ensure_ascii=False))
                
    except Exception as e:
        print(f"❌ 健康检查失败: {e}")

async def main():
    print("🧪 测试 model_service")
    print("=" * 50)
    
    # 先测试健康检查
    await test_health()
    print()
    
    # 测试处理API
    await test_model_service()

if __name__ == "__main__":
    asyncio.run(main())
EOF

# 10. 创建更新news_crawler的脚本
cat > update_crawler_trigger.py << 'EOF'
#!/usr/bin/env python3
"""
更新news_crawler_service以触发model_service
"""
import os

# 在news_crawler_service/database.py中添加的代码
trigger_code = '''
async def _trigger_event_extraction(cls, news_items: List[NewsRawItem]):
    """触发事件抽取服务"""
    try:
        import aiohttp
        
        # 准备数据
        news_data = [
            {
                "news_id": item.news_id,
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "publish_date": item.publish_date.isoformat()
            }
            for item in news_items
        ]
        
        # 调用model_service
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={"news_list": news_data},
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 事件抽取触发成功: {{result.get('message')}}")
                else:
                    print(f"⚠️ 事件抽取触发失败: {{response.status}}")
                    
    except Exception as e:
        print(f"❌ 触发事件抽取异常: {{e}}")

# 在save_news_batch方法调用后触发
async def save_news_batch_and_trigger(cls, news_items: List[NewsRawItem]):
    saved_count = await cls.save_news_batch(news_items)
    
    if saved_count > 0:
        # 异步触发，不阻塞
        asyncio.create_task(cls._trigger_event_extraction(news_items))
    
    return saved_count
'''

print("请手动将以下代码添加到 news_crawler_service/database.py 中:")
print("=" * 60)
print(trigger_code)
print("=" * 60)
print("\n添加位置建议:")
print("1. 在 DatabaseManager 类中添加 _trigger_event_extraction 方法")
print("2. 添加 save_news_batch_and_trigger 方法作为增强版保存")
print("3. 或者修改现有的 save_news_batch 方法末尾添加触发逻辑")
EOF

# 11. 创建 requirements.txt
cat > model_service/requirements.txt << 'EOF'
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
pydantic>=2.0.0
pydantic-settings>=2.0.0
asyncpg>=0.29.0
aiohttp>=3.9.0
python-dotenv>=1.0.0
openai>=1.0.0  # 可选，如果需要OpenAI
EOF

echo "✅ 所有文件创建完成！"
echo ""
echo "📁 创建的文件结构:"
find model_service -type f -name "*.py" | sort
echo ""
echo "🚀 下一步操作:"
echo "1. 启动服务: python start_model_service.py"
echo "2. 测试API: python test_model_service.py"
echo "3. 更新爬虫触发: python update_crawler_trigger.py"