#!/bin/bash
# 极简监控脚本

echo "📊 AI题材引擎 - 极简监控"
echo "="*60

while true; do
    clear
    echo "监控时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*60
    
    # 1. 服务状态
    echo "1. 🖥️ 服务状态:"
    echo "   ----------"
    
    # 主题服务
    if curl -s http://localhost:8002/health > /dev/null 2>&1; then
        echo "   ✅ 主题服务: 运行中"
        echo "      地址: http://localhost:8002"
    else
        echo "   ❌ 主题服务: 停止"
    fi
    
    # 数据处理器
    if pgrep -f "fixed_processor" > /dev/null; then
        echo "   ✅ 数据处理器: 运行中"
        PID=$(pgrep -f "fixed_processor")
        echo "      进程ID: $PID"
    else
        echo "   ❌ 数据处理器: 停止"
    fi
    
    # 2. 数据库统计（使用直接连接）
    echo ""
    echo "2. 📊 数据库统计:"
    echo "   ----------"
    
    python3 << 'PYEOF'
import asyncio
import asyncpg

async def get_stats():
    try:
        # 直接连接数据库
        conn = await asyncpg.connect("postgresql://postgres:zxbzj~925@localhost/stock_data")
        
        # 获取统计数据
        events = await conn.fetchval("SELECT COUNT(*) FROM news_event")
        themes = await conn.fetchval("SELECT COUNT(*) FROM theme_master")
        mappings = await conn.fetchval("SELECT COUNT(*) FROM event_theme_map")
        processed = await conn.fetchval("SELECT COUNT(DISTINCT event_id) FROM event_theme_map")
        
        print(f"   新闻事件: {events}")
        print(f"   投资主题: {themes}")
        print(f"   事件-主题映射: {mappings}")
        
        if events > 0:
            progress = (processed / events * 100)
            print(f"   处理进度: {progress:.1f}% ({processed}/{events})")
        
        # 最近活动
        from datetime import datetime, timedelta
        ten_min_ago = datetime.now() - timedelta(minutes=10)
        recent = await conn.fetchval(
            "SELECT COUNT(*) FROM event_theme_map WHERE created_at > $1",
            ten_min_ago
        )
        
        if recent > 0:
            print(f"   ⚡ 最近10分钟: {recent} 个新映射")
        else:
            print(f"   ⏸️  最近10分钟: 无新活动")
        
        await conn.close()
        
    except Exception as e:
        print(f"   ❌ 数据库错误: {str(e)[:50]}")

asyncio.run(get_stats())
PYEOF
    
    # 3. 最新主题
    echo ""
    echo "3. 🏷️ 最新主题:"
    echo "   ----------"
    
    python3 << 'PYEOF'
import asyncio
import asyncpg

async def get_recent_themes():
    try:
        conn = await asyncpg.connect("postgresql://postgres:zxbzj~925@localhost/stock_data")
        
        themes = await conn.fetch('''
            SELECT name, created_at 
            FROM theme_master 
            ORDER BY created_at DESC 
            LIMIT 5
        ''')
        
        if themes:
            for theme in themes:
                name = theme['name']
                created = theme['created_at'].strftime('%H:%M') if theme['created_at'] else '未知'
                print(f"   • {name} ({created})")
        else:
            print("   暂无主题数据")
        
        await conn.close()
        
    except Exception as e:
        print(f"   查询失败: {str(e)[:50]}")

asyncio.run(get_recent_themes())
PYEOF
    
    # 4. 系统信息
    echo ""
    echo "4. ℹ️ 系统信息:"
    echo "   ----------"
    echo "   数据库: postgresql://localhost/stock_data"
    echo "   监控更新: $(date '+%H:%M:%S')"
    echo "   按 Ctrl+C 退出"
    
    echo ""
    echo "="*60
    sleep 10
done
