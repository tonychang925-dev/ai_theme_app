import asyncpg
import asyncio
from datetime import datetime

async def transfer_shenwan_themes_correctly():
    """
    正确转移申万3级数据到theme_master表
    1. 从financial_categories提取3级作为题材
    2. 清理financial_categories中的3级数据
    3. 确保外键关系正确
    """
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    print("🎯 开始迁移申万3级数据到题材表")
    print("="*60)
    
    try:
        # 连接数据库
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 1. 首先统计现有数据
        print("📊 检查现有数据...")
        
        # 统计各级分类数量
        level1_count = await conn.fetchval("""
            SELECT COUNT(*) FROM financial_categories WHERE category_level = 1
        """)
        level2_count = await conn.fetchval("""
            SELECT COUNT(*) FROM financial_categories WHERE category_level = 2
        """)
        level3_count = await conn.fetchval("""
            SELECT COUNT(*) FROM financial_categories WHERE category_level = 3
        """)
        
        print(f"  1级分类: {level1_count} 个")
        print(f"  2级分类: {level2_count} 个")
        print(f"  3级分类: {level3_count} 个 (将迁移到theme_master)")
        
        # 2. 提取3级数据到theme_master
        print(f"\n📤 提取{level3_count}个3级分类到theme_master表...")
        
        # 获取所有3级数据及其1、2级父级信息
        level3_themes = await conn.fetch("""
            SELECT 
                fc3.category_code as theme_code,
                fc3.category_name as theme_name,
                fc3.description,
                fc2.category_code as level2_code,
                fc2.category_name as level2_name,
                fc1.category_code as level1_code,
                fc1.category_name as level1_name,
                ARRAY[fc1.category_name, fc2.category_name, fc3.category_name] as category_path
            FROM financial_categories fc3
            JOIN financial_categories fc2 ON fc3.parent_code = fc2.category_code
            JOIN financial_categories fc1 ON fc2.parent_code = fc1.category_code
            WHERE fc3.category_level = 3
            ORDER BY fc1.category_code, fc2.category_code, fc3.category_code
        """)
        
        print(f"  ✅ 成功提取 {len(level3_themes)} 个3级题材")
        
        # 3. 插入到theme_master表
        inserted_count = 0
        for theme in level3_themes:
            try:
                await conn.execute("""
                    INSERT INTO theme_master (
                        theme_code, 
                        theme_name, 
                        description, 
                        category1_code,
                        category1_name,
                        category2_code,
                        category2_name,
                        category_path,
                        source_system,
                        theme_type,
                        is_active,
                        created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
                    ON CONFLICT (theme_code) DO UPDATE SET
                        theme_name = EXCLUDED.theme_name,
                        description = EXCLUDED.description,
                        category1_code = EXCLUDED.category1_code,
                        category1_name = EXCLUDED.category1_name,
                        category2_code = EXCLUDED.category2_code,
                        category2_name = EXCLUDED.category2_name,
                        category_path = EXCLUDED.category_path,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    theme['theme_code'],
                    theme['theme_name'],
                    theme['description'],
                    theme['level1_code'],
                    theme['level1_name'],
                    theme['level2_code'],
                    theme['level2_name'],
                    theme['category_path'],
                    'shenwan',
                    'industry',  # 题材类型：行业
                    True,        # 激活状态
                    datetime.now()
                )
                inserted_count += 1
            except Exception as e:
                print(f"  ⚠️  插入失败 {theme['theme_code']}: {str(e)}")
        
        print(f"  ✅ 成功插入/更新 {inserted_count} 个题材到theme_master")
        
        # 4. 验证插入的数据
        theme_master_count = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
        print(f"\n📋 theme_master表现有: {theme_master_count} 个题材")
        
        # 查看前几个作为示例
        sample_themes = await conn.fetch("""
            SELECT theme_code, theme_name, category1_name, category2_name 
            FROM theme_master 
            WHERE source_system = 'shenwan'
            LIMIT 5
        """)
        
        print("\n📝 示例题材数据:")
        print("-" * 60)
        for theme in sample_themes:
            print(f"  代码: {theme['theme_code']}, 名称: {theme['theme_name']}")
            print(f"  分类路径: {theme['category1_name']} → {theme['category2_name']}")
            print("-" * 40)
        
        # 5. 确认是否需要从financial_categories删除3级数据
        print(f"\n🗑️  从financial_categories删除3级数据...")
        confirm = input(f"确认删除{level3_count}个3级分类？(y/N): ").strip().lower()
        
        if confirm == 'y':
            deleted_count = await conn.execute("""
                DELETE FROM financial_categories WHERE category_level = 3
            """)
            print(f"  ✅ 已删除 {deleted_count.split()[1]} 个3级分类")
            
            # 验证删除后的状态
            remaining_count = await conn.fetchval("SELECT COUNT(*) FROM financial_categories")
            remaining_level1 = await conn.fetchval("""
                SELECT COUNT(*) FROM financial_categories WHERE category_level = 1
            """)
            remaining_level2 = await conn.fetchval("""
                SELECT COUNT(*) FROM financial_categories WHERE category_level = 2
            """)
            
            print(f"\n✅ 清理完成!")
            print(f"  financial_categories 剩余: {remaining_count} 行")
            print(f"  其中: 1级分类 {remaining_level1} 个, 2级分类 {remaining_level2} 个")
        else:
            print("  ⚠️  跳过删除操作")
        
        # 6. 创建索引和外键（可选）
        print(f"\n🔗 创建外键关系...")
        try:
            await conn.execute("""
                ALTER TABLE theme_master 
                ADD CONSTRAINT fk_theme_category1 
                FOREIGN KEY (category1_code) 
                REFERENCES financial_categories(category_code);
            """)
            print("  ✅ 创建category1_code外键")
        except Exception as e:
            print(f"  ⚠️  外键已存在或创建失败: {str(e)}")
        
        print("\n🎉 数据迁移完成!")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
    finally:
        await conn.close()

# 运行脚本
if __name__ == "__main__":
    asyncio.run(transfer_shenwan_themes_correctly())