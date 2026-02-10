#!/usr/bin/env python3
"""
修复并处理所有事件
"""
import asyncio
import asyncpg
from datetime import datetime

async def fix_and_process():
    print("🚀 修复并处理所有事件")
    print("="*60)
    
    try:
        # 连接数据库
        conn = await asyncpg.connect("postgresql://postgres:zxbzj~925@localhost/stock_data")
        
        # 1. 首先检查表结构
        print("1. 🔍 检查表结构...")
        
        # 检查news_event表的列
        columns = await conn.fetch('''
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'news_event'
            ORDER BY ordinal_position
        ''')
        
        print("   news_event表列:")
        for col in columns:
            print(f"     - {col['column_name']}: {col['data_type']}")
        
        # 2. 获取正确的未处理事件
        print("\n2. 📥 获取未处理事件...")
        
        # 使用正确的列名
        unprocessed = await conn.fetch('''
            SELECT 
                ne.id,
                nr.title,
                ne.summary,
                ne.event_type,
                nr.content,
                ne.created_at
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            WHERE ne.id NOT IN (SELECT DISTINCT event_id FROM event_theme_map)
            ORDER BY ne.created_at DESC
        ''')
        
        if not unprocessed:
            print("✅ 所有事件都已处理完成！")
            return
        
        print(f"   发现 {len(unprocessed)} 个未处理事件")
        
        # 3. 扩展主题关键词映射
        theme_keywords = {
            # 科技类
            "人工智能": ["ai", "人工智能", "大模型", "gpt", "机器学习", "深度学习", "神经网络"],
            "半导体芯片": ["芯片", "半导体", "集成电路", "中芯国际", "光刻机", "处理器"],
            "数字经济": ["数字经济", "数据要素", "大数据", "云计算", "区块链", "数字货币"],
            "5G通信": ["5g", "通信", "华为", "中兴", "基站", "网络"],
            "物联网": ["物联网", "iot", "智能家居", "智能设备", "传感器"],
            
            # 新能源
            "新能源汽车": ["新能源汽车", "电动车", "特斯拉", "蔚来", "理想", "小鹏", "电池", "充电桩"],
            "新能源发电": ["光伏", "风电", "储能", "太阳能", "可再生能源", "绿色能源"],
            "锂电池": ["锂电池", "锂电", "电池材料", "正极材料", "负极材料"],
            
            # 消费类
            "消费电子": ["消费电子", "苹果", "华为", "小米", "手机", "智能穿戴", "耳机", "平板"],
            "大消费": ["消费", "零售", "电商", "食品饮料", "白酒", "家电", "家居", "服装"],
            "医药医疗": ["医药", "医疗", "生物医药", "创新药", "疫苗", "医疗器械", "医院", "健康"],
            "旅游酒店": ["旅游", "酒店", "航空", "机场", "文旅", "景点", "出行"],
            
            # 金融地产
            "金融": ["金融", "银行", "保险", "证券", "券商", "支付", "理财", "投资"],
            "房地产": ["房地产", "地产", "房企", "楼市", "房价", "住宅", "商业地产"],
            "基建": ["基建", "基础设施建设", "铁路", "公路", "桥梁", "水利", "市政"],
            
            # 其他
            "军工国防": ["军工", "国防", "军事", "航空航天", "卫星", "航母", "导弹"],
            "物流运输": ["物流", "快递", "运输", "供应链", "仓储", "配送"],
            "传媒娱乐": ["传媒", "娱乐", "游戏", "影视", "短视频", "直播", "动漫", "版权"],
            "农业": ["农业", "种业", "粮食", "乡村振兴", "农药", "化肥", "养殖"],
            "环保": ["环保", "污水处理", "固废处理", "碳中和", "碳排放", "清洁能源"],
            "教育": ["教育", "培训", "在线教育", "职业教育", "K12"],
        }
        
        # 4. 处理每个事件
        print("\n3. 🔄 开始处理事件...")
        processed_count = 0
        themes_created = 0
        mappings_created = 0
        
        for i, event in enumerate(unprocessed, 1):
            event_id = event['id']
            title = event['title'] or "无标题"
            summary = event['summary'] or ""
            content_raw = event['content'] or ""
            
            # 合并所有文本内容
            content = f"{title} {summary} {content_raw}".lower()
            
            # 显示处理进度
            if len(title) > 40:
                title_display = title[:37] + "..."
            else:
                title_display = title
            
            print(f"\n[{i}/{len(unprocessed)}] 处理事件 #{event_id}: {title_display}")
            
            # 分析主题
            themes_found = set()
            for theme_name, keywords in theme_keywords.items():
                for keyword in keywords:
                    if keyword.lower() in content:
                        themes_found.add(theme_name)
                        break
            
            if themes_found:
                print(f"   发现主题: {', '.join(sorted(themes_found))}")
                
                for theme_name in sorted(themes_found):
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
                            (name, keywords, status, discovery_source, discovery_confidence, heat_score)
                            VALUES ($1, $2, $3, $4, $5, $6)
                            RETURNING id
                        ''',
                            theme_name,
                            [theme_name],
                            'active',
                            'fix_process',
                            0.8,  # 较高置信度
                            50    # 初始热度
                        )
                        theme_id = result['id']
                        themes_created += 1
                        print(f"   创建新主题: {theme_name} (ID: {theme_id})")
                    
                    # 创建映射（使用UPSERT避免重复）
                    try:
                        result = await conn.execute('''
                            INSERT INTO event_theme_map 
                            (event_id, theme_id, confidence, confidence_level, confidence_weight)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (event_id, theme_id) DO NOTHING
                            RETURNING id
                        ''',
                            event_id,
                            theme_id,
                            0.8 if theme_name in ["人工智能", "新能源汽车"] else 0.7,
                            'strong' if theme_name in ["人工智能", "新能源汽车"] else 'medium',
                            100 if theme_name in ["人工智能", "新能源汽车"] else 60
                        )
                        
                        if "INSERT" in result:
                            mappings_created += 1
                            
                    except Exception as e:
                        print(f"   警告: 创建映射失败 - {e}")
                
                print(f"   ✅ 成功关联 {len(themes_found)} 个主题")
                processed_count += 1
            else:
                print(f"   ⏳ 未发现相关主题")
                # 即使没找到主题，也标记为已处理（避免重复检查）
                processed_count += 1
            
            # 每处理5个事件显示一次进度
            if i % 5 == 0 or i == len(unprocessed):
                progress = (i / len(unprocessed) * 100)
                print(f"\n📊 进度: {i}/{len(unprocessed)} ({progress:.1f}%)")
        
        # 5. 显示最终结果
        print("\n" + "="*60)
        print("🎉 批量处理完成！")
        print("="*60)
        
        print(f"\n📊 处理结果统计:")
        print(f"   处理事件总数: {processed_count}/{len(unprocessed)}")
        print(f"   创建新主题: {themes_created}")
        print(f"   创建映射关系: {mappings_created}")
        
        # 6. 更新总体统计
        total_events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        total_processed = await conn.fetchval("SELECT COUNT(DISTINCT event_id) FROM event_theme_map")
        total_themes = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
        total_mappings = await conn.fetchval("SELECT COUNT(*) FROM event_theme_map")
        
        print(f"\n📈 系统总体统计:")
        print(f"   新闻事件总数: {total_events}")
        print(f"   已处理事件: {total_processed}")
        
        if total_events > 0:
            completion_rate = (total_processed / total_events * 100)
            print(f"   处理完成率: {completion_rate:.1f}%")
            
            if completion_rate >= 99.9:
                print("   🎉 所有事件处理完成！")
            elif completion_rate >= 80:
                print("   ✅ 大部分事件已处理")
            elif completion_rate >= 50:
                print("   🟡 处理进度过半")
            else:
                print("   🟠 仍有较多事件待处理")
        
        print(f"   投资主题总数: {total_themes}")
        print(f"   事件-主题映射: {total_mappings}")
        
        if total_processed > 0:
            avg_mappings = total_mappings / total_processed
            print(f"   平均每个事件的主题数: {avg_mappings:.1f}")
        
        # 7. 显示热门主题
        print(f"\n🏆 热门投资主题排行榜:")
        hot_themes = await conn.fetch('''
            SELECT 
                tm.name,
                COUNT(etm.event_id) as event_count,
                tm.heat_score
            FROM theme_master tm
            LEFT JOIN event_theme_map etm ON tm.id = etm.theme_id
            GROUP BY tm.id, tm.name, tm.heat_score
            ORDER BY event_count DESC, tm.heat_score DESC
            LIMIT 10
        ''')
        
        for i, theme in enumerate(hot_themes, 1):
            name = theme['name']
            count = theme['event_count'] or 0
            heat = theme['heat_score'] or 0
            
            # 创建简单的条形图
            bar_length = min(count, 20)
            bar = "█" * bar_length
            
            print(f"   {i:2d}. {name:12} {bar:20} {count:3d}事件 🔥{heat:3d}")
        
        await conn.close()
        
        print("\n" + "="*60)
        print("✅ 处理完成！系统已准备好进行后续分析。")
        
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(fix_and_process())
