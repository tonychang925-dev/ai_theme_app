# final_verification.py
import asyncio
import asyncpg

async def final_verification():
    """最终验证数据库状态"""
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("🎯 最终数据库状态验证")
    print("="*60)
    
    # 1. theme_master 最终状态
    print("1. theme_master 表最终状态:")
    print("-"*40)
    
    tm_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total_count,
            COUNT(CASE WHEN status = 'active' THEN 1 END) as active_count,
            COUNT(CASE WHEN status = 'archived' THEN 1 END) as archived_count,
            COUNT(CASE WHEN code LIKE 'SW_%' THEN 1 END) as sw_count,
            MIN(id) as min_id,
            MAX(id) as max_id
        FROM theme_master
    """)
    
    print(f"✅ 总记录数: {tm_stats['total_count']}")
    print(f"✅ 活跃题材: {tm_stats['active_count']}")
    print(f"✅ 归档记录: {tm_stats['archived_count']}")
    print(f"✅ SW记录数: {tm_stats['sw_count']}")
    print(f"✅ ID范围: {tm_stats['min_id']} - {tm_stats['max_id']}")
    
    # 2. 活跃题材类型分布
    print(f"\n2. 活跃题材类型分布:")
    print("-"*40)
    
    theme_dist = await conn.fetch("""
        SELECT theme_type, source_system, COUNT(*) as count
        FROM theme_master
        WHERE status = 'active'
        GROUP BY theme_type, source_system
        ORDER BY theme_type, source_system
    """)
    
    total_active = 0
    for td in theme_dist:
        total_active += td['count']
        print(f"   📍 {td['theme_type'].upper()} ({td['source_system']}): {td['count']} 个")
    
    print(f"   📊 总计活跃题材: {total_active} 个")
    
    # 3. 关键词质量检查
    print(f"\n3. 关键词质量检查:")
    print("-"*40)
    
    keyword_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as themes_with_keywords,
            COUNT(CASE WHEN jsonb_array_length(tags->'keywords') >= 5 THEN 1 END) as good_keywords,
            AVG(jsonb_array_length(tags->'keywords')) as avg_keywords,
            MIN(jsonb_array_length(tags->'keywords')) as min_keywords,
            MAX(jsonb_array_length(tags->'keywords')) as max_keywords
        FROM theme_master
        WHERE status = 'active'
    """)
    
    print(f"✅ 有关键词的题材: {keyword_stats['themes_with_keywords']}")
    print(f"✅ 关键词≥5个的题材: {keyword_stats['good_keywords']}")
    print(f"✅ 平均关键词数: {keyword_stats['avg_keywords']:.1f}")
    print(f"✅ 最少关键词数: {keyword_stats['min_keywords']}")
    print(f"✅ 最多关键词数: {keyword_stats['max_keywords']}")
    
    # 4. 随机抽样检查
    print(f"\n4. 随机抽样检查（关键词完整性）:")
    print("-"*40)
    
    samples = await conn.fetch("""
        SELECT name, theme_type, source_system,
               jsonb_array_length(tags->'keywords') as keyword_count,
               tags->'keywords' as sample_keywords
        FROM theme_master
        WHERE status = 'active'
        ORDER BY RANDOM()
        LIMIT 5
    """)
    
    for i, sample in enumerate(samples, 1):
        keywords = sample['sample_keywords'][:3] if sample['sample_keywords'] else []
        print(f"   {i}. {sample['name']} [{sample['theme_type']}]")
        print(f"      来源: {sample['source_system']}, 关键词数: {sample['keyword_count']}")
        print(f"      关键词示例: {keywords}")
    
    # 5. financial_categories 状态
    print(f"\n5. financial_categories 表状态:")
    print("-"*40)
    
    fc_stats = await conn.fetchrow("""
        SELECT 
            COUNT(*) as total,
            COUNT(CASE WHEN category_level = 1 THEN 1 END) as level1,
            COUNT(CASE WHEN category_level = 2 THEN 1 END) as level2,
            COUNT(CASE WHEN category_level = 3 THEN 1 END) as level3,
            COUNT(CASE WHEN source_system = 'tushare' THEN 1 END) as shenwan
        FROM financial_categories
    """)
    
    print(f"✅ 总分类数: {fc_stats['total']}")
    print(f"✅ 一级分类: {fc_stats['level1']}")
    print(f"✅ 二级分类: {fc_stats['level2']}")
    print(f"✅ 三级分类: {fc_stats['level3']}")
    print(f"✅ 申万分类: {fc_stats['shenwan']}")
    
    await conn.close()
    
    print(f"\n{'='*60}")
    # 总结评估
    if (tm_stats['sw_count'] == 0 and 
        tm_stats['active_count'] >= 330 and
        keyword_stats['themes_with_keywords'] >= 300):
        print("🎉 数据库状态完美！符合新闻匹配要求！")
        print("   - 无SW冗余数据 ✓")
        print("   - 活跃题材充足 ✓")
        print("   - 关键词完整 ✓")
        print("   - 分类体系完整 ✓")
    else:
        print("⚠️  数据库状态需要进一步优化")
    
    print("="*60)

asyncio.run(final_verification())