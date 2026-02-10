#!/bin/bash
# 修复版监控脚本
echo "📊 AI题材引擎 - 数据流监控"
echo "="*60

while true; do
    clear
    echo "🎯 数据流监控 - $(date '+%Y-%m-%d %H:%M:%S')"
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
        conn = await asyncpg.connect(settings.DATABASE_URL)
        
        print('1. 📈 核心数据统计:')
        print('   ' + '-'*40)
        
        # 基本统计
        total_events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
        total_themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
        total_mappings = await conn.fetchval('SELECT COUNT(*) FROM event_theme_map')
        
        print(f'   新闻事件总数: {total_events}')
        print(f'   投资主题总数: {total_themes}')
        print(f'   事件-主题映射: {total_mappings}')
        
        if total_events > 0:
            coverage = (total_mappings / total_events * 100)
            print(f'   主题覆盖率: {coverage:.1f}%')
        
        print('\n2. 🏷️ 热门投资主题:')
        print('   ' + '-'*40)
        
        # 使用更简单的查询
        hot_themes = await conn.fetch('''
            SELECT 
                tm.name,
                COUNT(et.event_id) as event_count
            FROM theme_master tm
            LEFT JOIN event_theme_map et ON tm.id = et.theme_id
            GROUP BY tm.id, tm.name
            ORDER BY event_count DESC
            LIMIT 10
        ''')
        
        for i, theme in enumerate(hot_themes, 1):
            name = theme['name']
            count = theme['event_count'] or 0
            bar = '█' * min(count, 20)  # 简单条形图
            print(f'   {i:2d}. {name:15} {bar:20} ({count:3d}事件)')
        
        print('\n3. 📰 最新新闻事件:')
        print('   ' + '-'*40)
        
        # 简化的最新事件查询
        recent_events = await conn.fetch('''
            SELECT 
                ne.id,
                COALESCE(ne.title, nr.title, \'无标题\') as title,
                ne.created_at
            FROM news_event ne
            LEFT JOIN news_raw nr ON ne.news_id = nr.id
            ORDER BY ne.created_at DESC
            LIMIT 5
        ''')
        
        for event in recent_events:
            event_id = event['id']
            title = event['title']
            if len(title) > 45:
                title = title[:42] + '...'
            created = event['created_at'].strftime('%m-%d %H:%M') if event['created_at'] else '未知'
            
            # 检查是否有主题映射
            theme_count = await conn.fetchval('''
                SELECT COUNT(*) FROM event_theme_map WHERE event_id = \$1
            ''', event_id)
            
            status = '✅' if theme_count > 0 else '⏳'
            print(f'   {status} #{event_id:3d} [{created}] {title}')
        
        print('\n4. 🔄 处理状态:')
        print('   ' + '-'*40)
        
        # 检查处理状态
        processed_count = await conn.fetchval('''
            SELECT COUNT(DISTINCT event_id) FROM event_theme_map
        ''')
        
        if total_events > 0:
            progress = (processed_count / total_events * 100)
            bar_length = 30
            filled = int(bar_length * progress / 100)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            print(f'   处理进度: [{bar}] {progress:.1f}%')
            print(f'   已处理: {processed_count}/{total_events} 事件')
            
            if progress >= 90:
                status = '🟢 优秀'
            elif progress >= 70:
                status = '🟡 良好'
            elif progress >= 30:
                status = '🟠 进行中'
            else:
                status = '🔴 待处理'
            
            print(f'   状态: {status}')
        
        # 检查最近活动
        last_hour = datetime.now() - timedelta(hours=1)
        recent_activity = await conn.fetchval('''
            SELECT COUNT(*) FROM event_theme_map 
            WHERE created_at > \$1
        ''', last_hour)
        
        if recent_activity > 0:
            print(f'   ⏰ 最近1小时: {recent_activity} 个新映射')
        else:
            print(f'   ⏰ 最近1小时: 无新活动')
        
        print('\n' + '='*60)
        print('📋 服务信息:')
        print(f'   theme_service: http://localhost:8002')
        print(f'   数据库: {settings.DATABASE_URL[:40]}...')
        print(f'   监控更新时间: {datetime.now().strftime("%H:%M:%S")}')
        
        await conn.close()
        
    except Exception as e:
        print(f'❌ 监控错误: {e}')
        print('   可能是数据库连接问题或表结构不一致')

asyncio.run(fixed_monitor())
"
    
    echo ""
    echo "🔄 10秒后自动刷新..."
    echo "按 Ctrl+C 退出监控"
    sleep 10
done
