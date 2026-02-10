#!/bin/bash
# 增强版监控

echo "📊 AI题材引擎 - 增强监控面板"
echo "="*70

while true; do
    clear
    echo "🎯 实时数据流监控 - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "="*70
    
    python3 -c "
import asyncio
import sys
sys.path.append('.')
from theme_service.config import settings
import asyncpg
from datetime import datetime, timedelta

async def enhanced_monitor():
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
        
        print('1. 📈 核心数据指标:')
        print('   ' + '-'*45)
        
        # 基础统计
        stats = await conn.fetchrow('''
            SELECT 
                (SELECT COUNT(*) FROM news_event) as total_events,
                (SELECT COUNT(*) FROM theme_master) as total_themes,
                (SELECT COUNT(*) FROM event_theme_map) as total_mappings,
                (SELECT COUNT(DISTINCT event_id) FROM event_theme_map) as processed_events,
                (SELECT COUNT(*) FROM theme_master WHERE created_at > NOW() - INTERVAL '1 hour') as new_themes_1h
        ''')
        
        total_events = stats['total_events'] or 0
        total_themes = stats['total_themes'] or 0
        total_mappings = stats['total_mappings'] or 0
        processed_events = stats['processed_events'] or 0
        new_themes_1h = stats['new_themes_1h'] or 0
        
        print(f'   新闻事件: {total_events:4d}')
        print(f'   投资主题: {total_themes:4d}')
        print(f'   事件-主题映射: {total_mappings:4d}')
        
        if total_events > 0:
            progress = (processed_events / total_events * 100)
            bar_length = 25
            filled = int(bar_length * progress / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            print(f'   处理进度: [{bar}] {progress:.1f}%')
        
        print(f'   最近1小时新主题: {new_themes_1h}')
        
        print('\n2. 🔥 热门主题排行榜:')
        print('   ' + '-'*45)
        
        # 热门主题
        hot_themes = await conn.fetch('''
            SELECT 
                tm.name,
                COUNT(etm.event_id) as event_count,
                tm.heat_score,
                tm.discovery_source
            FROM theme_master tm
            LEFT JOIN event_theme_map etm ON tm.id = etm.theme_id
            GROUP BY tm.id, tm.name, tm.heat_score, tm.discovery_source
            ORDER BY event_count DESC, tm.heat_score DESC
            LIMIT 10
        ''')
        
        if hot_themes:
            print('   排名 主题             关联事件 热度 来源')
            print('   ---- --------------- -------- ---- ------')
            for i, theme in enumerate(hot_themes, 1):
                name = theme['name']
                if len(name) > 10:
                    name = name[:9] + '…'
                
                count = theme['event_count'] or 0
                heat = theme['heat_score'] or 0
                source = theme['discovery_source'] or '未知'
                if len(source) > 8:
                    source = source[:7] + '…'
                
                print(f'   {i:3d}. {name:14} {count:7d} {heat:5d} {source:8}')
        else:
            print('   暂无主题数据')
        
        print('\n3. 📰 最新动态:')
        print('   ' + '-'*45)
        
        # 最新事件
        recent_events = await conn.fetch('''
            SELECT 
                ne.id,
                COALESCE(nr.title, '无标题') as title,
                ne.event_type,
                ne.created_at,
                (SELECT COUNT(*) FROM event_theme_map WHERE event_id = ne.id) as theme_count
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            ORDER BY ne.created_at DESC
            LIMIT 4
        ''')
        
        if recent_events:
            for event in recent_events:
                event_id = event['id']
                title = event['title']
                if len(title) > 35:
                    title = title[:32] + '...'
                
                event_type = event['event_type'] or '未知'
                created = event['created_at'].strftime('%m-%d %H:%M')
                theme_count = event['theme_count'] or 0
                
                status = '✅' if theme_count > 0 else '⏳'
                type_icon = {
                    '政策利好': '📜',
                    '产品发布': '📱', 
                    '技术突破': '💡',
                    '风险警示': '⚠️ ',
                    '合作签约': '🤝',
                    '默认': '📰'
                }.get(event_type, '📰')
                
                print(f'   {status} {type_icon} #{event_id:3d} [{created}] {title}')
                if theme_count > 0:
                    # 获取具体主题
                    themes = await conn.fetch('''
                        SELECT tm.name 
                        FROM event_theme_map etm
                        JOIN theme_master tm ON etm.theme_id = tm.id
                        WHERE etm.event_id = \$1
                        LIMIT 3
                    ''', event_id)
                    
                    if themes:
                        theme_names = [t['name'] for t in themes]
                        print(f'       主题: {', '.join(theme_names)}' + ('...' if len(themes) == 3 else ''))
        
        print('\n4. ⚡ 实时处理状态:')
        print('   ' + '-'*45)
        
        # 最近活动
        now = datetime.now()
        time_ranges = [
            ('最近5分钟', 5),
            ('最近30分钟', 30),
            ('最近1小时', 60)
        ]
        
        for label, minutes in time_ranges:
            since = now - timedelta(minutes=minutes)
            count = await conn.fetchval('''
                SELECT COUNT(*) FROM event_theme_map WHERE created_at > \$1
            ''', since)
            
            icon = '⚡' if count > 0 else '⏸️'
            print(f'   {icon} {label}: {count:3d} 个映射')
        
        # 处理速度估算
        hour_ago = now - timedelta(hours=1)
        hour_count = await conn.fetchval('''
            SELECT COUNT(*) FROM event_theme_map WHERE created_at > \$1
        ''', hour_ago)
        
        if hour_count > 0:
            speed = hour_count / 60  # 每分钟
            print(f'   📈 处理速度: {speed:.1f} 事件/分钟')
        
        print('\n' + '='*70)
        print('📋 系统信息:')
        print(f'   数据库: {settings.DATABASE_URL[:45]}...')
        print(f'   主题服务: http://localhost:8002')
        print(f'   监控更新: {now.strftime(\"%H:%M:%S\")}')
        
        await conn.close()
        
    except Exception as e:
        print(f'❌ 监控错误: {str(e)[:70]}')

asyncio.run(enhanced_monitor())
"
    
    echo ""
    echo "🔄 15秒后自动刷新 (按 Ctrl+C 退出)"
    sleep 15
done
