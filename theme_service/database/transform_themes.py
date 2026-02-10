# transform_themes.py
"""
将申万行业转换为新闻友好的投资题材
"""
import asyncio
import asyncpg
import json
from typing import Dict, List

async def transform_shenwan_to_themes():
    """转换申万三级行业为投资题材"""
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    try:
        print("🔄 开始转换申万行业为投资题材...")
        
        # 1. 定义行业到题材的映射规则
        industry_to_theme_map = {
            # 农林牧渔
            "种子": ["种业振兴", "农业芯片", "生物育种"],
            "粮食种植": ["粮食安全", "农业现代化", "乡村振兴"],
            "水产养殖": ["渔业发展", "海洋经济", "水产种业"],
            
            # 食品饮料  
            "白酒": ["白酒消费", "高端白酒", "酒类投资"],
            "调味发酵品": ["调味品", "厨房经济", "食品消费"],
            
            # 计算机
            "软件开发": ["信创", "国产软件", "企业数字化", "云计算"],
            "IT服务": ["数字化转型", "IT外包", "技术服务"],
            
            # 电子
            "半导体": ["芯片国产化", "半导体设备", "集成电路"],
            "消费电子": ["智能手机", "智能穿戴", "消费电子创新"],
            
            # 医药
            "化学制药": ["创新药", "仿制药", "医药研发"],
            "中药": ["中药现代化", "中医药传承", "中药创新"],
            
            # 新能源
            "光伏设备": ["光伏发电", "太阳能", "清洁能源"],
            "电池": ["锂电池", "储能", "新能源车电池"],
            
            # 汽车
            "乘用车": ["新能源汽车", "智能汽车", "汽车消费"],
            "汽车零部件": ["汽车零配件", "汽车供应链", "汽车电子"],
        }
        
        # 2. 为每个申万三级行业创建对应的投资题材
        shenwan_themes = await conn.fetch("""
            SELECT tm.id, tm.name as industry_name, tm.code as industry_code,
                   tm.level1_category, tm.level2_category, tm.level3_category,
                   tm.category1_code, tm.category2_code, tm.category3_code,
                   fc.keywords as industry_keywords
            FROM theme_master tm
            LEFT JOIN financial_categories fc ON tm.category3_code = fc.category_code
            WHERE tm.source_system = 'shenwan'
            ORDER BY tm.level1_category, tm.level2_category, tm.name
        """)
        
        print(f"📋 处理 {len(shenwan_themes)} 个申万行业...")
        
        transformed_count = 0
        for theme in shenwan_themes:
            industry_name = theme['industry_name']
            
            # 查找对应的投资题材名称
            investment_themes = industry_to_theme_map.get(industry_name, [industry_name])
            
            # 为每个投资题材创建记录
            for investment_theme in investment_themes[:1]:  # 暂时先创建一个主要题材
                # 生成新的题材代码
                new_code = f"INVEST_{theme['industry_code']}"
                
                # 准备智能标签
                tags = {
                    "source_industry": industry_name,
                    "source_industry_code": theme['industry_code'],
                    "keywords": [],
                    "aliases": [],
                    "related_concepts": investment_themes,
                    "invest_themes": investment_themes,
                    "industry_keywords": theme['industry_keywords'] or [],
                    "transformed_at": "2024-01-16"
                }
                
                # 如果是映射表中的行业，添加更多关键词
                if industry_name in industry_to_theme_map:
                    tags["keywords"] = industry_to_theme_map[industry_name]
                    tags["aliases"] = [industry_name] + industry_to_theme_map[industry_name]
                
                # 计算热度（基于行业特性）
                heat_score = calculate_theme_heat(investment_theme, theme['level1_category'])
                
                # 插入新的投资题材记录
                await conn.execute("""
                    INSERT INTO theme_master 
                    (name, code, description, level1_category, level2_category, level3_category,
                     category_path, category1_code, category2_code, category3_code,
                     tags, theme_type, heat_score, source_system, source_id, status)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
                    ON CONFLICT (code) DO UPDATE SET
                    name = EXCLUDED.name,
                    tags = EXCLUDED.tags,
                    heat_score = EXCLUDED.heat_score,
                    updated_at = CURRENT_TIMESTAMP
                """,
                    investment_theme,                    # name
                    new_code,                           # code
                    f"投资题材：{investment_theme}（源于申万行业：{industry_name}）",  # description
                    theme['level1_category'],           # level1_category
                    theme['level2_category'],           # level2_category
                    investment_theme,                   # level3_category（用投资题材名）
                    [theme['level1_category'], theme['level2_category'], investment_theme],  # path
                    theme['category1_code'],            # category1_code
                    theme['category2_code'],            # category2_code
                    theme['category3_code'],            # category3_code
                    json.dumps(tags, ensure_ascii=False),  # tags
                    'investment',                       # theme_type（新的类型）
                    heat_score,                         # heat_score
                    'transformed',                      # source_system
                    theme['industry_code'],             # source_id
                    'active'                            # status
                )
                
                transformed_count += 1
        
        # 3. 禁用原始的申万行业记录（保留但不用于匹配）
        await conn.execute("""
            UPDATE theme_master 
            SET status = 'archived'
            WHERE source_system = 'shenwan' AND theme_type = 'industry'
        """)
        
        print(f"\n✅ 转换完成！")
        print(f"   创建了 {transformed_count} 个投资题材")
        print(f"   归档了 {len(shenwan_themes)} 个原始申万行业记录")
        
        # 4. 验证转换结果
        print(f"\n🔍 转换后验证：")
        
        # 投资题材统计
        investment_stats = await conn.fetchrow("""
            SELECT COUNT(*) as total, AVG(heat_score) as avg_heat,
                   COUNT(DISTINCT theme_type) as types
            FROM theme_master
            WHERE status = 'active'
        """)
        
        print(f"   活跃题材总数: {investment_stats['total']}")
        print(f"   平均热度: {investment_stats['avg_heat']:.1f}")
        print(f"   题材类型数: {investment_stats['types']}")
        
        # 显示示例
        print(f"\n📋 转换后的投资题材示例：")
        examples = await conn.fetch("""
            SELECT name, level1_category, level2_category, theme_type, heat_score, 
                   tags->>'keywords' as keywords
            FROM theme_master
            WHERE status = 'active' AND theme_type = 'investment'
            ORDER BY heat_score DESC
            LIMIT 8
        """)
        
        for i, ex in enumerate(examples, 1):
            keywords = json.loads(ex['keywords']) if ex['keywords'] else []
            kw_str = ', '.join(keywords[:3]) if keywords else ''
            print(f"  {i}. {ex['name']}")
            print(f"     分类: {ex['level1_category']} → {ex['level2_category']}")
            print(f"     类型: {ex['theme_type']}, 热度: {ex['heat_score']}")
            if kw_str:
                print(f"     关键词: {kw_str}")
        
        return True
        
    finally:
        await conn.close()

