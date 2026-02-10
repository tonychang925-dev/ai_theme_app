import asyncpg
import asyncio
from datetime import datetime
import json

async def migrate_tables():
    """迁移financial_categories和theme_master表"""
    
    source_conn = None
    target_conn = None
    
    try:
        print("🔗 连接数据库...")
        # 连接源数据库
        source_conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='zxbzj~925',
            database='stock_data'
        )
        
        # 连接目标数据库
        target_conn = await asyncpg.connect(
            host='localhost',
            port=5432,
            user='postgres',
            password='zxbzj~925',
            database='stock_data_test'
        )
        
        # 1. 清空目标表
        print("🗑️  清空目标表...")
        await target_conn.execute("TRUNCATE TABLE financial_categories CASCADE")
        await target_conn.execute("TRUNCATE TABLE theme_master CASCADE")
        
        # 2. 迁移 financial_categories
        print("📤 迁移 financial_categories...")
        categories = await source_conn.fetch("SELECT * FROM financial_categories ORDER BY id")
        
        for cat in categories:
            # 构建tags JSON
            tags = {
                "category_type": cat.get('category_type', 'industry'),
                "source_system": cat.get('source_system', ''),
                "standard_type": cat.get('standard_type'),
                "is_standard": cat.get('is_standard', True),
                "theme_count": cat.get('theme_count', 0),
                "stock_count": cat.get('stock_count', 0),
                "avg_heat_score": float(cat.get('avg_heat_score', 50.0)) if cat.get('avg_heat_score') else 50.0,
                "keywords": cat.get('keywords', []),
                "aliases": cat.get('aliases', []),
                "related_industries": cat.get('related_industries', []),
                "source_id": cat.get('source_id')
            }
            
            # 移除None值
            tags = {k: v for k, v in tags.items() if v is not None}
            
            await target_conn.execute("""
                INSERT INTO financial_categories 
                (id, category_code, category_name, parent_code, level, 
                 description, tags, created_at, updated_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
                cat['id'],
                cat['category_code'],
                cat['category_name'],
                cat['parent_code'],
                cat['category_level'],
                cat['description'],
                json.dumps(tags, ensure_ascii=False),
                cat['created_at'],
                cat['updated_at'] or datetime.now()
            )
        
        print(f"✅ 迁移 {len(categories)} 条 financial_categories 记录")
        
        # 3. 迁移 theme_master
        print("📤 迁移 theme_master...")
        themes = await source_conn.fetch("SELECT * FROM theme_master WHERE status = 'active' ORDER BY id")
        
        for theme in themes:
            await target_conn.execute("""
                INSERT INTO theme_master 
                (id, name, code, description, status, level1_category, 
                 level2_category, level3_category, category_path, category1_code,
                 category2_code, category3_code, tags, theme_type, heat_score,
                 confidence_score, lifecycle_stage, related_stocks, stock_count,
                 news_count, mention_count, last_mentioned, source_system, source_id,
                 created_by, created_at, updated_at, last_active_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
                       $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28)
            """,
                theme['id'],
                theme['name'],
                theme['code'],
                theme['description'],
                theme['status'],
                theme['level1_category'],
                theme['level2_category'],
                theme['level3_category'],
                theme['category_path'],
                theme['category1_code'],
                theme['category2_code'],
                theme['category3_code'],
                theme['tags'],
                theme['theme_type'],
                theme['heat_score'],
                float(theme['confidence_score']) if theme['confidence_score'] else 0.80,
                theme['lifecycle_stage'],
                theme['related_stocks'],
                theme['stock_count'],
                theme['news_count'],
                theme['mention_count'],
                theme['last_mentioned'],
                theme['source_system'],
                theme['source_id'],
                theme['created_by'],
                theme['created_at'],
                theme['updated_at'] or datetime.now(),
                theme['last_active_at'] or datetime.now()
            )
        
        print(f"✅ 迁移 {len(themes)} 条 theme_master 记录")
        
        # 4. 重置序列
        print("🔄 重置序列...")
        await target_conn.execute("""
            SELECT setval('financial_categories_id_seq', 
                COALESCE((SELECT MAX(id) FROM financial_categories), 1), true);
            SELECT setval('theme_master_id_seq', 
                COALESCE((SELECT MAX(id) FROM theme_master), 1), true);
        """)
        
        # 5. 验证
        print("🔍 验证结果...")
        cat_count = await target_conn.fetchval("SELECT COUNT(*) FROM financial_categories")
        theme_count = await target_conn.fetchval("SELECT COUNT(*) FROM theme_master WHERE status = 'active'")
        
        print(f"   financial_categories: {cat_count} 条")
        print(f"   theme_master: {theme_count} 条")
        
        print("🎉 迁移完成！")
        
    except Exception as e:
        print(f"❌ 迁移失败: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if source_conn:
            await source_conn.close()
        if target_conn:
            await target_conn.close()

if __name__ == "__main__":
    asyncio.run(migrate_tables())