"""
theme_service 数据库模块
处理主题相关的数据库操作
"""
import asyncpg
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, date

logger = logging.getLogger(__name__)

class ThemeDatabase:
    """主题数据库管理器"""
    
    def __init__(self, database_url: str):
        """
        初始化数据库管理器
        
        Args:
            database_url: 数据库连接URL
        """
        self.database_url = database_url
        self._connection_pool = None
        logger.info(f"ThemeDatabase 初始化，URL: {database_url[:30]}...")
    
    async def initialize(self):
        """初始化数据库连接池"""
        try:
            self._connection_pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logger.info("✅ 数据库连接池创建成功")
            
            # 初始化表结构
            await self._ensure_tables()
            
            return True
        except Exception as e:
            logger.error(f"❌ 数据库初始化失败: {e}")
            return False
    
    async def _ensure_tables(self):
        """确保所有必要的表存在"""
        if not self._connection_pool:
            return
        
        async with self._connection_pool.acquire() as conn:
            # 1. theme_master 表（如果不存在）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS theme_master (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    keywords TEXT[] DEFAULT '{}',
                    status VARCHAR(50) DEFAULT 'active',
                    discovery_source VARCHAR(50),
                    discovery_confidence FLOAT DEFAULT 0.0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            # 2. event_theme_map 表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS event_theme_map (
                    id SERIAL PRIMARY KEY,
                    event_id INTEGER NOT NULL,
                    theme_id INTEGER NOT NULL REFERENCES theme_master(id),
                    confidence FLOAT DEFAULT 0.0,
                    confidence_level VARCHAR(20),
                    confidence_weight INTEGER DEFAULT 0,
                    matched_keywords TEXT[],
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(event_id, theme_id)
                )
            """)
            
            # 3. theme_heat 表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS theme_heat (
                    id SERIAL PRIMARY KEY,
                    theme_id INTEGER NOT NULL REFERENCES theme_master(id),
                    date DATE NOT NULL DEFAULT CURRENT_DATE,
                    heat_value FLOAT DEFAULT 0.0,
                    event_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(theme_id, date)
                )
            """)
            
            # 4. theme_lifecycle 表
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS theme_lifecycle (
                    id SERIAL PRIMARY KEY,
                    theme_id INTEGER NOT NULL REFERENCES theme_master(id),
                    status VARCHAR(50) NOT NULL,
                    start_date DATE NOT NULL DEFAULT CURRENT_DATE,
                    end_date DATE,
                    confidence FLOAT,
                    indicators JSONB,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            
            logger.info("✅ 数据库表结构验证完成")
    
    async def acquire_connection(self):
        """直接获取数据库连接"""
        if not self._connection_pool:
            await self.initialize()
        return await self._connection_pool.acquire()
    
    async def execute_query(self, query: str, *args) -> List[Dict[str, Any]]:
        """执行查询并返回字典列表"""
        async with self._connection_pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
            return [dict(row) for row in rows]
    
    async def execute_update(self, query: str, *args) -> str:
        """执行更新操作"""
        async with self._connection_pool.acquire() as conn:
            result = await conn.execute(query, *args)
            return result
    
    async def save_theme(self, theme_data: Dict[str, Any]) -> int:
        """保存主题到数据库"""
        try:
            query = """
                INSERT INTO theme_master 
                (name, keywords, status, discovery_source, discovery_confidence)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO UPDATE SET
                    keywords = EXCLUDED.keywords,
                    status = EXCLUDED.status,
                    discovery_confidence = EXCLUDED.discovery_confidence,
                    updated_at = NOW()
                RETURNING id
            """
            
            result = await self.execute_query(
                query,
                theme_data.get("name"),
                theme_data.get("keywords", []),
                theme_data.get("status", "candidate"),
                theme_data.get("discovery_source", "ai_discovered"),
                theme_data.get("confidence", 0.5)
            )
            
            if result:
                theme_id = result[0]["id"]
                logger.info(f"✅ 主题保存成功: {theme_data.get('name')} (ID: {theme_id})")
                return theme_id
            
            return 0
            
        except Exception as e:
            logger.error(f"❌ 保存主题失败: {e}")
            return 0
    
    async def save_event_theme_mapping(self, event_id: int, theme_id: int, confidence: float) -> bool:
        """保存事件-主题映射"""
        try:
            # 确定置信度等级
            if confidence >= 0.7:
                level = "strong"
                weight = 100
            elif confidence >= 0.4:
                level = "medium"
                weight = 60
            elif confidence >= 0.1:
                level = "weak"
                weight = 30
            else:
                level = "ignore"
                weight = 0
            
            query = """
                INSERT INTO event_theme_map 
                (event_id, theme_id, confidence, confidence_level, confidence_weight)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (event_id, theme_id) DO UPDATE SET
                    confidence = EXCLUDED.confidence,
                    confidence_level = EXCLUDED.confidence_level,
                    confidence_weight = EXCLUDED.confidence_weight,
                    created_at = NOW()
            """
            
            await self.execute_update(query, event_id, theme_id, confidence, level, weight)
            logger.debug(f"✅ 事件-主题映射保存: event={event_id}, theme={theme_id}, conf={confidence}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 保存映射失败: {e}")
            return False
    
    async def get_recent_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取最近的事件"""
        try:
            query = """
                SELECT 
                    ne.id, ne.event_type, ne.impact_industries,
                    ne.direction, ne.confidence, ne.summary,
                    ne.created_at, nr.title, nr.news_id
                FROM news_event ne
                JOIN news_raw nr ON ne.news_id = nr.id
                ORDER BY ne.created_at DESC
                LIMIT $1
            """
            
            return await self.execute_query(query, limit)
            
        except Exception as e:
            logger.error(f"❌ 获取最近事件失败: {e}")
            return []
    
    async def get_themes_by_status(self, status: str = "active", limit: int = 50) -> List[Dict[str, Any]]:
        """根据状态获取主题"""
        try:
            query = """
                SELECT * FROM theme_master
                WHERE status = $1
                ORDER BY created_at DESC
                LIMIT $2
            """
            
            return await self.execute_query(query, status, limit)
            
        except Exception as e:
            logger.error(f"❌ 获取主题失败: {e}")
            return []
    
    async def update_theme_heat(self, theme_id: int, heat_value: float, event_count: int = 1):
        """更新主题热度"""
        try:
            query = """
                INSERT INTO theme_heat (theme_id, heat_value, event_count, date)
                VALUES ($1, $2, $3, CURRENT_DATE)
                ON CONFLICT (theme_id, date) DO UPDATE SET
                    heat_value = EXCLUDED.heat_value,
                    event_count = EXCLUDED.event_count,
                    created_at = NOW()
            """
            
            await self.execute_update(query, theme_id, heat_value, event_count)
            logger.debug(f"✅ 更新主题热度: theme={theme_id}, heat={heat_value}")
            
        except Exception as e:
            logger.error(f"❌ 更新热度失败: {e}")
    
    async def close(self):
        """关闭数据库连接"""
        if self._connection_pool:
            await self._connection_pool.close()
            logger.info("✅ 数据库连接已关闭")
    
    async def health_check(self) -> bool:
        """数据库健康检查"""
        try:
            if not self._connection_pool:
                await self.initialize()
            
            # 直接从连接池获取连接
            async with self._connection_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                return result == 1
        except Exception as e:
            logger.error(f"❌ 数据库健康检查失败: {e}")
            return False

# 兼容性别名
DatabaseManager = ThemeDatabase

# 创建全局实例（如果需要）
def create_database_manager():
    """创建数据库管理器实例"""
    from theme_service.config import settings
    return ThemeDatabase(settings.DATABASE_URL)

# 添加缺失的 get_conn 函数（兼容性）
def get_conn():
    """
    获取数据库连接（兼容性函数）
    注意：这是一个同步函数，返回一个异步上下文管理器
    """
    from theme_service.config import settings
    
    db = ThemeDatabase(settings.DATABASE_URL)
    
    class AsyncConnection:
        async def __aenter__(self):
            await db.initialize()
            return db
        
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            await db.close()
    
    return AsyncConnection()

# 添加其他可能缺失的兼容性函数
async def execute_sql(query: str, *args):
    """执行SQL查询（兼容性函数）"""
    db = ThemeDatabase(settings.DATABASE_URL)
    await db.initialize()
    try:
        result = await db.execute_query(query, *args)
        return result
    finally:
        await db.close()

async def update_sql(query: str, *args):
    """执行SQL更新（兼容性函数）"""
    db = ThemeDatabase(settings.DATABASE_URL)
    await db.initialize()
    try:
        result = await db.execute_update(query, *args)
        return result
    finally:
        await db.close()
