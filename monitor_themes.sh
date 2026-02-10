#!/bin/bash
# 监控主题变化
echo "📊 主题监控"
echo "="*60

while true; do
    clear
    echo "主题监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*60
    
    python -c "
import asyncio
import sys
sys.path.append('.')
from theme_service.config import settings
import asyncpg

async def monitor():
    conn = await asyncpg.connect(settings.DATABASE_URL)
    
    # 主题统计
    themes = await conn.fetch('SELECT name, status, discovery_source, created_at FROM theme_master ORDER BY created_at DESC LIMIT 10')
    print('📈 最新主题 (前10):')
    for i, theme in enumerate(themes, 1):
        created = theme['created_at'].strftime('%m-%d %H:%M') if theme['created_at'] else '未知'
        print(f'  {i}. {theme[\"name\"]} [{theme[\"status\"]}] ({theme[\"discovery_source\"]}) - {created}')
    
    # 映射统计
    mappings = await conn.fetch('SELECT COUNT(*) as count FROM event_theme_map')
    print(f'\n🔗 事件-主题映射: {mappings[0][\"count\"]}')
    
    # 最新事件
    events = await conn.fetch('''
        SELECT e.id, e.title, COUNT(et.theme_id) as theme_count
        FROM news_event e
        LEFT JOIN event_theme_map et ON e.id = et.event_id
        GROUP BY e.id, e.title
        ORDER BY e.created_at DESC
        LIMIT 5
    ''')
    
    print('\n📰 最新事件:')
    for event in events:
        title = event['title'][:50] if event['title'] else '无标题'
        print(f'  #{event[\"id\"]}: {title}... ({event[\"theme_count\"]}个主题)')
    
    await conn.close()

asyncio.run(monitor())
"
    
    echo ""
    echo "⏳ 10秒后刷新..."
    sleep 10
done
