import asyncpg
import asyncio
from datetime import datetime

async def transfer_shenwan_themes_corrected():
    """
    修正版：正确转移申万3级数据到theme_master表
    使用正确的列名
    """
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    print("🎯 迁移申万3级数据到题材表（修正版）")
    print("="*60)
    
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 1. 检查数据统计
        print("📊 检查现有数据...")
        
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
        
        # 2. 检查theme_master表结构
        print("\n🔍 检查theme_master表结构...")
        columns = await conn.fetch("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'theme_master'
            ORDER BY ordinal_position
        """)
        
        print("  现有列:")
        col_names = []
        for col in columns:
            col_names.append(col['column_name'])
            print(f"    • {col['column_name']}")
        
        # 检查必要列是否存在
        required_columns = ['code', 'name', 'level1_category', 'level2_category', 'level3_category']
        missing_columns = [col for col in required_columns if col not in col_names]
        
        if missing_columns:
            print(f"  ⚠️  缺少必要列: {missing_columns}")
            return
        
        # 3. 提取3级数据
        print(f"\n📤 提取{level3_count}个3级分类数据...")
        
        level3_themes = await conn.fetch("""
            SELECT 
                fc3.category_code as industry_code,
                fc3.category_name as industry_name,
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
        
        # 4. 插入到theme_master表（使用正确的列名）
        inserted_count = 0
        skipped_count = 0
        
        print("\n💾 插入到theme_master表...")
        
        for i, theme in enumerate(level3_themes):
            try:
                # 生成题材代码（使用SW_前缀）
                theme_code = f"SW_{theme['industry_code']}"
                
                await conn.execute("""
                    INSERT INTO theme_master (
                        code, 
                        name, 
                        description, 
                        level1_category,
                        level2_category,
                        level3_category,
                        category_path,
                        category1_code,
                        category2_code,
                        category3_code,
                        theme_type,
                        is_active,
                        source_system,
                        created_at
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (code) DO UPDATE SET
                        name = EXCLUDED.name,
                        level1_category = EXCLUDED.level1_category,
                        level2_category = EXCLUDED.level2_category,
                        level3_category = EXCLUDED.level3_category,
                        category_path = EXCLUDED.category_path,
                        category1_code = EXCLUDED.category1_code,
                        category2_code = EXCLUDED.category2_code,
                        category3_code = EXCLUDED.category3_code,
                        updated_at = CURRENT_TIMESTAMP
                """,
                    theme_code,                    # code
                    theme['industry_name'],        # name
                    f"申万三级行业: {theme['industry_name']}",  # description
                    theme['level1_name'],          # level1_category
                    theme['level2_name'],          # level2_category
                    theme['industry_name'],        # level3_category
                    theme['category_path'],        # category_path
                    theme['level1_code'],          # category1_code
                    theme['level2_code'],          # category2_code
                    theme['industry_code'],        # category3_code
                    'industry',                    # theme_type
                    True,                          # is_active
                    'shenwan',                     # source_system
                    datetime.now()                 # created_at
                )
                inserted_count += 1
                
                # 显示进度
                if (i + 1) % 50 == 0 or (i + 1) == len(level3_themes):
                    print(f"    进度: {i + 1}/{len(level3_themes)}")
                    
            except Exception as e:
                skipped_count += 1
                print(f"  ⚠️  插入失败 {theme['industry_code']}: {str(e)[:50]}...")
                continue
        
        print(f"\n✅ 插入完成!")
        print(f"  成功: {inserted_count} 个")
        print(f"  失败: {skipped_count} 个")
        
        # 5. 验证数据
        theme_master_count = await conn.fetchval("""
            SELECT COUNT(*) FROM theme_master WHERE source_system = 'shenwan'
        """)
        print(f"\n📋 theme_master表现有 {theme_master_count} 个申万题材")
        
        # 显示示例数据
        sample_themes = await conn.fetch("""
            SELECT code, name, level1_category, level2_category
            FROM theme_master 
            WHERE source_system = 'shenwan'
            LIMIT 5
        """)
        
        print("\n📝 示例题材:")
        print("-" * 60)
        for theme in sample_themes:
            print(f"  代码: {theme['code']}")
            print(f"  名称: {theme['name']}")
            print(f"  分类: {theme['level1_category']} → {theme['level2_category']}")
            print("-" * 40)
        
        # 6. 清理financial_categories中的3级数据
        print(f"\n🗑️  清理financial_categories中的3级数据...")
        confirm = input(f"确认删除{level3_count}个3级分类？(y/N): ").strip().lower()
        
        if confirm == 'y':
            # 先备份到临时表（可选）
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS shenwan_l3_backup AS 
                SELECT * FROM financial_categories WHERE category_level = 3
            """)
            
            deleted_count = await conn.execute("""
                DELETE FROM financial_categories WHERE category_level = 3
            """)
            
            print(f"  ✅ 已删除 {deleted_count.split()[1]} 个3级分类")
            print(f"  💾 备份到 shenwan_l3_backup 表")
            
            # 验证清理结果
            remaining_level1 = await conn.fetchval("""
                SELECT COUNT(*) FROM financial_categories WHERE category_level = 1
            """)
            remaining_level2 = await conn.fetchval("""
                SELECT COUNT(*) FROM financial_categories WHERE category_level = 2
            """)
            remaining_total = await conn.fetchval("""
                SELECT COUNT(*) FROM financial_categories
            """)
            
            print(f"\n📊 清理后统计:")
            print(f"  1级分类: {remaining_level1} 个")
            print(f"  2级分类: {remaining_level2} 个")
            print(f"  总计: {remaining_total} 个")
        else:
            print("  ⚠️  跳过清理操作")
        
        print("\n🎉 迁移完成!")
        
    except Exception as e:
        print(f"❌ 错误: {str(e)}")
    finally:
        if conn:
            await conn.close()

# 快速检查SQL版本（如果需要手动执行）
def get_correct_sql():
    """获取正确的SQL语句"""
    sql = """
-- 1. 查询3级数据并生成theme_master格式
SELECT 
    fc3.category_code as industry_code,
    fc3.category_name as industry_name,
    fc2.category_code as level2_code,
    fc2.category_name as level2_name,
    fc1.category_code as level1_code,
    fc1.category_name as level1_name,
    ARRAY[fc1.category_name, fc2.category_name, fc3.category_name] as category_path,
    'SW_' || fc3.category_code as theme_code
FROM financial_categories fc3
JOIN financial_categories fc2 ON fc3.parent_code = fc2.category_code
JOIN financial_categories fc1 ON fc2.parent_code = fc1.category_code
WHERE fc3.category_level = 3
LIMIT 10;

-- 2. 插入到theme_master的示例SQL
INSERT INTO theme_master (
    code, 
    name, 
    description, 
    level1_category,
    level2_category,
    level3_category,
    category_path,
    category1_code,
    category2_code,
    category3_code,
    theme_type,
    is_active,
    source_system,
    created_at
) 
SELECT 
    'SW_' || fc3.category_code as code,
    fc3.category_name as name,
    '申万三级行业: ' || fc3.category_name as description,
    fc1.category_name as level1_category,
    fc2.category_name as level2_category,
    fc3.category_name as level3_category,
    ARRAY[fc1.category_name, fc2.category_name, fc3.category_name] as category_path,
    fc1.category_code as category1_code,
    fc2.category_code as category2_code,
    fc3.category_code as category3_code,
    'industry' as theme_type,
    true as is_active,
    'shenwan' as source_system,
    CURRENT_TIMESTAMP as created_at
FROM financial_categories fc3
JOIN financial_categories fc2 ON fc3.parent_code = fc2.category_code
JOIN financial_categories fc1 ON fc2.parent_code = fc1.category_code
WHERE fc3.category_level = 3
ON CONFLICT (code) DO UPDATE SET
    name = EXCLUDED.name,
    level1_category = EXCLUDED.level1_category,
    level2_category = EXCLUDED.level2_category,
    level3_category = EXCLUDED.level3_category,
    updated_at = CURRENT_TIMESTAMP;
    """
    
    print("正确的SQL语句已生成")
    return sql

if __name__ == "__main__":
    # 运行迁移脚本
    asyncio.run(transfer_shenwan_themes_corrected())
    
    # 如果需要手动执行SQL
    # print("\n📝 如果需要手动执行，以下是正确SQL:")
    # print(get_correct_sql())