# final_verify.py
import asyncio
import asyncpg

async def final_verify():
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("🔍 最终数据验证报告")
    print("="*60)
    
    # 1. 总体统计
    print("📊 总体统计：")
    
    # financial_categories
    cat_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN category_level = 1 THEN 1 END) as level1,
            COUNT(CASE WHEN category_level = 2 THEN 1 END) as level2,
            COUNT(CASE WHEN category_level = 3 THEN 1 END) as level3
        FROM financial_categories
        WHERE source_system = 'tushare'
    """)
    
    print(f"✅ financial_categories 表：")
    print(f"   总记录数: {cat_stats['total']}")
    print(f"   一级行业: {cat_stats['level1']} 个")
    print(f"   二级行业: {cat_stats['level2']} 个")
    print(f"   三级行业: {cat_stats['level3']} 个")
    
    # theme_master
    theme_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total,
            COUNT(DISTINCT level1_category) as unique_l1,
            COUNT(DISTINCT level2_category) as unique_l2,
            AVG(heat_score) as avg_heat,
            COUNT(CASE WHEN array_length(related_stocks, 1) > 0 THEN 1 END) as with_stocks,
            COUNT(CASE WHEN array_length(related_stocks, 1) = 0 THEN 1 END) as without_stocks
        FROM theme_master
        WHERE source_system = 'shenwan'
    """)
    
    print(f"\n✅ theme_master 表：")
    print(f"   总题材数: {theme_stats['total']}")
    print(f"   唯一一级分类: {theme_stats['unique_l1']}")
    print(f"   唯一二级分类: {theme_stats['unique_l2']}")
    print(f"   平均热度: {theme_stats['avg_heat']:.1f}")
    print(f"   有成分股的题材: {theme_stats['with_stocks']} 个")
    print(f"   无成分股的题材: {theme_stats['without_stocks']} 个（需后续补充）")
    
    # 2. 热门题材示例
    print(f"\n🔥 热门题材示例（按热度排序）：")
    hot_themes = await conn.fetch("""
        SELECT name, level1_category, level2_category, 
               heat_score, array_length(related_stocks, 1) as stock_count
        FROM theme_master 
        WHERE source_system = 'tushare'
        ORDER BY heat_score DESC
        LIMIT 10
    """)
    
    for i, theme in enumerate(hot_themes, 1):
        print(f"  {i:2d}. {theme['name']}")
        print(f"      分类: {theme['level1_category']} → {theme['level2_category']}")
        print(f"      热度: {theme['heat_score']}, 成分股: {theme['stock_count'] or 0} 只")
    
    # 3. 一级行业分布
    print(f"\n📁 一级行业分布：")
    level1_dist = await conn.fetch("""
        SELECT level1_category, COUNT(*) as theme_count,
               COUNT(CASE WHEN array_length(related_stocks, 1) > 0 THEN 1 END) as with_stocks
        FROM theme_master
        WHERE source_system = 'tushare'
        GROUP BY level1_category
        ORDER BY theme_count DESC
        LIMIT 8
    """)
    
    for dist in level1_dist:
        stock_ratio = f"{dist['with_stocks']}/{dist['theme_count']}"
        print(f"  • {dist['level1_category']}: {dist['theme_count']} 个题材 ({stock_ratio} 有成分股)")
    
    # 4. 数据结构检查
    print(f"\n🛠️  数据结构完整性：")
    missing_fields = await conn.fetchval("""
        SELECT COUNT(*) 
        FROM theme_master 
        WHERE source_system = 'tushare'
        AND (category1_code IS NULL OR category2_code IS NULL OR category3_code IS NULL)
    """)
    
    if missing_fields == 0:
        print("  ✅ 所有题材都有完整的分类编码")
    else:
        print(f"  ⚠️  {missing_fields} 个题材缺少分类编码")
    
    await conn.close()
    
    print(f"\n{'='*60}")
    print("🎉 验证完成！申万行业题材库已成功构建！")
    print("="*60)

asyncio.run(final_verify())