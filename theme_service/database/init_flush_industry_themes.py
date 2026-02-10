# theme_service/database/init_theme_master_final.py
"""
最终版主题库初始化脚本 - 修复所有参数传递问题
"""
import asyncio
import asyncpg
import json
import logging
from datetime import datetime
from typing import List, Dict, Any
import sys
import os

# 基础标准题材配置
STANDARD_THEMES = [
    # 一级分类（10大行业）
    {"id": 1001, "name": "大科技", "category": "行业分类", "description": "科技创新与数字化转型产业", "priority": 1},
    {"id": 1002, "name": "大新能源", "category": "行业分类", "description": "能源转型与碳中和相关产业", "priority": 2},
    {"id": 1003, "name": "大消费", "category": "行业分类", "description": "居民消费与零售服务产业", "priority": 3},
    {"id": 1004, "name": "大医药", "category": "行业分类", "description": "医疗健康与生物医药产业", "priority": 4},
    {"id": 1005, "name": "大周期", "category": "行业分类", "description": "经济周期敏感性基础产业", "priority": 5},
    {"id": 1006, "name": "大制造", "category": "行业分类", "description": "高端制造与工业升级产业", "priority": 6},
    {"id": 1007, "name": "大金融", "category": "行业分类", "description": "金融服务与资本中介产业", "priority": 7},
    {"id": 1008, "name": "国际关系与地缘政治", "category": "国际关系", "description": "国际关系对经济和市场的影响", "priority": 8},
    {"id": 1009, "name": "政策主题", "category": "政策主题", "description": "国家政策驱动的投资主题", "priority": 9},
    {"id": 1010, "name": "公用事业", "category": "行业分类", "description": "公共事业与基础设施产业", "priority": 10},
    
    # 二级分类
    {"id": 2001, "name": "人工智能", "category": "大科技", "description": "人工智能技术及应用全产业链", 
     "keywords": ["AI", "人工智能", "大模型", "机器学习", "深度学习", "AIGC"]},
    {"id": 2002, "name": "半导体", "category": "大科技", "description": "半导体设计、制造、封测全产业链",
     "keywords": ["芯片", "半导体", "集成电路", "IC设计", "晶圆制造", "封装测试"]},
    {"id": 2003, "name": "消费电子", "category": "大科技", "description": "智能硬件与消费电子产品",
     "keywords": ["智能手机", "可穿戴设备", "AR/VR", "智能家居", "TWS耳机", "折叠屏"]},
    {"id": 2004, "name": "5G通信", "category": "大科技", "description": "5G及通信设备与技术",
     "keywords": ["5G", "基站", "光模块", "光纤光缆", "卫星互联网", "物联网"]},
    {"id": 2005, "name": "新能源汽车", "category": "大新能源", "description": "电动汽车及配套产业链",
     "keywords": ["新能源汽车", "电动车", "锂电池", "充电桩", "智能驾驶", "特斯拉"]},
    {"id": 2006, "name": "光伏", "category": "大新能源", "description": "太阳能光伏发电全产业链",
     "keywords": ["光伏", "太阳能", "硅料", "硅片", "电池片", "组件", "逆变器"]},
    {"id": 2007, "name": "中日关系", "category": "国际关系与地缘政治", "description": "中日双边关系及地缘政治影响",
     "keywords": ["中日关系", "日本", "靖国神社", "出口管制", "外交施压", "东海", "钓鱼岛"],
     "merge_keywords": ["对日两用物项出口管制", "日政要参拜神社", "中日关系紧张升级", "对日反制措施", "对日外交施压", "中日地缘政治紧张"]},
    {"id": 2008, "name": "中美关系", "category": "国际关系与地缘政治", "description": "中美经贸与科技关系",
     "keywords": ["中美关系", "贸易摩擦", "技术制裁", "芯片禁令", "实体清单", "关税"]},
]

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class FinalThemeInitializer:
    """最终版主题库初始化器"""
    
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
    
    async def clear_existing_data(self):
        """清空现有数据"""
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("DELETE FROM theme_master")
                logger.info("🗑️  已清空现有主题数据")
                return True
            except Exception as e:
                logger.error(f"❌ 清空数据失败: {e}")
                return False
    
    async def insert_standard_themes(self):
        """插入标准题材（使用INSERT ONLY，不更新）"""
        logger.info("🚀 开始插入标准题材库...")
        
        inserted = 0
        skipped = 0
        
        async with self.pool.acquire() as conn:
            for theme in STANDARD_THEMES:
                try:
                    # 检查是否已存在
                    existing = await conn.fetchval(
                        "SELECT id FROM theme_master WHERE name = $1",
                        theme["name"]
                    )
                    
                    if existing:
                        logger.debug(f"⚠️  跳过已存在的主题: {theme['name']}")
                        skipped += 1
                        continue
                    
                    # 计算热度
                    heat_score = theme.get("priority", 5) * 15 + 50
                    
                    # 插入新记录
                    await conn.execute("""
                        INSERT INTO theme_master (
                            id, name, category, description, keywords, merge_keywords,
                            is_standard_theme, standard_name, heat_score, 
                            discovery_source, discovery_confidence, status,
                            created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    """, (
                        theme.get("id"),
                        theme["name"],
                        theme.get("category"),
                        theme.get("description"),
                        theme.get("keywords", []),
                        theme.get("merge_keywords", []),
                        True,
                        theme.get("name"),
                        heat_score,
                        "standard_library",
                        0.95,
                        "active",
                        datetime.now(),
                        datetime.now()
                    ))
                    
                    logger.debug(f"  ➕ 插入: {theme['name']}")
                    inserted += 1
                    
                except Exception as e:
                    logger.error(f"❌ 插入标准题材 {theme['name']} 失败: {e}")
        
        logger.info(f"✅ 标准题材插入完成: 新增{inserted}个, 跳过{skipped}个")
        return inserted
    
    async def load_flush_themes_simple(self, data_file: str):
        """简化版加载同花顺主题"""
        if not os.path.exists(data_file):
            logger.warning(f"⚠️  文件不存在: {data_file}")
            return 0
        
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                themes = json.load(f)
            logger.info(f"📂 加载了 {len(themes)} 个同花顺主题")
        except Exception as e:
            logger.error(f"❌ 加载数据文件失败: {e}")
            return 0
        
        inserted = 0
        skipped = 0
        
        async with self.pool.acquire() as conn:
            for theme in themes:
                try:
                    # 检查是否已存在
                    existing = await conn.fetchval(
                        "SELECT id FROM theme_master WHERE name = $1 AND is_flush_industry = TRUE",
                        theme['name']
                    )
                    
                    if existing:
                        logger.debug(f"⚠️  跳过已存在的同花顺主题: {theme['name']}")
                        skipped += 1
                        continue
                    
                    # 准备参数
                    category = theme.get('category', '')
                    sub_category = theme.get('sub_category', '')
                    description = theme.get('description', '')
                    keywords = theme.get('keywords', [])
                    heat_score = theme.get('heat_score', 70)
                    classification_code = theme.get('classification_code')
                    classification_level = theme.get('classification_level')
                    parent_industry_code = theme.get('parent_industry_code')
                    
                    # 插入新记录（简化参数）
                    await conn.execute("""
                        INSERT INTO theme_master (
                            name, category, sub_category, description, keywords,
                            discovery_source, discovery_confidence, heat_score,
                            lifecycle_stage, status, classification_code,
                            classification_level, parent_industry_code,
                            is_flush_industry, is_industry_standard,
                            created_at, updated_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
                    """, (
                        theme['name'],
                        category,
                        sub_category,
                        description,
                        keywords,
                        theme.get('discovery_source', 'flush_industry'),
                        theme.get('discovery_confidence', 0.9),
                        heat_score,
                        theme.get('lifecycle_stage', 'stable'),
                        theme.get('status', 'active'),
                        classification_code,
                        classification_level,
                        parent_industry_code,
                        True,
                        True,
                        datetime.now(),
                        datetime.now()
                    ))
                    
                    logger.debug(f"  ➕ 同花顺: {theme['name']}")
                    inserted += 1
                    
                except Exception as e:
                    logger.error(f"❌ 处理同花顺主题 {theme.get('name', 'unknown')} 失败: {e}")
        
        logger.info(f"✅ 同花顺主题插入完成: 新增{inserted}个, 跳过{skipped}个")
        return inserted
    
    async def verify_data(self):
        """验证数据"""
        async with self.pool.acquire() as conn:
            try:
                print("\n" + "="*60)
                print("📊 数据验证报告")
                print("="*60)
                
                # 总体统计
                stats = await conn.fetchrow("""
                    SELECT 
                        COUNT(*) as total,
                        COUNT(CASE WHEN is_standard_theme = TRUE THEN 1 END) as standard_count,
                        COUNT(CASE WHEN is_flush_industry = TRUE THEN 1 END) as flush_count,
                        AVG(heat_score) as avg_heat
                    FROM theme_master
                """)
                
                print(f"🔢 总体统计:")
                print(f"   主题总数: {stats['total']} 个")
                print(f"   标准题材: {stats['standard_count']} 个")
                print(f"   同花顺主题: {stats['flush_count']} 个")
                print(f"   平均热度: {stats['avg_heat']:.1f}")
                
                # 显示各类主题
                if stats['standard_count'] > 0:
                    standard_themes = await conn.fetch("""
                        SELECT name, heat_score, category 
                        FROM theme_master 
                        WHERE is_standard_theme = TRUE 
                        ORDER BY heat_score DESC 
                        LIMIT 5
                    """)
                    
                    print(f"\n🎯 标准题材TOP5:")
                    for i, theme in enumerate(standard_themes, 1):
                        print(f"   {i:2d}. {theme['name']:20s} - 热度: {theme['heat_score']:3d}, 分类: {theme['category']}")
                
                if stats['flush_count'] > 0:
                    flush_themes = await conn.fetch("""
                        SELECT name, heat_score, classification_level 
                        FROM theme_master 
                        WHERE is_flush_industry = TRUE 
                        ORDER BY heat_score DESC 
                        LIMIT 5
                    """)
                    
                    print(f"\n📈 同花顺主题TOP5:")
                    for i, theme in enumerate(flush_themes, 1):
                        print(f"   {i:2d}. {theme['name']:20s} - 热度: {theme['heat_score']:3d}, 级别: {theme['classification_level']}")
                
                print("\n✅ 数据验证完成")
                print("="*60)
                
                return True
                
            except Exception as e:
                logger.error(f"❌ 验证失败: {e}")
                return False

