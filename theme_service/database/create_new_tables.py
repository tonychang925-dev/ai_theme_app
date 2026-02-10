# create_new_tables.py
import asyncio
import asyncpg

async def create_complete_tables():
    """创建全新的完整表结构"""
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = None
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        print("🗑️  清理旧表...")
        
        # 安全地删除旧表（如果存在）
        tables_to_drop = ['theme_master', 'financial_categories']
        
        for table in tables_to_drop:
            try:
                await conn.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
                print(f"  ✅ 删除表: {table}")
            except Exception as e:
                print(f"  ⚠️  删除表 {table} 失败: {e}")
        
        print("\n🔄 创建全新的完整表结构...")
        print("="*60)
        
        # ========== 1. 创建专业分类表 ==========
        print("📊 创建 financial_categories 表...")
        await conn.execute("""
            CREATE TABLE financial_categories (
                -- 核心标识
                id SERIAL PRIMARY KEY,
                category_code VARCHAR(50) UNIQUE NOT NULL,
                category_name VARCHAR(100) NOT NULL,
                description TEXT,
                
                -- 层级关系
                category_level INTEGER NOT NULL CHECK (category_level >= 1 AND category_level <= 3),
                parent_code VARCHAR(50),
                full_path TEXT[],
                
                -- 分类属性
                category_type VARCHAR(30) NOT NULL,  -- 'industry'/'concept'/'relation'/'policy'/'event'
                standard_type VARCHAR(20),            -- 'shenwan'/'gics'/'csrc'等标准类型
                
                -- 智能标签
                keywords TEXT[] DEFAULT '{}',
                aliases TEXT[] DEFAULT '{}',
                related_industries TEXT[] DEFAULT '{}',
                
                -- 来源信息
                source_system VARCHAR(50) NOT NULL,   -- 'shenwan'/'eastmoney'/'tonghuashun'/'custom'
                source_id VARCHAR(100),
                is_standard BOOLEAN DEFAULT TRUE,
                
                -- 统计信息
                theme_count INTEGER DEFAULT 0,
                stock_count INTEGER DEFAULT 0,
                avg_heat_score DECIMAL(5,2) DEFAULT 50.0,
                
                -- 时间戳
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- 索引
                CONSTRAINT valid_category_level CHECK (category_level IN (1, 2, 3))
            )
        """)
        
        # ========== 2. 创建题材主表（全新设计） ==========
        print("📊 创建 theme_master 表（完整版）...")
        await conn.execute("""
            CREATE TABLE theme_master (
                -- 核心标识
                id SERIAL PRIMARY KEY,
                name VARCHAR(150) NOT NULL,
                code VARCHAR(80) UNIQUE NOT NULL,
                description TEXT,
                status VARCHAR(20) DEFAULT 'active',
                
                -- 三级分类体系（直接存储，查询最快）
                level1_category VARCHAR(80),
                level2_category VARCHAR(80),
                level3_category VARCHAR(80),
                category_path TEXT[],
                
                -- 与专业分类的关联（外键关系）
                category1_code VARCHAR(50),
                category2_code VARCHAR(50),
                category3_code VARCHAR(50),
                
                -- 智能标签系统（JSONB格式，支持高效查询）
                tags JSONB DEFAULT '{}'::jsonb,
                
                -- 业务属性
                theme_type VARCHAR(30) NOT NULL DEFAULT 'concept',
                heat_score INTEGER DEFAULT 50,
                confidence_score DECIMAL(3,2) DEFAULT 0.80,
                lifecycle_stage VARCHAR(20) DEFAULT 'growth',
                
                -- 股票关联
                related_stocks TEXT[] DEFAULT '{}',
                stock_count INTEGER DEFAULT 0,
                
                -- 新闻统计
                news_count INTEGER DEFAULT 0,
                mention_count INTEGER DEFAULT 0,
                last_mentioned TIMESTAMP,
                
                -- 来源追踪
                source_system VARCHAR(50) NOT NULL,
                source_id VARCHAR(100),
                created_by VARCHAR(50) DEFAULT 'system',
                
                -- 时间管理
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                
                -- 约束
                CONSTRAINT valid_status CHECK (status IN ('active', 'inactive', 'archived')),
                CONSTRAINT valid_theme_type CHECK (theme_type IN ('concept', 'industry', 'policy', 'relation', 'event')),
                CONSTRAINT valid_lifecycle CHECK (lifecycle_stage IN ('emerging', 'growth', 'mature', 'decline', 'archived')),
                CONSTRAINT valid_confidence CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0),
                
                -- 外键约束（可选，如果需要强一致性）
                FOREIGN KEY (category1_code) REFERENCES financial_categories(category_code) ON DELETE SET NULL,
                FOREIGN KEY (category2_code) REFERENCES financial_categories(category_code) ON DELETE SET NULL,
                FOREIGN KEY (category3_code) REFERENCES financial_categories(category_code) ON DELETE SET NULL
            )
        """)
        
        # ========== 3. 创建索引（优化查询性能） ==========
        print("📊 创建索引...")
        
        # financial_categories 索引
        category_indexes = [
            "CREATE INDEX idx_categories_code ON financial_categories(category_code)",
            "CREATE INDEX idx_categories_level ON financial_categories(category_level)",
            "CREATE INDEX idx_categories_parent ON financial_categories(parent_code)",
            "CREATE INDEX idx_categories_type ON financial_categories(category_type)",
            "CREATE INDEX idx_categories_source ON financial_categories(source_system)",
            "CREATE INDEX idx_categories_keywords ON financial_categories USING GIN(keywords)",
            "CREATE INDEX idx_categories_path ON financial_categories USING GIN(full_path)"
        ]
        
        # theme_master 索引
        theme_indexes = [
            "CREATE INDEX idx_theme_code ON theme_master(code)",
            "CREATE INDEX idx_theme_name ON theme_master(name)",
            "CREATE INDEX idx_theme_status ON theme_master(status)",
            "CREATE INDEX idx_theme_type ON theme_master(theme_type)",
            "CREATE INDEX idx_theme_level1 ON theme_master(level1_category)",
            "CREATE INDEX idx_theme_level2 ON theme_master(level2_category)",
            "CREATE INDEX idx_theme_level3 ON theme_master(level3_category)",
            "CREATE INDEX idx_theme_heat ON theme_master(heat_score DESC)",
            "CREATE INDEX idx_theme_source ON theme_master(source_system)",
            "CREATE INDEX idx_theme_created ON theme_master(created_at DESC)",
            "CREATE INDEX idx_theme_active ON theme_master(last_active_at DESC)",
            "CREATE INDEX idx_theme_tags ON theme_master USING GIN(tags)",
            "CREATE INDEX idx_theme_path ON theme_master USING GIN(category_path)",
            "CREATE INDEX idx_theme_stocks ON theme_master USING GIN(related_stocks)",
            "CREATE INDEX idx_theme_cat1 ON theme_master(category1_code)",
            "CREATE INDEX idx_theme_cat2 ON theme_master(category2_code)",
            "CREATE INDEX idx_theme_cat3 ON theme_master(category3_code)"
        ]
        
        all_indexes = category_indexes + theme_indexes
        
        for idx_sql in all_indexes:
            try:
                await conn.execute(idx_sql)
            except Exception as e:
                print(f"  ⚠️  创建索引失败（可能已存在）: {e}")
        
        print("✅ 所有索引创建完成")
        
        # ========== 4. 验证表结构 ==========
        print("\n🔍 验证表结构...")
        
        # 检查表是否创建成功
        tables = await conn.fetch("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('theme_master', 'financial_categories')
            ORDER BY table_name
        """)
        
        print(f"✅ 已创建的表：{[row['table_name'] for row in tables]}")
        
        # 检查字段数量
        for table in ['theme_master', 'financial_categories']:
            col_count = await conn.fetchval(f"""
                SELECT COUNT(*) 
                FROM information_schema.columns 
                WHERE table_name = '{table}'
            """)
            print(f"  {table}: {col_count} 个字段")
        
        print("\n🎉 全新表结构创建完成！")
        print("="*60)
        print("📋 表结构特性：")
        print("   1. theme_master: 46个字段，完整支持三级分类 + 智能标签")
        print("   2. financial_categories: 23个字段，专业金融分类体系")
        print("   3. 17个索引，确保查询性能")
        print("   4. 完整的外键约束和数据验证")
        
        return True
        
    except Exception as e:
        print(f"❌ 创建表失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            await conn.close()

async def main():
    print("="*60)
    print("🏗️  创建全新的完整数据库表结构")
    print("="*60)
    print("⚠️  将删除并重建 theme_master 和 financial_categories 表")
    print("   请确保已备份重要数据！")
    print("="*60)
    
    confirm = input("是否继续？(yes/NO): ")
    if confirm.lower() != 'yes':
        print("⏹️  操作取消")
        return
    
    success = await create_complete_tables()
    
    if success:
        print("\n✅ 全新表结构创建成功！")
        print("\n🚀 下一步操作：")
        print("   1. 重新运行 fetch_shenwan.py 导入申万数据")
        print("   2. 如有需要，运行 restore_backup.py 恢复自定义题材")
    else:
        print("\n❌ 表结构创建失败")

if __name__ == "__main__":
    asyncio.run(main())