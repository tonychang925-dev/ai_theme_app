#!/bin/bash
# 最终版启动脚本

echo "🚀 AI题材引擎 - 最终版系统启动"
echo "="*70

# 检查Python
python3 --version || {
    echo "❌ Python3 未安装"
    exit 1
}

# 检查依赖
echo "🔧 检查依赖..."
python3 -c "import asyncpg" 2>/dev/null || {
    echo "❌ 缺少 asyncpg，正在安装..."
    pip3 install asyncpg
}

# 检查数据库
echo "🔍 检查数据库连接..."
python3 -c "
import asyncio
import sys
sys.path.append('.')
from theme_service.config import settings
import asyncpg

async def check():
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
        print('✅ 数据库连接成功')
        
        # 检查核心表
        tables = await conn.fetch('''
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public'
            AND table_name IN ('news_raw', 'news_event', 'theme_master', 'event_theme_map')
        ''')
        
        if len(tables) == 4:
            print('✅ 所有核心表都存在')
        else:
            print(f'⚠️  缺少某些表，找到 {len(tables)}/4 个表')
        
        # 显示数据量
        for table in ['news_event', 'theme_master', 'event_theme_map']:
            count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
            print(f'   {table}: {count} 条记录')
        
        await conn.close()
        return True
    except Exception as e:
        print(f'❌ 数据库检查失败: {e}')
        return False

success = asyncio.run(check())
if not success:
    exit 1
"

# 启动主题服务（如果未运行）
echo ""
echo "🌐 检查主题服务..."
if ! curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "启动主题服务..."
    cd theme_service
    nohup python3 start_service.py > ../theme_service.log 2>&1 &
    THEME_PID=$!
    cd ..
    
    # 等待启动
    echo "等待服务启动..."
    sleep 5
    
    if curl -s http://localhost:8002/health > /dev/null; then
        echo "✅ 主题服务已启动 (PID: $THEME_PID)"
        echo "   API: http://localhost:8002"
        echo "   日志: theme_service.log"
    else
        echo "❌ 主题服务启动失败"
        exit 1
    fi
else
    echo "✅ 主题服务已在运行"
fi

# 启动数据处理器
echo ""
echo "🔄 启动数据处理器..."
if pgrep -f "final_processor.py" > /dev/null; then
    echo "✅ 数据处理器已在运行"
else
    nohup python3 theme_service/final_processor.py > data_processor.log 2>&1 &
    PROCESSOR_PID=$!
    sleep 2
    
    if ps -p $PROCESSOR_PID > /dev/null; then
        echo "✅ 数据处理器已启动 (PID: $PROCESSOR_PID)"
        echo "   日志: data_processor.log"
        echo "   监控: ./final_monitor.sh"
    else
        echo "❌ 数据处理器启动失败"
        exit 1
    fi
fi

echo ""
echo "="*70
echo "🎉 系统启动完成！"
echo ""
echo "📋 可用命令:"
echo "   查看监控:      ./final_monitor.sh"
echo "   查看处理器日志: tail -f data_processor.log"
echo "   查看服务日志:   tail -f theme_service.log"
echo "   停止所有服务:   pkill -f 'python.*(final_processor|start_service)'"
echo ""
echo "🌐 访问服务:"
echo "   主题服务API: http://localhost:8002"
echo "   API文档:     http://localhost:8002/docs"
echo ""
echo "🔍 验证数据流:"
echo "   1. 在新终端运行: ./final_monitor.sh"
echo "   2. 观察主题如何从新闻事件中自动发现"
echo "   3. 查看映射关系在数据库中建立"
echo ""
echo "✅ Phase 2: 真实数据流集成 已完成！"