def calculate_theme_heat(theme_name: str, level1_category: str) -> int:
    """根据题材名称和行业计算热度"""
    base_score = 65
    
    # 根据一级行业调整
    industry_boost = {
        '计算机': 15,
        '电子': 12,
        '医药生物': 10,
        '电力设备': 10,
        '汽车': 8,
        '食品饮料': 8,
        '国防军工': 5,
        '农林牧渔': 3,
        '煤炭': 2,
        '钢铁': 2,
        '建筑材料': 2,
        '建筑装饰': 2,
        '房地产': 1,
        '银行': 1,
        '非银金融': 3,
        '传媒': 8,
        '通信': 8,
        '美容护理': 5,
        '家用电器': 5,
        '机械设备': 5,
        '石油石化': 2,
        '基础化工': 5,
        '交通运输': 3,
        '公用事业': 2,
        '环保': 3,
        '商贸零售': 4,
        '社会服务': 4,
        '轻工制造': 4,
        '有色金属': 5,
        '纺织服饰': 3,
        '综合': 2
    }
    
    # 根据题材关键词调整
    hot_keywords = {
        'AI': 20, '人工智能': 20, '芯片': 18, '半导体': 18,
        '新能源': 15, '光伏': 15, '电池': 15, '储能': 15,
        '创新药': 12, '生物医药': 12, '中药': 10,
        '白酒': 12, '消费': 10,
        '信创': 15, '国产软件': 12, '云计算': 10,
        '智能驾驶': 15, '新能源汽车': 15,
        '机器人': 12, '智能制造': 10,
        '数据要素': 15, '数字经济': 12,
        '一带一路': 8, '中特估': 10
    }
    
    # 计算总热度
    score = base_score
    
    # 行业加成
    score += industry_boost.get(level1_category, 5)
    
    # 关键词加成
    for keyword, boost in hot_keywords.items():
        if keyword in theme_name:
            score += boost
            break
    
    return min(score, 95)  # 上限95

async def main():
    print("="*60)
    print("🔄 申万行业 → 投资题材转换")
    print("="*60)
    print("将技术性的申万三级行业转换为新闻友好的投资题材")
    
    success = await transform_shenwan_to_themes()
    
    if success:
        print(f"\n🎉 转换完成！现在可以用于新闻匹配了")
        print(f"   投资题材已具备完整的关键词标签和合理的热度分布")
    else:
        print(f"\n❌ 转换失败")

if __name__ == "__main__":
    asyncio.run(main())