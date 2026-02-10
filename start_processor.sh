#!/bin/bash
# 启动数据处理器

echo "🚀 启动 AI题材引擎数据处理器"
echo "="*60

# 检查环境
python --version || {
    echo "❌ Python未安装"
    exit 1
}

# 检查数据库
echo "🔍 检查数据库连接..."
python -c "
import asyncio
import sys
sys.path.append('.')
from theme_service.config import settings
import asyncpg

async def check():
    try:
        conn = await asyncpg.connect(settings.DATABASE_URL)
        print(f'✅ 数据库连接成功: {settings.DATABASE_URL[:50]}...')
        
        # 检查表
        tables = await conn.fetch('SELECT table_name FROM information_schema.tables WHERE table_schema=\\'public\\'')
        print(f'📊 发现 {len(tables)} 个表')
        
        for table in tables[:5]:
            count = await conn.fetchval(f'SELECT COUNT(*) FROM {table[\"table_name\"]}')
            print(f'  {table[\"table_name\"]}: {count}')
        
        await conn.close()
        return True
    except Exception as e:
        print(f'❌ 数据库连接失败: {e}')
        return False

asyncio.run(check())
" || {
    echo "❌ 数据库检查失败"
    exit 1
}

# 启动处理器
echo ""
echo "🎯 启动数据处理器..."
echo "📋 说明:"
echo "  - 每30秒检查一次新事件"
echo "  - 自动发现投资主题"
echo "  - 按 Ctrl+C 停止"
echo "  - 查看日志: tail -f data_processing.log"
echo ""
echo "开始处理..."
python theme_service/simple_processor.py
