#!/bin/bash
# AI题材引擎 - 完整生产监控面板

echo "📊 AI题材引擎 - 生产环境监控面板"
echo "="*70

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
NC='\033[0m' # No Color

# 设置Python路径
export PYTHONPATH=$PYTHONPATH:$(pwd)

while true; do
    clear
    echo -e "${BLUE}🏭 AI题材引擎 - 生产环境监控面板${NC}"
    echo -e "${CYAN}监控时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo "="*70
    
    python3 << 'PYEOF'
import asyncio
import asyncpg
from datetime import datetime, timedelta
import sys

async def production_dashboard():
    try:
        # 连接数据库
        DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"
        conn = await asyncpg.connect(DATABASE_URL)
        
        # 1. 系统概览
        print("1. 🎯 系统概览:")
        print("   " + "-"*45)
        
        # 基础统计
        stats = await conn.fetchrow('''
            SELECT 
                (SELECT COUNT(*) FROM news_event) as total_events,
                (SELECT COUNT(DISTINCT event_id) FROM event_theme_map) as processed_events,
                (SELECT COUNT(*) FROM theme_master) as total_themes,
                (SELECT COUNT(*) FROM event_theme_map) as total_mappings,
                (SELECT MAX(created_at) FROM event_theme_map) as last_processed
        ''')
        
        total_events = stats['total_events'] or 0
        processed_events = stats['processed_events'] or 0
        total_themes = stats['total_themes'] or 0
        total_mappings = stats['total_mappings'] or 0
        last_processed = stats['last_processed']
        
        # 处理进度
        if total_events > 0:
            progress = (processed_events / total_events * 100)
            bar_length = 30
            filled = int(bar_length * progress / 100)
            bar = "█" * filled + "░" * (bar_length - filled)
            
            # 进度颜色
            if progress >= 90:
                progress_color = "\033[92m"  # 绿色
            elif progress >= 70:
                progress_color = "\033[93m"  # 黄色
            elif progress >= 50:
                progress_color = "\033[33m"  # 橙色
            else:
                progress_color = "\033[91m"  # 红色
            
            print(f"   处理进度: {progress_color}[{bar}]\033[0m {progress:.1f}%")
            print(f"   新闻事件: {processed_events}/{total_events}")
            
            if progress >= 99.9:
                print("   \033[92m✅ 所有事件处理完成！\033[0m")
            elif progress >= 80:
                print("   \033[93m⚠️  接近完成\033[0m")
            else:
                remaining = total_events - processed_events
                print(f"   \033[33m📋 剩余待处理: {remaining} 个事件\033[0m")
        
        # 数据规模
        print(f"   投资主题: \033[94m{total_themes}\033[0m")
        print(f"   事件映射: \033[94m{total_mappings}\033[0m")
        
        if processed_events > 0:
            avg_density = total_mappings / processed_events
            density_color = "\033[92m" if avg_density >= 1.5 else "\033[93m" if avg_density >= 1.0 else "\033[91m"
            print(f"   映射密度: {density_color}{avg_density:.1f} 主题/事件\033[0m")
        
        # 2. 实时活动监控
        print("\n2. ⚡ 实时活动监控:")
        print("   " + "-"*45)
        
        now = datetime.now()
        time_ranges = [
            ("最近5分钟", 5),
            ("最近30分钟", 30),
            ("最近1小时", 60)
        ]
        
        total_recent = 0
        for label, minutes in time_ranges:
            since = now - timedelta(minutes=minutes)
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM event_theme_map WHERE created_at > $1",
                since
            )
            
            total_recent += count if minutes == 5 else 0
            
            # 活动图标和颜色
            if count > 0:
                if minutes == 5:
                    icon = "🟢"
                    color = "\033[92m"
                elif minutes == 30:
                    icon = "🟡"
                    color = "\033[93m"
                else:
                    icon = "🟠"
                    color = "\033[33m"
            else:
                icon = "⚪"
                color = "\033[90m"
            
            print(f"   {icon} {label}: {color}{count:3d}\033[0m 个映射")
        
        # 处理速度
        if total_recent > 0:
            speed = total_recent / 5  # 每分钟
            speed_color = "\033[92m" if speed >= 5 else "\033[93m" if speed >= 2 else "\033[91m"
            print(f"   📈 处理速度: {speed_color}{speed:.1f}\033[0m 映射/分钟")
        
        # 最后处理时间
        if last_processed:
            time_diff = (now - last_processed).total_seconds() / 60  # 分钟
            
            if time_diff < 5:
                recency = "🟢 实时"
                color = "\033[92m"
            elif time_diff < 30:
                recency = "🟡 正常"
                color = "\033[93m"
            elif time_diff < 60:
                recency = "🟠 延迟"
                color = "\033[33m"
            else:
                recency = "🔴 停滞"
                color = "\033[91m"
            
            last_time = last_processed.strftime("%H:%M:%S")
            print(f"   ⏰ 最后处理: {color}{last_time}\033[0m ({recency})")
        
        # 3. 热门主题排行榜
        print("\n3. 🏆 热门主题排行榜:")
        print("   " + "-"*45)
        
        hot_themes = await conn.fetch('''
            SELECT 
                tm.name,
                COUNT(etm.event_id) as event_count,
                tm.heat_score,
                tm.created_at,
                tm.discovery_source
            FROM theme_master tm
            LEFT JOIN event_theme_map etm ON tm.id = etm.theme_id
            GROUP BY tm.id, tm.name, tm.heat_score, tm.created_at, tm.discovery_source
            ORDER BY event_count DESC, tm.heat_score DESC
            LIMIT 10
        ''')
        
        if hot_themes:
            print("   排名 | 主题名称       | 热度 | 事件数 | 来源")
            print("   ----|---------------|------|--------|----------")
            
            for i, theme in enumerate(hot_themes, 1):
                name = theme['name']
                if len(name) > 10:
                    name = name[:9] + "…"
                
                heat = theme['heat_score'] or 0
                count = theme['event_count'] or 0
                source = theme['discovery_source'] or "未知"
                if len(source) > 6:
                    source = source[:5] + "…"
                
                # 热度颜色
                if heat >= 70:
                    heat_color = "\033[92m"  # 绿色
                elif heat >= 40:
                    heat_color = "\033[93m"  # 黄色
                else:
                    heat_color = "\033[90m"  # 灰色
                
                # 排名图标
                if i == 1:
                    rank_icon = "🥇"
                elif i == 2:
                    rank_icon = "🥈"
                elif i == 3:
                    rank_icon = "🥉"
                else:
                    rank_icon = f"{i:2d}."
                
                # 事件数条形图
                bar_length = min(count, 15)
                bar = "█" * bar_length
                
                print(f"   {rank_icon:3} {name:13} {heat_color}{heat:4d}\033[0m {bar:15} {count:3d} {source:6}")
        
        # 4. 最新处理事件
        print("\n4. 📰 最新处理事件:")
        print("   " + "-"*45)
        
        recent_events = await conn.fetch('''
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
        
        if recent_events:
            for event in recent_events:
                event_id = event['id']
                title = event['title']
                if len(title) > 40:
                    title = title[:37] + "..."
                
                theme_count = event['theme_count'] or 0
                processed_at = event['processed_at']
                
                if processed_at:
                    time_str = processed_at.strftime("%H:%M:%S")
                    time_diff = (now - processed_at).total_seconds()
                    
                    if time_diff < 60:
                        recency = "刚刚"
                        time_color = "\033[92m"
                    elif time_diff < 300:
                        recency = "5分钟内"
                        time_color = "\033[93m"
                    else:
                        minutes = int(time_diff / 60)
                        recency = f"{minutes}分钟前"
                        time_color = "\033[90m"
                    
                    # 主题数量图标
                    if theme_count >= 3:
                        theme_icon = "🔴"
                    elif theme_count >= 2:
                        theme_icon = "🟡"
                    else:
                        theme_icon = "🟢"
                    
                    print(f"   {theme_icon} \033[94m#{event_id:03d}\033[0m [{time_color}{time_str}\033[0m] {title}")
                    print(f"       主题: {theme_count}个 ({time_color}{recency}\033[0m)")
        else:
            print("   暂无已处理事件")
        
        # 5. 系统状态
        print("\n5. 🖥️ 系统状态:")
        print("   " + "-"*45)
        
        # 检查服务状态
        import subprocess
        import json
        
        # 主题服务
        theme_service_status = "未知"
        try:
            import urllib.request
            import urllib.error
            req = urllib.request.Request('http://localhost:8002/health', method='GET')
            response = urllib.request.urlopen(req, timeout=2)
            theme_service_status = "\033[92m运行中\033[0m"
        except:
            theme_service_status = "\033[91m停止\033[0m"
        
        print(f"   主题服务: {theme_service_status}")
        print(f"      地址: \033[94mhttp://localhost:8002\033[0m")
        
        # 数据处理器
        import psutil
        processor_running = False
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['cmdline'] and any('processor' in str(cmd).lower() for cmd in proc.info['cmdline']):
                    processor_running = True
                    processor_pid = proc.info['pid']
                    break
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        if processor_running:
            print(f"   数据处理器: \033[92m运行中\033[0m (PID: {processor_pid})")
        else:
            print(f"   数据处理器: \033[91m停止\033[0m")
        
        # 数据库连接
        print(f"   数据库连接: \033[92m正常\033[0m")
        print(f"      地址: {DATABASE_URL[:40]}...")
        
        # 系统信息
        uptime = await conn.fetchval("SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at))) FROM event_theme_map")
        if uptime:
            hours = int(uptime / 3600)
            minutes = int((uptime % 3600) / 60)
            print(f"   运行时间: {hours}小时{minutes}分钟")
        
        await conn.close()
        
        print("\n" + "="*70)
        print("📋 监控信息:")
        print(f"   最后更新: {now.strftime('%H:%M:%S')}")
        print(f"   刷新间隔: 10秒")
        print(f"   按 Ctrl+C 退出监控")
        
    except Exception as e:
        print(f"\n\033[91m❌ 监控错误: {str(e)[:80]}\033[0m")
        print("   请检查数据库连接或系统状态")

asyncio.run(production_dashboard())
PYEOF
    
    echo ""
    echo -e "${YELLOW}🔄 10秒后自动刷新...${NC}"
    sleep 10
done
