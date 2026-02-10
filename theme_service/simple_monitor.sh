#!/bin/bash
# 最简单的监控脚本

echo "📊 AI题材引擎 - 简易监控"
echo "="*60

while true; do
    clear
    echo "监控时间: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*60
    
    # 1. 检查服务状态
    echo "1. 🔍 服务状态:"
    if pgrep -f "python.*start_service" > /dev/null; then
        echo "   ✅ 主题服务: 运行中"
    else
        echo "   ❌ 主题服务: 停止"
    fi
    
    if pgrep -f "python.*processor" > /dev/null; then
        echo "   ✅ 数据处理器: 运行中"
    else
        echo "   ❌ 数据处理器: 停止"
    fi
    
    # 2. 数据库统计
    echo ""
    echo "2. 📊 数据库统计:"
    python3 -c "
import asyncio
import sys
sys.path.append('.')
try:
    from theme_service.config import settings
    import asyncpg
    
    async def simple_stats():
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            
            # 基本统计
            events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
            themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
            mappings = await conn.fetchval('SELECT COUNT(*) FROM event_theme_map')
            
            print(f'   新闻事件: {events}')
            print(f'   投资主题: {themes}')
            print(f'   事件-主题映射: {mappings}')
            
            # 处理进度
            if events > 0:
                processed = await conn.fetchval('SELECT COUNT(DISTINCT event_id) FROM event_theme_map')
                percent = (processed / events * 100)
                print(f'   处理进度: {processed}/{events} ({percent:.1f}%)')
            
            # 最近活动
            recent = await conn.fetchval('''
                SELECT COUNT(*) FROM event_theme_map 
                WHERE created_at > NOW() - INTERVAL '5 minutes'
            ''')
            
            if recent > 0:
                print(f'   ⚡ 最近5分钟: {recent} 个新映射')
            else:
                print(f'   ⏸️  最近5分钟: 无新活动')
            
            await conn.close()
            
        except Exception as e:
            print(f'   ❌ 数据库错误: {str(e)[:50]}')
    
    asyncio.run(simple_stats())
    
except Exception as e:
    print(f'   ❌ 初始化错误: {e}')
"
    
    # 3. 最新主题
    echo ""
    echo "3. 🏷️ 最新发现的主题:"
    python3 -c "
import asyncio
import sys
sys.path.append('.')
try:
    from theme_service.config import settings
    import asyncpg
    
    async def recent_themes():
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            
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
                    print(f'   • {name} ({created})')
            else:
                print('   暂无主题数据')
            
            await conn.close()
            
        except Exception as e:
            print(f'   查询错误: {e}')
    
    asyncio.run(recent_themes())
    
except:
    print('   无法获取主题数据')
"
    
    # 4. 系统信息
    echo ""
    echo "4. ℹ️ 系统信息:"
    echo "   主题服务: http://localhost:8002"
    echo "   监控更新: $(date '+%H:%M:%S')"
    echo "   按 Ctrl+C 退出监控"
    
    echo ""
    echo "="*60
    sleep 10
done
