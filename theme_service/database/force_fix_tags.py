# force_fix_tags.py
import asyncio
import asyncpg
import json
import re

async def force_fix_all_tags():
    """强制修复所有题材的tags字段"""
    DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
    
    conn = await asyncpg.connect(DATABASE_URL)
    
    print("🔧 强制修复tags字段")
    print("="*60)
    
    try:
        # 1. 获取所有需要修复的题材
        themes = await conn.fetch("""
            SELECT id, name, code, theme_type, level1_category, level2_category,
                   heat_score, tags
            FROM theme_master
            WHERE status = 'active'
            ORDER BY heat_score DESC
        """)
        
        print(f"📋 需要处理的题材: {len(themes)} 个")
        
        fixed_count = 0
        error_count = 0
        
        for theme in themes:
            try:
                theme_id = theme['id']
                theme_name = theme['name']
                theme_type = theme['theme_type']
                
                # 2. 根据不同类型生成不同的tags
                tags_data = generate_tags_for_theme(
                    name=theme_name,
                    theme_type=theme_type,
                    level1=theme['level1_category'],
                    level2=theme['level2_category'],
                    heat_score=theme['heat_score']
                )
                
                # 3. 更新数据库
                await conn.execute("""
                    UPDATE theme_master 
                    SET tags = $1, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $2
                """, json.dumps(tags_data, ensure_ascii=False), theme_id)
                
                fixed_count += 1
                
                # 显示进度
                if fixed_count % 50 == 0:
                    print(f"  🔄 已处理 {fixed_count}/{len(themes)} 个题材")
                    
            except Exception as e:
                error_count += 1
                print(f"  ❌ 处理失败 {theme['name']}: {e}")
        
        print(f"\n✅ 修复完成！")
        print(f"   成功修复: {fixed_count} 个题材")
        print(f"   失败: {error_count} 个")
        
        # 4. 验证修复结果
        print(f"\n🔍 验证修复结果：")
        verify_stats = await conn.fetchrow("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN tags IS NULL OR tags = '{}' THEN 1 END) as empty_tags,
                COUNT(CASE WHEN tags->>'keywords' IS NOT NULL 
                          AND tags->>'keywords' != '[]' THEN 1 END) as has_keywords,
                AVG(jsonb_array_length(tags->'keywords')) as avg_keywords
            FROM theme_master
            WHERE status = 'active'
        """)
        
        print(f"   总题材数: {verify_stats['total']}")
        print(f"   空tags: {verify_stats['empty_tags']}")
        print(f"   有关键词: {verify_stats['has_keywords']}")
        print(f"   平均关键词数: {verify_stats['avg_keywords']:.1f}")
        
        # 5. 显示示例
        print(f"\n📋 修复后示例：")
        examples = await conn.fetch("""
            SELECT name, tags->>'keywords' as keywords, theme_type
            FROM theme_master
            WHERE status = 'active'
            AND jsonb_array_length(tags->'keywords') > 0
            ORDER BY heat_score DESC
            LIMIT 5
        """)
        
        for ex in examples:
            keywords = json.loads(ex['keywords'])
            print(f"  • {ex['name']} ({ex['theme_type']})")
            print(f"     关键词: {', '.join(keywords[:5])}")
        
        return True
        
    except Exception as e:
        print(f"❌ 修复失败: {e}")
        return False
    finally:
        await conn.close()

def generate_tags_for_theme(name: str, theme_type: str, level1: str, 
                           level2: str, heat_score: int) -> dict:
    """为题材生成智能标签"""
    
    # 基础关键词（从名称中提取）
    base_keywords = extract_keywords_from_name(name)
    
    # 根据类型添加特定关键词
    if theme_type == 'relation':
        tags = {
            "keywords": base_keywords + ["外交", "国际关系", "地缘政治"],
            "aliases": [name, f"{name}概念", f"{name}题材"],
            "merge_candidates": [],
            "industries": ["外交", "国际贸易", "国家安全"],
            "concepts": ["国际关系", "外交政策", "国家安全"],
            "heat_level": "high" if heat_score > 80 else "medium",
            "source": "financial_categories",
            "version": "2.0"
        }
    elif theme_type == 'concept':
        tags = {
            "keywords": base_keywords + ["人工智能", "科技创新", "数字经济"],
            "aliases": [name, f"{name}板块", f"{name}主题"],
            "merge_candidates": [],
            "industries": ["科技", "互联网", "软件"],
            "concepts": ["技术创新", "产业升级", "数字化转型"],
            "heat_level": "high" if heat_score > 85 else "medium",
            "source": "custom",
            "version": "2.0"
        }
    else:  # investment类型（申万行业）
        # 为申万行业生成更丰富的关键词
        industry_keywords = generate_industry_keywords(name, level1, level2)
        
        tags = {
            "keywords": base_keywords + industry_keywords,
            "aliases": [name, f"{name}板块", f"{name}行业"],
            "merge_candidates": [],
            "industries": [level2, level1],
            "concepts": ["产业投资", "行业轮动", "经济周期"],
            "heat_level": "high" if heat_score > 85 else "medium",
            "source": "shenwan",
            "industry_code": name,  # 保留行业代码
            "version": "2.0"
        }
    
    return tags

def extract_keywords_from_name(name: str) -> list:
    """从题材名称中提取关键词"""
    # 移除罗马数字和特殊字符
    cleaned = re.sub(r'[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩⅪⅫ]', '', name)
    cleaned = re.sub(r'[Ⅰ-Ⅻ]', '', cleaned)
    
    # 分割关键词
    keywords = []
    
    # 常见分隔符
    separators = ['、', '，', ',', ' ', '及', '与']
    
    for sep in separators:
        if sep in cleaned:
            parts = [p.strip() for p in cleaned.split(sep) if p.strip()]
            keywords.extend(parts)
            break
    else:
        # 没有分隔符，尝试按长度分割
        if len(cleaned) <= 6:
            keywords = [cleaned]
        else:
            # 尝试找到自然分割点
            keywords = [cleaned]
    
    # 添加常见后缀变体
    enhanced = []
    for kw in keywords:
        enhanced.append(kw)
        if not kw.endswith('概念'):
            enhanced.append(f"{kw}概念")
        if not kw.endswith('题材'):
            enhanced.append(f"{kw}题材")
        if not kw.endswith('板块'):
            enhanced.append(f"{kw}板块")
    
    return list(set(enhanced))  # 去重

def generate_industry_keywords(name: str, level1: str, level2: str) -> list:
    """为行业生成相关关键词"""
    keywords = []
    
    # 一级行业关键词映射
    level1_keywords = {
        '计算机': ['科技', '软件', '互联网', '数字化', '信息技术'],
        '电子': ['芯片', '半导体', '集成电路', '消费电子', '元器件'],
        '医药生物': ['医疗', '健康', '制药', '生物技术', '医疗器械'],
        '电力设备': ['新能源', '电力', '电池', '光伏', '储能'],
        '食品饮料': ['消费', '食品', '饮料', '餐饮', '快消品'],
        '汽车': ['汽车', '新能源汽车', '零部件', '自动驾驶', '智能汽车'],
        '传媒': ['媒体', '娱乐', '文化', '游戏', '广告'],
        '基础化工': ['化工', '材料', '化学品', '新材料', '精细化工'],
        '机械设备': ['机械', '设备', '制造', '工业', '自动化'],
        '国防军工': ['军工', '国防', '航空航天', '武器装备', '国家安全'],
        '通信': ['通信', '5G', '网络', '物联网', '通信设备'],
        '银行': ['银行', '金融', '信贷', '银行业', '金融服务'],
        '非银金融': ['证券', '保险', '信托', '金融', '投资'],
        '房地产': ['地产', '房地产', '物业', '开发', '建筑工程'],
        '农林牧渔': ['农业', '林业', '畜牧业', '渔业', '乡村振兴'],
        '有色金属': ['金属', '矿产', '资源', '有色', '矿业'],
        '煤炭': ['煤炭', '能源', '采矿', '煤矿', '传统能源'],
        '钢铁': ['钢铁', '金属', '冶金', '钢材', '重工业'],
        '建筑装饰': ['建筑', '装饰', '装修', '建材', '建筑工程'],
        '交通运输': ['交通', '运输', '物流', '航运', '港口'],
        '公用事业': ['公用事业', '电力', '燃气', '水务', '基础设施'],
        '环保': ['环保', '环境', '污染治理', '节能', '绿色发展'],
        '商贸零售': ['零售', '商业', '贸易', '百货', '电商'],
        '社会服务': ['服务', '教育', '旅游', '酒店', '社会服务'],
        '轻工制造': ['轻工', '制造', '消费品', '家居', '包装'],
        '石油石化': ['石油', '石化', '能源', '化工', '油气'],
        '美容护理': ['美容', '护理', '化妆品', '个人护理', '日化'],
        '家用电器': ['家电', '电器', '电子产品', '智能家居', '消费电子'],
        '综合': ['综合', '多元化', '投资', '控股', '集团']
    }
    
    # 添加一级行业关键词
    if level1 in level1_keywords:
        keywords.extend(level1_keywords[level1])
    
    # 添加二级行业关键词
    keywords.append(level2)
    
    # 根据名称添加特定关键词
    if '芯片' in name or '半导体' in name:
        keywords.extend(['集成电路', '微电子', '处理器', '存储芯片'])
    elif '电池' in name:
        keywords.extend(['锂电池', '动力电池', '储能', '新能源'])
    elif '光伏' in name:
        keywords.extend(['太阳能', '新能源', '清洁能源', '可再生能源'])
    elif '软件' in name:
        keywords.extend(['程序', '系统', '应用', '开发'])
    elif '人工智能' in name or 'AI' in name:
        keywords.extend(['机器学习', '深度学习', '智能算法', '机器人'])
    elif '医药' in name or '医疗' in name:
        keywords.extend(['健康', '治疗', '药品', '医院'])
    elif '白酒' in name:
        keywords.extend(['酒类', '酿酒', '消费', '高端消费'])
    elif '证券' in name or '券商' in name:
        keywords.extend(['股票', '经纪', '投行', '资本市场'])
    elif '保险' in name:
        keywords.extend(['寿险', '财险', '风险管理', '金融保障'])
    
    return list(set(keywords))  # 去重

async def main():
    print("="*60)
    print("🔧 强制修复tags字段（完整版）")
    print("="*60)
    
    success = await force_fix_all_tags()
    
    if success:
        print(f"\n🎉 tags字段修复完成！")
        print(f"   现在所有题材都有完整的智能标签系统")
        print(f"\n🚀 下一步：重新运行新闻匹配测试")
    else:
        print(f"\n❌ 修复失败")

if __name__ == "__main__":
    asyncio.run(main())