#!/bin/bash
# 增强版数据流监控
echo "📊 AI题材引擎 - 数据流集成监控"
echo "="*70

while true; do
    clear
    echo "🎯 数据流集成监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*70
    
    python3 -c "
import asyncio
import sys
sys.path.append('.')
from theme_service.config import settings
import asyncpg
from datetime import datetime, timedelta

async def enhanced_monitor():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    
    print('1. 📈 数据概览:')
    print('   ' + '-'*40)
    
    # 总体统计
    total_events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
    total_themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
    total_mappings = await conn.fetchval('SELECT COUNT(*) FROM event_theme_map')
    
    print(f'   新闻事件: {total_events}')
    print(f'   投资主题: {total_themes}')
    print(f'   事件-主题映射: {total_mappings}')
    print(f'   映射覆盖率: {(total_mappings/total_events*100 if total_events>0 else 0):.1f}%')
    
    # 今日统计
    today = datetime.now().date()
    today_events = await conn.fetchval(
        'SELECT COUNT(*) FROM news_event WHERE DATE(created_at) = \$1',
        today
    )
    
    # 最近1小时处理
    one_hour_ago = datetime.now() - timedelta(hours=1)
    recent_mappings = await conn.fetchval('''
        SELECT COUNT(*) FROM event_theme_map 
        WHERE created_at > \$1
    ''', one_hour_ago)
    
    print(f'\n   今日事件: {today_events}')
    print(f'   最近1小时映射: {recent_mappings}')
    
    print('\n2. 🏷️ 热门主题 (按事件数量):')
    print('   ' + '-'*40)
    
    hot_themes = await conn.fetch('''
        SELECT 
            tm.name,
            COUNT(et.event_id) as event_count,
            tm.heat_score,
            tm.lifecycle_stage
        FROM theme_master tm
        LEFT JOIN event_theme_map et ON tm.id = et.theme_id
        GROUP BY tm.id, tm.name, tm.heat_score, tm.lifecycle_stage
        ORDER BY event_count DESC, tm.heat_score DESC
        LIMIT 8
    ''')
    
    for i, theme in enumerate(hot_themes, 1):
        stage = theme['lifecycle_stage'] or 'unknown'
        heat = theme['heat_score'] or 0
        events = theme['event_count'] or 0
        print(f'   {i}. {theme[\"name\"]:15} 🔥{heat:3d} 📰{events:3d}  [{stage}]')
    
    print('\n3. 📰 最新处理的事件:')
    print('   ' + '-'*40)
    
    recent_events = await conn.fetch('''
        SELECT 
            ne.id,
            COALESCE(ne.title, nr.title) as title,
            ne.event_type,
            COUNT(et.theme_id) as theme_count,
            ne.created_at
        FROM news_event ne
        LEFT JOIN news_raw nr ON ne.news_id = nr.id
        LEFT JOIN event_theme_map et ON ne.id = et.event_id
        GROUP BY ne.id, ne.title, nr.title, ne.event_type, ne.created_at
        ORDER BY ne.created_at DESC
        LIMIT 5
    ''')
    
    for event in recent_events:
        event_id = event['id']
        title = event['title'] or '无标题'
        if len(title) > 40:
            title = title[:37] + '...'
        theme_count = event['theme_count'] or 0
        event_type = event['event_type'] or '未知'
        created = event['created_at'].strftime('%H:%M') if event['created_at'] else '未知'
        
        theme_icon = '🎯' if theme_count > 0 else '📭'
        print(f'   #{event_id:3d} [{created}] {theme_icon} {title}')
        print(f'        类型: {event_type:10} 主题: {theme_count:2d}个')
    
    print('\n4. 🔄 数据流状态:')
    print('   ' + '-'*40)
    
    # 检查处理进度
    processed_events = await conn.fetchval('''
        SELECT COUNT(DISTINCT event_id) FROM event_theme_map
    ''')
    
    progress = (processed_events/total_events*100) if total_events > 0 else 0
    
    if progress >= 80:
        status = '✅ 良好'
    elif progress >= 50:
        status = '⚠️  一般'
    elif progress > 0:
        status = '🔄 进行中'
    else:
        status = '⏸️  未开始'
    
    print(f'   处理进度: {progress:.1f}% ({processed_events}/{total_events})')
    print(f'   数据流状态: {status}')
    
    # 检查是否有新事件需要处理
    unprocessed = total_events - processed_events
    if unprocessed > 0:
        print(f'   ⚠️  有待处理事件: {unprocessed} 个')
    
    print('\n' + '='*70)
    print('📋 服务状态:')
    print(f'   theme_service: http://localhost:8002')
    print(f'   model_service: http://localhost:8001 (如启用)')
    print(f'   数据库连接: ✅ 正常')
    
    await conn.close()

asyncio.run(enhanced_monitor())
"
    
    echo ""
    echo "🔄 15秒后自动刷新..."
    echo "按 Ctrl+C 退出监控"
    sleep 15
done
