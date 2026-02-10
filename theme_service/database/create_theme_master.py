# theme_service/database/create_theme_master.py
"""
创建统一的三级分类题材库表结构
"""
import asyncio
import asyncpg
import logging
import os
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 完整的表结构定义
THEME_MASTER_SCHEMA = """
-- 题材/主题主表（统一三级分类结构）
CREATE TABLE IF NOT EXISTS theme_master (
    -- ========== 1. 核心标识 ==========
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    code VARCHAR(50) UNIQUE,
    description TEXT,
    status VARCHAR(20) DEFAULT 'active',
    
    -- ========== 2. 三级分类体系 ==========
    level1_category VARCHAR(50),
    level1_code VARCHAR(20),
    
    level2_category VARCHAR(50),
    level2_code VARCHAR(20),
    
    level3_category VARCHAR(50),
    level3_code VARCHAR(20),
    
    parent_id INTEGER,
    category_path TEXT[],
    depth INTEGER DEFAULT 1,
    
    -- ========== 3. 智能标签系统 ==========
    tags JSONB DEFAULT '{}',
    
    -- ========== 4. 来源与属性 ==========
    source_system VARCHAR(30) DEFAULT 'standard',
    source_id VARCHAR(100),
    theme_type VARCHAR(20) DEFAULT 'concept',
    
    -- ========== 5. 热度与生命周期 ==========
    heat_score INTEGER DEFAULT 50,
    confidence_score FLOAT DEFAULT 0.9,
    lifecycle VARCHAR(20) DEFAULT 'growth',
    
    -- ========== 6. 统计信息 ==========
    related_stocks TEXT[] DEFAULT '{}',
    news_count INTEGER DEFAULT 0,
    mention_count INTEGER DEFAULT 0,
    
    -- ========== 7. 时间戳 ==========
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- ========== 8. 约束 ==========
    CONSTRAINT valid_heat CHECK (heat_score >= 0 AND heat_score <= 100),
    CONSTRAINT valid_confidence CHECK (confidence_score >= 0 AND confidence_score <= 1),
    CONSTRAINT valid_depth CHECK (depth >= 1 AND depth <= 3),
    CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'archived')),
    CONSTRAINT valid_type CHECK (theme_type IN ('industry', 'concept', 'policy', 'event', 'relation'))
);
"""

# 索引定义
THEME_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_theme_name ON theme_master(name)",
    "CREATE INDEX IF NOT EXISTS idx_theme_code ON theme_master(code)",
    "CREATE INDEX IF NOT EXISTS idx_theme_level1 ON theme_master(level1_category)",
    "CREATE INDEX IF NOT EXISTS idx_theme_level2 ON theme_master(level2_category)",
    "CREATE INDEX IF NOT EXISTS idx_theme_level3 ON theme_master(level3_category)",
    "CREATE INDEX IF NOT EXISTS idx_theme_depth ON theme_master(depth)",
    "CREATE INDEX IF NOT EXISTS idx_theme_parent ON theme_master(parent_id)",
    "CREATE INDEX IF NOT EXISTS idx_theme_tags ON theme_master USING GIN(tags)",
    "CREATE INDEX IF NOT EXISTS idx_theme_path ON theme_master USING GIN(category_path)",
    "CREATE INDEX IF NOT EXISTS idx_theme_stocks ON theme_master USING GIN(related_stocks)",
    "CREATE INDEX IF NOT EXISTS idx_theme_heat ON theme_master(heat_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_theme_source ON theme_master(source_system, source_id)",
    "CREATE INDEX IF NOT EXISTS idx_theme_type ON theme_master(theme_type)",
    "CREATE INDEX IF NOT EXISTS idx_theme_status ON theme_master(status)",
    "CREATE INDEX IF NOT EXISTS idx_theme_active ON theme_master(last_active_at DESC)",
]

