#!/bin/bash
# 系统状态检查

echo "🔍 AI题材引擎 - 系统状态检查"
echo "="*60

# 检查服务进程
echo "1. 运行中的服务:"
echo "   -------------------------"

# 主题服务
if pgrep -f "uvicorn.*8002" > /dev/null || pgrep -f "python.*start_service" > /dev/null; then
    echo "   ✅ 主题服务: 运行中"
    echo "      地址: http://localhost:8002"
    echo "      文档: http://localhost:8002/docs"
else
    echo "   ❌ 主题服务: 停止"
fi

# 数据处理器
if pgrep -f "fixed_processor" > /dev/null || pgrep -f "final_processor" > /dev/null; then
    echo "   ✅ 数据处理器: 运行中"
else
    echo "   ❌ 数据处理器: 停止"
fi

# 数据库连接
echo ""
echo "2. 数据库状态:"
echo "   -------------------------"
python3 -c "
import asyncio
import sys
sys.path.append('.')
try:
    from theme_service.config import settings
    import asyncpg
    
    async def db_status():
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            
            # 表统计
            tables = {
                '新闻事件': 'news_event',
                '投资主题': 'theme_master', 
                '事件-主题映射': 'event_theme_map'
            }
            
            for name, table in tables.items():
                try:
                    count = await conn.fetchval(f'SELECT COUNT(*) FROM {table}')
                    print(f'   {name}: {count}')
                except:
                    print(f'   {name}: 表不存在')
            
            # 最近活动
            recent = await conn.fetchval('''
                SELECT COUNT(*) FROM event_theme_map 
                WHERE created_at > NOW() - INTERVAL '10 minutes'
            ''')
            
            if recent > 0:
                print(f'   ⚡ 最近10分钟活动: {recent} 个映射')
            else:
                print(f'   ⏸️  最近10分钟: 无活动')
            
            await conn.close()
            
        except Exception as e:
            print(f'   ❌ 连接失败: {e}')
    
    asyncio.run(db_status())
    
except Exception as e:
    print(f'   ❌ 初始化失败: {e}')
"

# 日志文件
echo ""
echo "3. 日志文件:"
echo "   -------------------------"
for log in "theme_service.log" "processor.log"; do
    if [ -f "$log" ]; then
        size=$(ls -lh "$log" | awk '{print $5}')
        modified=$(date -r "$log" '+%H:%M:%S')
        echo "   $log: $size (最后修改: $modified)"
    else
        echo "   $log: 不存在"
    fi
done

# 系统信息
echo ""
echo "4. 系统信息:"
echo "   -------------------------"
echo "   当前时间: $(date '+%Y-%m-%d %H:%M:%S')"
echo "   运行监控: ./simple_monitor.sh"
echo "   启动系统: ./start_all.sh"
echo "   停止系统: pkill -f 'python.*(uvicorn|processor)'"

echo ""
echo "="*60
echo "📋 总结: 如果所有服务都显示'运行中'，系统正常工作"
