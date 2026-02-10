#!/usr/bin/env python3
"""
手动处理所有未处理事件
"""
import asyncio
import asyncpg
from datetime import datetime
import sys

async def manual_process():
    print("🚀 手动处理所有未处理事件")
    print("="*60)
    
    try:
        # 连接数据库
        conn = await asyncpg.connect("postgresql://postgres:zxbzj~925@localhost/stock_data")
        
        # 1. 获取未处理事件
        print("\n1. 🔍 查找未处理事件...")
        
        unprocessed = await conn.fetch('''
            SELECT 
                ne.id,
                COALESCE(ne.title, nr.title) as title,
                ne.summary,
                ne.event_type,
                nr.content
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            WHERE ne.id NOT IN (SELECT DISTINCT event_id FROM event_theme_map)
            ORDER BY ne.id
        ''')
        
        if not unprocessed:
            print("✅ 所有事件都已处理完成！")
            return
        
        print(f"📥 发现 {len(unprocessed)} 个未处理事件")
        
        # 2. 简化的主题关键词映射
        theme_keywords = {
            "人工智能": ["ai", "人工智能", "大模型", "gpt", "机器学习"],
            "新能源汽车": ["新能源", "电动车", "特斯拉", "电池", "充电"],
            "半导体芯片": ["芯片", "半导体", "集成电路"],
            "医药医疗": ["医药", "医疗", "医院", "疫苗"],
            "消费电子": ["苹果", "华为", "小米", "手机"],
            "数字经济": ["数据", "数字", "云计算", "大数据"],
            "金融": ["银行", "保险", "证券", "金融"],
            "军工国防": ["军工", "国防", "军事"],
            "新能源发电": ["光伏", "风电", "储能"],
            "传媒娱乐": ["游戏", "传媒", "影视"],
            "物流": ["物流", "快递", "运输"],
            "消费": ["消费", "零售", "电商"],
            "旅游": ["旅游", "文旅", "酒店"],
            "基建": ["基建", "基础设施", "铁路"],
            "房地产": ["房地产", "地产", "房价"],
        }
        
        # 3. 处理每个事件
        print("\n2. 🔄 开始处理事件...")
        processed_count = 0
        themes_created = 0
        mappings_created = 0
        
        for event in unprocessed:
            event_id = event['id']
            title = event['title'] or "无标题"
            summary = event['summary'] or ""
            content = (title + " " + summary).lower()
            
            print(f"\n处理事件 #{event_id}: {title[:50]}...")
            
            # 分析主题
            themes_found = []
            for theme_name, keywords in theme_keywords.items():
                for keyword in keywords:
                    if keyword in content:
                        themes_found.append(theme_name)
                        break
            
            if themes_found:
                print(f"   发现主题: {', '.join(themes_found)}")
                
                for theme_name in themes_found:
                    # 获取或创建主题
                    theme = await conn.fetchrow(
                        "SELECT id FROM theme_master WHERE name = $1",
                        theme_name
                    )
                    
                    if theme:
                        theme_id = theme['id']
                    else:
                        # 创建新主题
                        result = await conn.fetchrow('''
                            INSERT INTO theme_master 
                            (name, keywords, status, discovery_source, discovery_confidence)
                            VALUES ($1, $2, $3, $4, $5)
                            RETURNING id
                        ''',
                            theme_name,
                            [theme_name],
                            'active',
                            'manual_process',
                            0.7
                        )
                        theme_id = result['id']
                        themes_created += 1
                        print(f"   创建新主题: {theme_name} (ID: {theme_id})")
                    
                    # 创建映射
                    await conn.execute('''
                        INSERT INTO event_theme_map 
                        (event_id, theme_id, confidence, confidence_level, confidence_weight)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (event_id, theme_id) DO NOTHING
                    ''',
                        event_id,
                        theme_id,
                        0.7,
                        'medium',
                        60
                    )
                    mappings_created += 1
                
                print(f"   ✅ 关联 {len(themes_found)} 个主题")
            else:
                print(f"   ⏳ 未发现相关主题")
            
            processed_count += 1
            
            # 显示进度
            if processed_count % 5 == 0 or processed_count == len(unprocessed):
                print(f"\n📊 进度: {processed_count}/{len(unprocessed)} ({(processed_count/len(unprocessed)*100):.1f}%)")
        
        # 4. 显示结果
        print("\n" + "="*60)
        print("🎉 手动处理完成！")
        print("="*60)
        
        print(f"\n📊 处理结果:")
        print(f"   处理事件: {processed_count} 个")
        print(f"   创建主题: {themes_created} 个")
        print(f"   创建映射: {mappings_created} 个")
        
        # 5. 更新统计
        total_events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        processed_events = await conn.fetchval("SELECT COUNT(DISTINCT event_id) FROM event_theme_map")
        
        print(f"\n📈 当前进度:")
        print(f"   总事件数: {total_events}")
        print(f"   已处理: {processed_events}")
        print(f"   完成率: {(processed_events/total_events*100 if total_events>0 else 0):.1f}%")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(manual_process())
