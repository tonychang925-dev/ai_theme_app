#!/bin/bash
# 修复版启动脚本

echo "🚀 AI题材引擎 - 启动数据流集成系统"
echo "="*70

# 检查Python
if ! python3 --version > /dev/null 2>&1; then
    echo "❌ Python3 未安装"
    exit 1
fi
echo "✅ Python3: $(python3 --version)"

# 检查依赖
echo "🔧 检查Python依赖..."
python3 -c "import asyncpg" > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "正在安装 asyncpg..."
    pip3 install asyncpg
    if [ $? -ne 0 ]; then
        echo "❌ asyncpg 安装失败"
        exit 1
    fi
fi
echo "✅ asyncpg 已安装"

# 检查数据库连接
echo "🔍 测试数据库连接..."
python3 -c "
import asyncio
import sys
sys.path.append('.')
try:
    from theme_service.config import settings
    import asyncpg
    
    async def test_db():
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            print('✅ 数据库连接成功')
            
            # 简单查询测试
            events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
            themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
            print(f'   新闻事件: {events}')
            print(f'   投资主题: {themes}')
            
            await conn.close()
            return True
        except Exception as e:
            print(f'❌ 数据库连接失败: {e}')
            return False
    
    success = asyncio.run(test_db())
    if not success:
        sys.exit(1)
        
except ImportError as e:
    print(f'❌ 导入失败: {e}')
    sys.exit(1)
"

if [ $? -ne 0 ]; then
    echo "❌ 数据库检查失败"
    exit 1
fi

# 启动主题服务
echo ""
echo "🌐 启动主题服务..."
cd theme_service
nohup python3 start_service.py > ../theme_service.log 2>&1 &
THEME_PID=$!
cd ..

# 等待服务启动
echo "等待主题服务启动（5秒）..."
sleep 5

# 检查服务是否启动
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "✅ 主题服务已启动 (PID: $THEME_PID)"
    echo "   API地址: http://localhost:8002"
else
    echo "❌ 主题服务启动失败，检查日志: tail -f theme_service.log"
    exit 1
fi

# 启动数据处理器
echo ""
echo "🔄 启动数据处理器..."
cd theme_service
nohup python3 final_processor.py > ../data_processor.log 2>&1 &
PROCESSOR_PID=$!
cd ..

# 等待处理器启动
sleep 2

if ps -p $PROCESSOR_PID > /dev/null 2>&1; then
    echo "✅ 数据处理器已启动 (PID: $PROCESSOR_PID)"
    echo "   处理日志: data_processor.log"
else
    echo "❌ 数据处理器启动失败，检查日志: tail -f data_processor.log"
    exit 1
fi

echo ""
echo "="*70
echo "🎉 系统启动成功！"
echo ""
echo "📋 下一步操作:"
echo "   1. 查看实时监控: ./final_monitor.sh"
echo "   2. 查看处理日志: tail -f data_processor.log"
echo "   3. 访问主题服务: http://localhost:8002"
echo "   4. 查看API文档: http://localhost:8002/docs"
echo ""
echo "🛑 停止系统: ./stop_system.sh"
echo ""
echo "✅ Phase 2: 数据流集成 已完成！"
