#!/bin/bash
# 修复导入问题的监控脚本

echo "📊 AI题材引擎 - 数据流监控"
echo "="*60

# 设置Python路径
export PYTHONPATH=$PYTHONPATH:$(pwd)

while true; do
    clear
    echo "🎯 实时数据流监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*60
    
    # 直接使用Python代码，避免复杂的导入
    python3 << 'PYEOF'
import asyncio
import asyncpg
import sys
import os
from datetime import datetime, timedelta

# 添加当前目录到Python路径
current_dir = os.getcwd()
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.join(current_dir, "theme_service"))

async def simple_monitor():
    try:
        # 直接使用数据库连接字符串
        DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
        
        print("1. 🔌 数据库连接状态:")
        print("   " + "-"*40)
        
        conn = None
        try:
            conn = await asyncpg.connect(DATABASE_URL)
            print("   ✅ 数据库连接成功")
        except Exception as e:
            print(f"   ❌ 数据库连接失败: {e}")
            return
        
        try:
            # 1. 基本统计
            print("\n2. 📊 数据统计:")
            print("   " + "-"*40)
            
            # 新闻事件总数
            total_events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
            print(f"   新闻事件总数: {total_events}")
            
            # 投资主题总数
            total_themes = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
            print(f"   投资主题总数: {total_themes}")
            
            # 事件-主题映射
            total_mappings = await conn.fetchval("SELECT COUNT(*) FROM event_theme_map")
            print(f"   事件-主题映射: {total_mappings}")
            
            # 已处理事件
            processed_events = await conn.fetchval("SELECT COUNT(DISTINCT event_id) FROM event_theme_map")
            print(f"   已处理事件: {processed_events}")
            
            # 处理进度
            if total_events > 0:
                progress = (processed_events / total_events * 100)
                print(f"   处理进度: {progress:.1f}%")
            
            # 2. 热门主题
            print("\n3. 🔥 热门主题排行榜:")
            print("   " + "-"*40)
            
            hot_themes = await conn.fetch('''
                SELECT 
                    tm.name,
                    COUNT(etm.event_id) as event_count
                FROM theme_master tm
                LEFT JOIN event_theme_map etm ON tm.id = etm.theme_id
                GROUP BY tm.id, tm.name
                ORDER BY event_count DESC
                LIMIT 8
            ''')
            
            if hot_themes:
                print("   排名 | 主题名称       | 关联事件")
                print("   -----|---------------|-----------")
                for i, theme in enumerate(hot_themes, 1):
                    name = theme['name']
                    if len(name) > 12:
                        name = name[:11] + "…"
                    count = theme['event_count'] or 0
                    print(f"   {i:4d} | {name:13} | {count:8d}")
            else:
                print("   暂无主题数据")
            
            # 3. 最新事件
            print("\n4. 📰 最新事件处理状态:")
            print("   " + "-"*40)
            
            recent_events = await conn.fetch('''
                SELECT 
                    ne.id,
                    COALESCE(nr.title, '无标题') as title,
                    (SELECT COUNT(*) FROM event_theme_map WHERE event_id = ne.id) as theme_count
                FROM news_event ne
                LEFT JOIN news_raw nr ON ne.news_id = nr.id
                ORDER BY ne.created_at DESC
                LIMIT 5
            ''')
            
            if recent_events:
                for event in recent_events:
                    event_id = event['id']
                    title = event['title']
                    if len(title) > 40:
                        title = title[:37] + "..."
                    
                    theme_count = event['theme_count'] or 0
                    
                    if theme_count > 0:
                        status = "✅"
                    else:
                        status = "⏳"
                    
                    print(f"   {status} #{event_id:3d} {title}")
            else:
                print("   暂无事件数据")
            
            # 4. 处理状态
            print("\n5. ⚡ 实时处理状态:")
            print("   " + "-"*40)
            
            # 最近10分钟的活动
            ten_min_ago = datetime.now() - timedelta(minutes=10)
            recent_mappings = await conn.fetchval('''
                SELECT COUNT(*) FROM event_theme_map WHERE created_at > $1
            ''', ten_min_ago)
            
            print(f"   最近10分钟处理: {recent_mappings} 个映射")
            
            if recent_mappings > 0:
                speed = recent_mappings / 10  # 每分钟
                print(f"   处理速度: {speed:.1f} 事件/分钟")
            else:
                print("   ⏸️  最近10分钟无新处理")
            
            # 最新处理时间
            latest_processed = await conn.fetchval('''
                SELECT MAX(created_at) FROM event_theme_map
            ''')
            
            if latest_processed:
                latest_time = latest_processed.strftime("%H:%M:%S")
                time_diff = (datetime.now() - latest_processed).total_seconds()
                
                if time_diff < 60:
                    recency = "🟢 实时"
                elif time_diff < 300:
                    recency = "🟡 正常"
                elif time_diff < 1800:
                    recency = "🟠 延迟"
                else:
                    recency = "🔴 停滞"
                
                print(f"   最后处理时间: {latest_time} ({recency})")
            
            print("\n" + "="*60)
            print("📋 系统信息:")
            print(f"   数据库: {DATABASE_URL[:40]}...")
            print(f"   监控更新: {datetime.now().strftime('%H:%M:%S')}")
            
        finally:
            if conn:
                await conn.close()
                
    except Exception as e:
        print(f"❌ 监控错误: {str(e)[:80]}")

# 运行监控
asyncio.run(simple_monitor())
PYEOF
    
    echo ""
    echo "🔄 10秒后自动刷新 (按 Ctrl+C 退出)"
    sleep 10
done
