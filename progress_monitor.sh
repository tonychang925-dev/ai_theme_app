#!/bin/bash
# 进度监控脚本

echo "📈 AI题材引擎 - 处理进度监控"
echo "="*60

while true; do
    clear
    echo "监控时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*60
    
    # 获取处理进度
    python3 << 'PYEOF'
import asyncio
import asyncpg
from datetime import datetime

async def monitor_progress():
    try:
        conn = await asyncpg.connect("postgresql://postgres:zxbzj~925@localhost/stock_data")
        
        # 基本统计
        total_events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        processed_events = await conn.fetchval("SELECT COUNT(DISTINCT event_id) FROM event_theme_map")
        total_themes = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
        total_mappings = await conn.fetchval("SELECT COUNT(*) FROM event_theme_map")
        
        print("1. 📊 总体进度:")
        print("   ----------")
        print(f"   新闻事件总数: {total_events}")
        print(f"   已处理事件: {processed_events}")
        
        if total_events > 0:
            progress = (processed_events / total_events * 100)
            # 创建进度条
            bar_length = 30
            filled = int(bar_length * progress / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            print(f"   处理进度: [{bar}] {progress:.1f}%")
            
            remaining = total_events - processed_events
            if remaining > 0:
                print(f"   ⚠️  剩余待处理: {remaining} 个事件")
            else:
                print(f"   ✅ 所有事件处理完成！")
        
        print(f"\n2. 🎯 处理结果:")
        print("   ----------")
        print(f"   投资主题总数: {total_themes}")
        print(f"   事件-主题映射: {total_mappings}")
        
        # 最近活动
        from datetime import datetime, timedelta
        five_min_ago = datetime.now() - timedelta(minutes=5)
        recent = await conn.fetchval(
            "SELECT COUNT(*) FROM event_theme_map WHERE created_at > $1",
            five_min_ago
        )
        
        print(f"\n3. ⚡ 最近活动:")
        print("   ----------")
        if recent > 0:
            print(f"   ✅ 最近5分钟: {recent} 个新映射")
            speed = recent / 5  # 每分钟
            print(f"   处理速度: {speed:.1f} 映射/分钟")
        else:
            print("   ⏸️  最近5分钟: 无新活动")
        
        # 最新处理的几个事件
        print(f"\n4. 📰 最新处理的事件:")
        print("   ----------")
        recent_processed = await conn.fetch('''
            SELECT 
                ne.id,
                COALESCE(nr.title, '无标题') as title,
                (SELECT COUNT(*) FROM event_theme_map WHERE event_id = ne.id) as theme_count,
                (SELECT MAX(created_at) FROM event_theme_map WHERE event_id = ne.id) as processed_at
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            WHERE ne.id IN (SELECT DISTINCT event_id FROM event_theme_map)
            ORDER BY (SELECT MAX(created_at) FROM event_theme_map WHERE event_id = ne.id) DESC
            LIMIT 3
        ''')
        
        if recent_processed:
            for event in recent_processed:
                event_id = event['id']
                title = event['title']
                if len(title) > 40:
                    title = title[:37] + "..."
                
                theme_count = event['theme_count'] or 0
                processed_at = event['processed_at']
                
                if processed_at:
                    time_str = processed_at.strftime("%H:%M:%S")
                    time_diff = (datetime.now() - processed_at).total_seconds()
                    
                    if time_diff < 60:
                        recency = "刚刚"
                    elif time_diff < 300:
                        recency = "5分钟内"
                    else:
                        recency = f"{int(time_diff/60)}分钟前"
                    
                    print(f"   ✅ #{event_id}: {title}")
                    print(f"      主题: {theme_count}个, 处理于: {time_str} ({recency})")
        else:
            print("   暂无已处理事件")
        
        await conn.close()
        
    except Exception as e:
        print(f"❌ 监控错误: {e}")

asyncio.run(monitor_progress())
PYEOF
    
    echo ""
    echo "="*60
    echo "📋 系统信息:"
    echo "   强制处理器PID: $FORCE_PID (如果正在运行)"
    echo "   查看完整日志: tail -f force_processor.log"
    echo "   按 Ctrl+C 退出监控"
    echo ""
    
    # 检查处理器是否还在运行
    if ps -p $FORCE_PID > /dev/null 2>&1; then
        echo "✅ 强制处理器正在运行"
    else
        echo "❌ 强制处理器已停止"
        echo "   查看日志了解原因: tail -20 force_processor.log"
    fi
    
    sleep 10
done
