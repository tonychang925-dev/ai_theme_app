# ai_theme_app/news_crawler_service/database.py
import asyncpg
from typing import List, Optional
from datetime import datetime
import logging
from contextlib import asynccontextmanager

from .models.news_raw import NewsRawItem
from .config import settings

# 配置日志
logger = logging.getLogger(__name__)

class DatabaseManager:
    """数据库管理器（连接池模式）"""
    
    _pool: Optional[asyncpg.Pool] = None
    
    @classmethod
    async def get_pool(cls) -> asyncpg.Pool:
        """获取数据库连接池（单例）"""
        if cls._pool is None:
            await cls.initialize()
        return cls._pool
    
    @classmethod
    async def initialize(cls):
        """初始化数据库连接池"""
        try:
            cls._pool = await asyncpg.create_pool(
                dsn=settings.DATABASE_URL,
                min_size=1,
                max_size=10,
                max_queries=50000,
                max_inactive_connection_lifetime=300,
                command_timeout=60,
            )
            logger.info("数据库连接池初始化成功")
            
            # 确保表存在
            await cls._ensure_tables()
            
        except Exception as e:
            logger.error(f"数据库连接池初始化失败: {e}")
            raise
    
    @classmethod
    async def _ensure_tables(cls):
        """确保新闻表存在"""
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS news_raw (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT,
            source VARCHAR(100) NOT NULL,
            publish_date DATE NOT NULL,
            publish_time TIME,
            market VARCHAR(20) DEFAULT 'A股',
            url TEXT,
            news_id VARCHAR(64) UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW(),
            
            -- 索引优化查询性能
            INDEX idx_news_id (news_id),
            INDEX idx_publish_date (publish_date),
            INDEX idx_source (source),
            INDEX idx_created_at (created_at)
        );
        
        -- 创建更新时间的触发器
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ language 'plpgsql';
        
        DROP TRIGGER IF EXISTS update_news_raw_updated_at ON news_raw;
        CREATE TRIGGER update_news_raw_updated_at
        BEFORE UPDATE ON news_raw
        FOR EACH ROW
        EXECUTE FUNCTION update_updated_at_column();
        """
        
        async with cls._pool.acquire() as conn:
            await conn.execute(create_table_sql)
            logger.info("news_raw表验证/创建完成")
    
    @classmethod
    async def save_news_batch(cls, news_items: List[NewsRawItem]) -> int:
        """批量保存新闻到数据库（幂等操作）"""
        if not news_items:
            return 0
        
        saved_count = 0
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            # 开启事务
            async with conn.transaction():
                for item in news_items:
                    try:
                        # 使用INSERT...ON CONFLICT确保幂等性
                        await conn.execute("""
                            INSERT INTO news_raw 
                            (title, content, source, publish_date, publish_time, 
                             market, url, news_id)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (news_id) DO NOTHING
                        """,
                            item.title, item.content, item.source,
                            item.publish_date, item.publish_time,
                            item.market, item.url, item.news_id
                        )
                        saved_count += 1
                        
                    except Exception as e:
                        logger.warning(f"保存新闻失败 (news_id: {item.news_id}): {e}")
                        continue
        
        logger.info(f"批量保存完成: 总计{len(news_items)}条, 成功{saved_count}条")
        return saved_count
    
    @classmethod
    async def check_news_exists(cls, news_id: str) -> bool:
        """检查新闻是否已存在"""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT 1 FROM news_raw WHERE news_id = $1 LIMIT 1",
                news_id
            )
            return result is not None
    
    @classmethod
    async def get_recent_news(cls, limit: int = 20) -> List[dict]:
        """获取最近的新闻（用于调试）"""
        pool = await cls.get_pool()
        
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT title, source, publish_date, news_id
                FROM news_raw 
                ORDER BY publish_date DESC, created_at DESC 
                LIMIT $1
            """, limit)
            
            return [dict(row) for row in rows]
    
    @classmethod
    async def close(cls):
        """关闭数据库连接池"""
        if cls._pool:
            await cls._pool.close()
            cls._pool = None
            logger.info("数据库连接池已关闭")

async def _trigger_event_extraction(self, news_items):
    """触发事件抽取服务"""
    try:
        import aiohttp
        import asyncio
        
        print(f"📤 触发事件抽取: {{len(news_items)}} 条新闻")
        
        # 准备数据
        news_data = [
            {{
                "news_id": item.news_id,
                "title": item.title,
                "content": item.content,
                "source": item.source,
                "publish_date": item.publish_date.isoformat() if hasattr(item.publish_date, "isoformat") else str(item.publish_date)
            }}
            for item in news_items
        ]
        
        # 调用model_service
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8001/api/process-news",
                json={{"news_list": news_data}},
                timeout=10
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print(f"✅ 事件抽取触发成功: {{result.get('message')}}")
                else:
                    print(f"⚠️ 事件抽取触发失败: {{response.status}}")
                    
    except Exception as e:
        print(f"❌ 触发事件抽取异常: {{e}}")

async def save_news_batch_with_trigger(self, news_items):
    """保存新闻并触发事件抽取"""
    saved_count = await self.save_news_batch(news_items)
    
    if saved_count > 0:
        # 异步触发，不阻塞当前操作
        asyncio.create_task(self._trigger_event_extraction(news_items))
    
    return saved_count


# 上下文管理器，方便在with语句中使用
@asynccontextmanager
async def get_db_connection():
    """获取数据库连接的上下文管理器"""
    pool = await DatabaseManager.get_pool()
    async with pool.acquire() as conn:
        yield conn

# 初始化函数（在应用启动时调用）
async def init_database():
    """初始化数据库（应用启动时调用）"""
    await DatabaseManager.initialize()

# 清理函数（在应用关闭时调用）
async def close_database():
    """关闭数据库连接（应用关闭时调用）"""
    await DatabaseManager.close()