#!/bin/bash
# 修复版监控面板 - 不依赖psutil

echo "📊 AI题材引擎 - 生产环境监控面板"
echo "="*70

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

while true; do
    clear
    echo -e "${BLUE}🏭 AI题材引擎 - 生产环境监控面板${NC}"
    echo -e "${CYAN}监控时间: $(date '+%Y-%m-%d %H:%M:%S')${NC}"
    echo "="*70
    
    python3 << 'PYEOF'
import asyncio
import asyncpg
from datetime import datetime, timedelta
import subprocess
import sys

async def fixed_dashboard():
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
                (SELECT MAX(created_at) FROM event_theme_map) as last_processed,
                (SELECT MIN(created_at) FROM event_theme_map) as first_processed
        ''')
        
        total_events = stats['total_events'] or 0
        processed_events = stats['processed_events'] or 0
        total_themes = stats['total_themes'] or 0
        total_mappings = stats['total_mappings'] or 0
        last_processed = stats['last_processed']
        first_processed = stats['first_processed']
        
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
            ("最近15分钟", 15),
            ("最近1小时", 60)
        ]
        
        total_recent = 0
        for label, minutes in time_ranges:
            since = now - timedelta(minutes=minutes)
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM event_theme_map WHERE created_at > $1",
                since
            )
            
            total_recent += count if minutes == 15 else 0
            
            # 活动图标和颜色
            if count > 0:
                if minutes == 5:
                    icon = "🟢"
                    color = "\033[92m"
                elif minutes == 15:
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
            speed = total_recent / 15  # 每分钟
            speed_color = "\033[92m" if speed >= 2 else "\033[93m" if speed >= 1 else "\033[91m"
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
        
        # 3. 热门主题排行榜（优化版）
        print("\n3. 🏆 热门主题排行榜:")
        print("   " + "-"*45)
        
        hot_themes = await conn.fetch('''
            SELECT 
                tm.name,
                COUNT(etm.event_id) as event_count,
                tm.heat_score,
                tm.discovery_source,
                COUNT(DISTINCT DATE(etm.created_at)) as active_days
            FROM theme_master tm
            LEFT JOIN event_theme_map etm ON tm.id = etm.theme_id
            GROUP BY tm.id, tm.name, tm.heat_score, tm.discovery_source
            HAVING COUNT(etm.event_id) > 0
            ORDER BY event_count DESC, tm.heat_score DESC
            LIMIT 10
        ''')
        
        if hot_themes:
            print("   排名 | 主题名称       | 热度 | 事件 | 活跃天数")
            print("   ----|---------------|------|------|----------")
            
            for i, theme in enumerate(hot_themes, 1):
                name = theme['name']
                if len(name) > 10:
                    name = name[:9] + "…"
                
                heat = theme['heat_score'] or 0
                count = theme['event_count'] or 0
                active_days = theme['active_days'] or 1
                
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
                bar_length = min(count, 12)
                bar = "█" * bar_length
                
                # 活跃天数指示
                if active_days >= 3:
                    days_icon = "🔥"
                elif active_days >= 2:
                    days_icon = "⚡"
                else:
                    days_icon = "⏳"
                
                print(f"   {rank_icon:3} {name:13} {heat_color}{heat:4d}\033[0m {bar:12} {count:3d} {days_icon}{active_days:2d}")
        
        # 4. 系统处理统计
        print("\n4. 📊 系统处理统计:")
        print("   " + "-"*45)
        
        # 今日处理统计
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_count = await conn.fetchval(
            "SELECT COUNT(*) FROM event_theme_map WHERE created_at >= $1",
            today_start
        )
        
        # 最近7天趋势
        week_start = datetime.now() - timedelta(days=7)
        week_stats = await conn.fetch('''
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as daily_count
            FROM event_theme_map
            WHERE created_at >= $1
            GROUP BY DATE(created_at)
            ORDER BY date DESC
            LIMIT 7
        ''', week_start)
        
        print(f"   今日处理: \033[94m{today_count}\033[0m 个映射")
        
        if week_stats:
            avg_daily = sum(row['daily_count'] for row in week_stats) / len(week_stats)
            print(f"   日均处理: \033[94m{avg_daily:.1f}\033[0m 个映射")
            
            # 趋势分析
            if len(week_stats) >= 2:
                latest = week_stats[0]['daily_count']
                previous = week_stats[1]['daily_count'] if len(week_stats) > 1 else 0
                
                if latest > previous * 1.2:
                    trend = "📈 上升"
                    trend_color = "\033[92m"
                elif latest < previous * 0.8:
                    trend = "📉 下降"
                    trend_color = "\033[91m"
                else:
                    trend = "➡️  平稳"
                    trend_color = "\033[93m"
                
                print(f"   处理趋势: {trend_color}{trend}\033[0m")
        
        # 5. 系统状态（简化版）
        print("\n5. 🖥️ 系统状态:")
        print("   " + "-"*45)
        
        # 检查主题服务
        theme_service_status = "未知"
        try:
            import urllib.request
            req = urllib.request.Request('http://localhost:8002/health', method='GET')
            response = urllib.request.urlopen(req, timeout=3)
            theme_service_status = "\033[92m✅ 运行中\033[0m"
        except:
            theme_service_status = "\033[91m❌ 停止\033[0m"
        
        print(f"   主题服务: {theme_service_status}")
        
        # 检查数据处理器（简化检查）
        import os
        processor_status = "\033[93m⚡ 检查中...\033[0m"
        try:
            result = subprocess.run(['pgrep', '-f', 'processor'], 
                                  capture_output=True, text=True)
            if result.returncode == 0:
                processor_status = "\033[92m✅ 运行中\033[0m"
            else:
                processor_status = "\033[91m❌ 停止\033[0m"
        except:
            processor_status = "\033[90m❓ 未知\033[0m"
        
        print(f"   数据处理器: {processor_status}")
        
        # 数据库状态
        print(f"   数据库: \033[92m✅ 连接正常\033[0m")
        
        # 运行时间
        if first_processed:
            uptime_days = (now - first_processed).days
            if uptime_days > 0:
                print(f"   运行时间: \033[94m{uptime_days}\033[0m 天")
            else:
                uptime_hours = int((now - first_processed).total_seconds() / 3600)
                print(f"   运行时间: \033[94m{uptime_hours}\033[0m 小时")
        
        await conn.close()
        
        print("\n" + "="*70)
        print("📋 监控信息:")
        print(f"   最后更新: {now.strftime('%H:%M:%S')}")
        print(f"   刷新间隔: 15秒")
        print(f"   按 Ctrl+C 退出监控")
        
    except Exception as e:
        print(f"\n\033[91m❌ 监控错误: {str(e)[:80]}\033[0m")
        print("   请检查数据库连接")

asyncio.run(fixed_dashboard())
PYEOF
    
    echo ""
    echo -e "${YELLOW}🔄 15秒后自动刷新...${NC}"
    sleep 15
done
