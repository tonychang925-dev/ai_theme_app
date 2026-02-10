#!/bin/bash
# 启动简化监控面板

echo "🚀 启动 AI题材引擎 - 简化监控面板"
echo "="*70

# 检查服务状态
echo "检查系统状态..."
echo ""

# 数据库状态
python3 -c "
import asyncio
import asyncpg

async def quick_status():
    try:
        conn = await asyncpg.connect('postgresql://postgres:zxbzj~925@localhost/stock_data')
        
        events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
        processed = await conn.fetchval('SELECT COUNT(DISTINCT event_id) FROM event_theme_map')
        themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
        mappings = await conn.fetchval('SELECT COUNT(*) FROM event_theme_map')
        
        print('📊 数据统计:')
        print(f'   新闻事件: {events}')
        print(f'   已处理: {processed} ({processed/events*100 if events>0 else 0:.1f}%)')
        print(f'   投资主题: {themes}')
        print(f'   事件映射: {mappings}')
        
        await conn.close()
        
    except Exception as e:
        print(f'❌ 数据库错误: {e}')

asyncio.run(quick_status())
"

echo ""
echo "🌐 服务状态:"
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "   主题服务: \033[92m✅ 运行中\033[0m (http://localhost:8002)"
else
    echo -e "   主题服务: \033[91m❌ 停止\033[0m"
fi

if pgrep -f "python.*processor" > /dev/null; then
    echo -e "   数据处理器: \033[92m✅ 运行中\033[0m"
else
    echo -e "   数据处理器: \033[91m❌ 停止\033[0m"
fi

echo ""
echo "="*70
echo -e "${GREEN}🎯 启动监控面板...${NC}"
echo ""
echo -e "${CYAN}监控面板包含:${NC}"
echo "  📊 实时处理进度和统计"
echo "  ⚡ 活动监控和速度分析"
echo "  🏆 热门主题排行榜"
echo "  📰 系统处理统计"
echo "  🖥️ 系统状态监控"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止监控${NC}"
echo ""

# 启动监控面板
./fixed_dashboard.sh
