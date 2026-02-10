# final_check.py
import asyncio
import asyncpg
import json

async def final_check():
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("🔍 题材数据库最终状态检查")
    print("="*60)
    
    # 1. 总体概览
    print("📊 数据库总体概览：")
    
    overall = await conn.fetchrow("""
        SELECT 
            (SELECT COUNT(*) FROM financial_categories) as categories_total,
            (SELECT COUNT(*) FROM theme_master WHERE status = 'active') as themes_active,
            (SELECT COUNT(*) FROM theme_master WHERE status = 'archived') as themes_archived,
            (SELECT COUNT(DISTINCT theme_type) FROM theme_master WHERE status = 'active') as theme_types
    """)
    
    print(f"  分类表记录: {overall['categories_total']} 条")
    print(f"  活跃题材: {overall['themes_active']} 个")
    print(f"  归档题材: {overall['themes_archived']} 个")
    print(f"  题材类型: {overall['theme_types']} 种")
    
    # 2. 按类型分布
    print(f"\n🎯 活跃题材类型分布：")
    type_dist = await conn.fetch("""
        SELECT theme_type, COUNT(*) as count, AVG(heat_score) as avg_heat
        FROM theme_master
        WHERE status = 'active'
        GROUP BY theme_type
        ORDER BY count DESC
    """)
    
    for dist in type_dist:
        print(f"  • {dist['theme_type']}: {dist['count']} 个 (平均热度: {dist['avg_heat']:.1f})")
    
    # 3. 热门题材TOP20
    print(f"\n🔥 热门题材TOP20：")
    hot_themes = await conn.fetch("""
        SELECT name, level1_category, level2_category, theme_type, heat_score,
               tags->>'keywords' as keywords
        FROM theme_master
        WHERE status = 'active'
        ORDER BY heat_score DESC
        LIMIT 20
    """)
    
    for i, theme in enumerate(hot_themes, 1):
        # 解析关键词
        keywords = []
        if theme['keywords']:
            try:
                keywords = json.loads(theme['keywords'])[:3]
            except:
                keywords = []
        
        kw_str = f" | 关键词: {', '.join(keywords)}" if keywords else ""
        
        print(f"  {i:2d}. {theme['name']} (热度: {theme['heat_score']})")
        print(f"      分类: {theme['level1_category']} → {theme['level2_category']}")
        print(f"      类型: {theme['theme_type']}{kw_str}")
    
    # 4. 中日关系专题验证
    print(f"\n🎯 中日关系专题验证（你的核心需求）：")
    sino_japan = await conn.fetch("""
        SELECT name, description, heat_score, tags->>'keywords' as keywords
        FROM theme_master
        WHERE level2_category = '中日关系' AND status = 'active'
        ORDER BY heat_score DESC
    """)
    
    for theme in sino_japan:
        keywords = []
        if theme['keywords']:
            try:
                keywords = json.loads(theme['keywords'])[:5]
            except:
                keywords = []
        
        print(f"  • {theme['name']} (热度: {theme['heat_score']})")
        print(f"     描述: {theme['description'][:60]}...")
        if keywords:
            print(f"     关键词: {', '.join(keywords)}")
    
    # 5. 标签系统完整性
    print(f"\n🏷️  标签系统完整性检查：")
    tag_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN tags IS NULL OR tags = '{}' THEN 1 END) as no_tags,
            COUNT(CASE WHEN tags->>'keywords' IS NULL OR tags->>'keywords' = '[]' THEN 1 END) as no_keywords,
            COUNT(CASE WHEN tags->>'aliases' IS NULL OR tags->>'aliases' = '[]' THEN 1 END) as no_aliases
        FROM theme_master
        WHERE status = 'active'
    """)
    
    print(f"   总题材数: {tag_stats['total']}")
    print(f"   无标签: {tag_stats['no_tags']}")
    print(f"   无关键词: {tag_stats['no_keywords']}")
    print(f"   无别名: {tag_stats['no_aliases']}")
    
    # 6. 查询性能测试
    print(f"\n⚡ 查询性能测试：")
    
    # 按关键词搜索示例
    test_keywords = ['出口管制', '人工智能', '白酒', '芯片']
    
    for keyword in test_keywords:
        match_count = await conn.fetchval("""
            SELECT COUNT(*)
            FROM theme_master
            WHERE status = 'active'
            AND (
                name ILIKE '%' || $1 || '%'
                OR tags->>'keywords' ILIKE '%' || $1 || '%'
                OR tags->>'aliases' ILIKE '%' || $1 || '%'
            )
        """, keyword)
        
        print(f"  关键词 '{keyword}' 匹配到 {match_count} 个题材")
    
    await conn.close()
    
    print(f"\n{'='*60}")
    print("✅ 题材数据库构建完成！")
    print("   数据库已准备好用于新闻匹配引擎开发")
    print("="*60)

asyncio.run(final_check())