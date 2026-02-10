#!/bin/bash
# 启动最终监控系统

echo "🚀 启动 AI题材引擎 - 完整监控系统"
echo "="*70

# 检查主题服务
echo "检查主题服务状态..."
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo -e "✅ 主题服务运行正常: http://localhost:8002"
else
    echo -e "❌ 主题服务未运行，正在启动..."
    cd theme_service
    nohup python3 -c "
import uvicorn
from app import app
uvicorn.run(app, host='0.0.0.0', port=8002, log_level='warning')
" > ../theme_service.log 2>&1 &
    cd ..
    sleep 5
fi

# 检查数据处理器
echo ""
echo "检查数据处理器状态..."
if pgrep -f "python.*processor" > /dev/null; then
    echo -e "✅ 数据处理器运行中"
    echo -e "   进程ID: $(pgrep -f 'python.*processor')"
else
    echo -e "⚠️  数据处理器未运行"
    echo -e "   如果需要持续处理，请启动数据处理器"
fi

# 检查数据库
echo ""
echo "检查数据库连接..."
python3 -c "
import asyncio
import asyncpg

async def check_db():
    try:
        conn = await asyncpg.connect('postgresql://postgres:zxbzj~925@localhost/stock_data')
        print('✅ 数据库连接正常')
        
        # 检查数据
        events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
        themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
        mappings = await conn.fetchval('SELECT COUNT(*) FROM event_theme_map')
        
        print(f'   新闻事件: {events}')
        print(f'   投资主题: {themes}')
        print(f'   事件映射: {mappings}')
        
        await conn.close()
    except Exception as e:
        print(f'❌ 数据库连接失败: {e}')

asyncio.run(check_db())
"

echo ""
echo "="*70
echo -e "${GREEN}🎉 启动完整监控面板...${NC}"
echo ""
echo -e "${CYAN}监控面板功能:${NC}"
echo "  📊 实时处理进度和统计"
echo "  ⚡ 活动监控和速度分析"
echo "  🏆 热门主题排行榜"
echo "  📰 最新处理事件"
echo "  🖥️ 系统状态监控"
echo ""
echo -e "${YELLOW}按 Ctrl+C 停止监控${NC}"
echo ""

# 启动监控面板
./final_dashboard.sh
