#!/bin/bash
# 修复语法错误的监控脚本
echo "📊 AI题材引擎 - 数据流监控"
echo "="*60

while true; do
    clear
    echo "🎯 实时数据流监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*60
    
    python3 -c "
import asyncio
import sys
sys.path.append('.')
from theme_service.config import settings
import asyncpg
from datetime import datetime, timedelta

async def fixed_monitor():
    try:
        # 连接数据库
        conn = await asyncpg.connect(settings.DATABASE_URL)
        
        print('1. 🎯 系统核心指标:')
        print('   ' + '-'*40)
        
        # 获取基础统计
        stats = await conn.fetchrow('''
            SELECT 
                (SELECT COUNT(*) FROM news_event) as total_events,
                (SELECT COUNT(*) FROM theme_master) as total_themes,
                (SELECT COUNT(*) FROM event_theme_map) as total_mappings,
                (SELECT COUNT(DISTINCT event_id) FROM event_theme_map) as processed_events
        ''')
        
        total_events = stats['total_events'] or 0
        total_themes = stats['total_themes'] or 0
        total_mappings = stats['total_mappings'] or 0
        processed_events = stats['processed_events'] or 0
        
        print(f'   新闻事件总数: {total_events}')
        print(f'   投资主题总数: {total_themes}')
        print(f'   事件-主题映射: {total_mappings}')
        
        if total_events > 0:
            progress = (processed_events / total_events * 100)
            print(f'   处理进度: {progress:.1f}% ({processed_events}/{total_events})')
        
        print('\n2. 🔥 热门投资主题排名:')
        print('   ' + '-'*40)
        
        # 获取热门主题
        hot_themes = await conn.fetch('''
            SELECT 
                tm.name as theme_name,
                COUNT(etm.event_id) as event_count,
                tm.heat_score
            FROM theme_master tm
            LEFT JOIN event_theme_map etm ON tm.id = etm.theme_id
            GROUP BY tm.id, tm.name, tm.heat_score
            ORDER BY event_count DESC, tm.heat_score DESC
            LIMIT 8
        ''')
        
        if hot_themes:
            for i, theme in enumerate(hot_themes, 1):
                name = theme['theme_name']
                count = theme['event_count'] or 0
                heat = theme['heat_score'] or 0
                
                # 创建简单的柱状图
                bar = '█' * min(count, 15)
                print(f'   {i:2d}. {name:12} {bar:15} 📰{count:2d} 🔥{heat:3d}')
        else:
            print('   暂无主题数据')
        
        print('\n3. 📰 最新新闻事件处理:')
        print('   ' + '-'*40)
        
        # 获取最新事件
        recent_events = await conn.fetch('''
            SELECT 
                ne.id,
                nr.title,
                ne.event_type,
                ne.created_at,
                (SELECT COUNT(*) FROM event_theme_map WHERE event_id = ne.id) as theme_count
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            ORDER BY ne.created_at DESC
            LIMIT 5
        ''')
        
        if recent_events:
            for event in recent_events:
                event_id = event['id']
                title = event['title'] or '无标题'
                if len(title) > 40:
                    title = title[:37] + '...'
                
                event_type = event['event_type'] or '未知'
                created = event['created_at'].strftime('%m-%d %H:%M') if event['created_at'] else '未知'
                theme_count = event['theme_count'] or 0
                
                # 状态图标
                if theme_count > 0:
                    status = '✅'
                else:
                    status = '⏳'
                
                print(f'   {status} #{event_id:3d} [{created}] {event_type:8} {title}')
                if theme_count > 0:
                    print(f'       关联主题: {theme_count}个')
        else:
            print('   暂无新闻事件')
        
        print('\n4. ⚡ 实时处理状态:')
        print('   ' + '-'*40)
        
        # 最近10分钟的活动
        ten_min_ago = datetime.now() - timedelta(minutes=10)
        recent_mappings = await conn.fetchval('''
            SELECT COUNT(*) FROM event_theme_map WHERE created_at > \$1
        ''', ten_min_ago)
        
        # 最新处理的事件
        latest_processed = await conn.fetchval('''
            SELECT MAX(created_at) FROM event_theme_map
        ''')
        
        if latest_processed:
            latest_time = latest_processed.strftime('%H:%M:%S')
            time_diff = (datetime.now() - latest_processed).total_seconds()
            
            if time_diff < 60:
                recency = '🟢 实时'
            elif time_diff < 300:
                recency = '🟡 正常'
            elif time_diff < 1800:
                recency = '🟠 延迟'
            else:
                recency = '🔴 停滞'
            
            print(f'   最后处理时间: {latest_time} ({recency})')
            print(f'   最近10分钟处理: {recent_mappings} 个映射')
        else:
            print('   尚未开始处理')
        
        # 显示处理速度
        if recent_mappings > 0:
            speed = recent_mappings / 10  # 每分钟处理数
            print(f'   处理速度: {speed:.1f} 事件/分钟')
        
        print('\n' + '='*60)
        print('📋 系统信息:')
        print(f'   • 数据库: {settings.DATABASE_URL[:40]}...')
        print(f'   • 主题服务: http://localhost:8002')
        print(f'   • 监控更新: {datetime.now().strftime(\"%H:%M:%S\")}')
        
        await conn.close()
        
    except Exception as e:
        print(f'❌ 监控错误: {str(e)[:80]}')
        print('   请检查数据库连接或表结构')

asyncio.run(fixed_monitor())
"
    
    echo ""
    echo "🔄 10秒后自动刷新 (按 Ctrl+C 退出)"
    sleep 10
done
