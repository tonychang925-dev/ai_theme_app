#!/bin/bash
# 检查系统状态

echo "🔍 AI题材引擎 - 系统状态检查"
echo "="*60

# 1. 检查进程
echo "1. 检查运行进程:"
if pgrep -f "python.*(start_service|fixed_start_service)" > /dev/null; then
    echo "   ✅ 主题服务: 运行中"
    THEME_PID=$(pgrep -f "python.*(start_service|fixed_start_service)")
    echo "      进程ID: $THEME_PID"
else
    echo "   ❌ 主题服务: 未运行"
fi

if pgrep -f "python.*(final_processor|fixed_processor)" > /dev/null; then
    echo "   ✅ 数据处理器: 运行中"
    PROCESSOR_PID=$(pgrep -f "python.*(final_processor|fixed_processor)")
    echo "      进程ID: $PROCESSOR_PID"
else
    echo "   ❌ 数据处理器: 未运行"
fi

# 2. 检查服务端口
echo ""
echo "2. 检查服务端口:"
if curl -s http://localhost:8002/health > /dev/null 2>&1; then
    echo "   ✅ 主题服务API: 可访问 (http://localhost:8002)"
    echo "      文档: http://localhost:8002/docs"
else
    echo "   ❌ 主题服务API: 不可访问"
fi

# 3. 检查数据库
echo ""
echo "3. 检查数据库连接和数据:"
python3 -c "
import asyncio
import sys
sys.path.append('.')
try:
    from theme_service.config import settings
    import asyncpg
    
    async def check_data():
        try:
            conn = await asyncpg.connect(settings.DATABASE_URL)
            
            # 基础统计
            events = await conn.fetchval('SELECT COUNT(*) FROM news_event')
            themes = await conn.fetchval('SELECT COUNT(*) FROM theme_master')
            mappings = await conn.fetchval('SELECT COUNT(*) FROM event_theme_map')
            
            print(f'   新闻事件总数: {events}')
            print(f'   投资主题总数: {themes}')
            print(f'   事件-主题映射: {mappings}')
            
            if events > 0:
                processed = await conn.fetchval('SELECT COUNT(DISTINCT event_id) FROM event_theme_map')
                progress = (processed / events * 100)
                print(f'   处理进度: {progress:.1f}% ({processed}/{events})')
            
            # 最近活动
            recent = await conn.fetchval('''
                SELECT COUNT(*) FROM event_theme_map 
                WHERE created_at > NOW() - INTERVAL '10 minutes'
            ''')
            
            if recent > 0:
                print(f'   ✅ 数据流正常: 最近10分钟处理了 {recent} 个映射')
            else:
                print(f'   ⚠️  最近10分钟无新活动')
            
            await conn.close()
            
        except Exception as e:
            print(f'   ❌ 数据库错误: {e}')
    
    asyncio.run(check_data())
    
except ImportError as e:
    print(f'   ❌ 导入失败: {e}')
"

# 4. 检查日志
echo ""
echo "4. 检查日志文件:"
for log_file in "theme_service.log" "data_processor.log"; do
    if [ -f "$log_file" ]; then
        size=$(ls -lh "$log_file" | awk '{print $5}')
        lines=$(wc -l < "$log_file")
        echo "   📝 $log_file: $size, $lines 行"
    else
        echo "   ❌ $log_file: 不存在"
    fi
done

echo ""
echo "="*60
echo "📋 总结:"
echo "   如果看到'数据流正常'，说明系统工作正常！"
echo "   运行 ./final_monitor.sh 查看实时监控"