async def main():
    """主函数"""
    print("="*60)
    print("🚀 最终版主题库初始化")
    print("="*60)
    
    # 确认操作
    confirm = input("⚠️  此操作将清空现有数据并重新初始化。是否继续？(y/N): ")
    if confirm.lower() != 'y':
        print("⏹️  操作取消")
        return
    
    initializer = FinalThemeInitializer()
    
    try:
        # 1. 连接数据库
        if not await initializer.connect():
            return
        
        # 2. 清空现有数据
        if not await initializer.clear_existing_data():
            return
        
        # 3. 插入标准题材
        std_count = await initializer.insert_standard_themes()
        
        # 4. 加载同花顺主题
        data_file = "evaluate_service/data/flush_theme_master_data.json"
        flush_count = await initializer.load_flush_themes_simple(data_file)
        
        # 5. 验证数据
        await initializer.verify_data()
        
        print(f"\n🎉 初始化完成！")
        print(f"   标准题材: {std_count} 个")
        print(f"   同花顺主题: {flush_count} 个")
        print(f"   总计: {std_count + flush_count} 个主题")
        
        if flush_count == 0:
            print("\n⚠️  同花顺主题导入失败，请检查文件路径:")
            print(f"   当前路径: {data_file}")
            print(f"   绝对路径: {os.path.abspath(data_file)}")
            print(f"   文件存在: {os.path.exists(data_file)}")
        
    except KeyboardInterrupt:
        print("\n⏹️  用户中断")
    except Exception as e:
        logger.error(f"❌ 初始化异常: {e}")
    finally:
        await initializer.close()

if __name__ == "__main__":
    asyncio.run(main())