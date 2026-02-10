#!/bin/bash
# start_theme_service.sh - 修复启动脚本
echo "🚀 启动 AI题材引擎服务"
echo "====================="

# 检查当前目录
echo "🔍 当前目录: $(pwd)"
echo "🔍 Python版本: $(python --version)"

# 创建启动脚本文件
cat > /tmp/start_service.py << 'PYEOF'
#!/usr/bin/env python3
"""
启动 theme_service
"""
import asyncio
import sys
import os
import logging

# 添加当前目录到路径
current_dir = os.getcwd()
sys.path.insert(0, current_dir)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    try:
        print('=' * 60)
        print('🚀 AI题材引擎服务启动中...')
        print('=' * 60)
        
        # 导入必要的模块
        from theme_service.config import settings
        from theme_service.app import app
        import uvicorn
        
        print('📋 服务配置:')
        print(f'   数据库: {settings.DATABASE_URL[:40]}...')
        print(f'   模式: {settings.INTEGRATION_MODE}')
        print(f'   端口: {settings.PORT}')
        
        print('\n🌐 Web服务信息:')
        print(f'   标题: {app.title}')
        print(f'   版本: {app.version}')
        
        print('\n📡 可用API端点:')
        try:
            for route in app.routes:
                if hasattr(route, 'methods'):
                    methods = ','.join(route.methods)
                    path = route.path
                    print(f'   {methods:8} {path}')
        except:
            print('   默认端点: /, /health, /docs, /redoc')
        
        print('\n' + '=' * 60)
        print('🔄 服务运行中...')
        print('=' * 60)
        print('按 Ctrl+C 停止服务')
        print('访问地址: http://localhost:8002')
        print('API文档: http://localhost:8002/docs')
        print('=' * 60)
        
        # 启动服务器
        config = uvicorn.Config(
            app,
            host='0.0.0.0',
            port=settings.PORT,
            reload=False,
            log_level='info'
        )
        
        server = uvicorn.Server(config)
        await server.serve()
        
    except KeyboardInterrupt:
        print('\n🛑 接收到停止信号')
    except Exception as e:
        print(f'\n❌ 启动失败: {e}')
        import traceback
        traceback.print_exc()
    
    print('\n👋 服务已停止')

if __name__ == '__main__':
    asyncio.run(main())
PYEOF

echo ""
echo "🧪 运行服务..."
cd "$(dirname "$0")"
python /tmp/start_service.py

echo ""
echo "👋 服务已退出"