class ThemeDatabaseCreator:
    """创建主题数据库"""
    
    def __init__(self, db_url: str = None):
        self.db_url = db_url or "postgresql://postgres:zxbzj~925@localhost/stock_data"
        self.pool = None
    
    async def connect(self):
        """连接数据库"""
        try:
            self.pool = await asyncpg.create_pool(self.db_url, min_size=2, max_size=5)
            logger.info("✅ 数据库连接成功")
            return True
        except Exception as e:
            logger.error(f"❌ 连接失败: {e}")
            return False
    
    async def create_table(self):
        """创建表"""
        async with self.pool.acquire() as conn:
            try:
                # 检查表是否存在
                table_exists = await conn.fetchval("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'theme_master'
                    )
                """)
                
                if table_exists:
                    print("\n⚠️  theme_master表已存在")
                    choice = input("是否删除并重建？(y/N): ")
                    if choice.lower() != 'y':
                        print("⏹️  保留现有表")
                        return False
                    
                    # 删除旧表
                    await conn.execute("DROP TABLE IF EXISTS theme_master CASCADE")
                    print("🗑️  已删除旧表")
                
                # 创建新表
                await conn.execute(THEME_MASTER_SCHEMA)
                logger.info("✅ 创建theme_master表成功")
                
                # 创建索引
                for index_sql in THEME_INDEXES:
                    try:
                        await conn.execute(index_sql)
                    except Exception as e:
                        logger.warning(f"创建索引失败: {e}")
                
                logger.info("✅ 创建索引完成")
                return True
                
            except Exception as e:
                logger.error(f"❌ 创建表失败: {e}")
                return False
    
    async def verify_table(self):
        """验证表结构"""
        async with self.pool.acquire() as conn:
            try:
                # 查看表结构
                columns = await conn.fetch("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'theme_master'
                    ORDER BY ordinal_position
                """)
                
                print("\n📋 表结构验证:")
                print("-" * 60)
                print(f"{'字段名':<20} {'类型':<20} {'可空':<10}")
                print("-" * 60)
                for col in columns:
                    print(f"{col['column_name']:<20} {col['data_type']:<20} {col['is_nullable']:<10}")
                
                # 检查约束
                constraints = await conn.fetch("""
                    SELECT constraint_name, constraint_type
                    FROM information_schema.table_constraints
                    WHERE table_name = 'theme_master'
                """)
                
                print(f"\n🔒 约束检查 ({len(constraints)} 个):")
                for con in constraints:
                    print(f"  - {con['constraint_name']}: {con['constraint_type']}")
                
                # 检查索引
                indexes = await conn.fetch("""
                    SELECT indexname, indexdef
                    FROM pg_indexes
                    WHERE tablename = 'theme_master'
                """)
                
                print(f"\n📊 索引检查 ({len(indexes)} 个):")
                for idx in indexes[:5]:  # 显示前5个
                    print(f"  - {idx['indexname']}")
                
                if len(indexes) > 5:
                    print(f"    ... 还有 {len(indexes)-5} 个索引")
                
                return True
                
            except Exception as e:
                logger.error(f"❌ 验证失败: {e}")
                return False
    
    async def close(self):
        """关闭连接"""
        if self.pool:
            await self.pool.close()
            logger.info("✅ 数据库连接已关闭")

async def main():
    """主函数"""
    print("=" * 60)
    print("🚀 创建三级分类题材库表结构")
    print("=" * 60)
    
    creator = ThemeDatabaseCreator()
    
    try:
        # 1. 连接数据库
        if not await creator.connect():
            return
        
        # 2. 创建表
        if not await creator.create_table():
            return
        
        # 3. 验证表结构
        await creator.verify_table()
        
        print("\n🎉 表结构创建完成！")
        print("📌 下一步：初始化标准题材数据")
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断")
    except Exception as e:
        logger.error(f"❌ 操作异常: {e}")
    finally:
        await creator.close()

if __name__ == "__main__":
    asyncio.run(main())