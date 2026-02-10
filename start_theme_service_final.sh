#!/bin/bash
# start_theme_service_final.sh - 最终启动脚本
echo "🚀 启动 AI题材引擎服务 (最终版)"
echo "=============================="

# 检查环境
echo "🔍 环境检查..."
python --version

# 运行快速测试
echo ""
echo "🧪 运行快速测试..."
python -c "
import sys
sys.path.insert(0, '.')

print('快速导入测试:')
tests = [
    ('theme_service.config.settings', '配置'),
    ('theme_service.database.ThemeDatabase', '数据库'),
    ('theme_service.services.ai_client.AIThemeClient', 'AI客户端'),
    ('theme_service.services.theme_discovery.ThemeDiscoveryEngine', '主题发现'),
    ('theme_service.app.app', 'FastAPI应用'),
]

all_passed = True
for import_path, name in tests:
    try:
        exec(f'import {import_path.split(\".\")[0]}')
        print(f'  ✅ {name}')
    except Exception as e:
        print(f'  ❌ {name}: {str(e)[:50]}...')
        all_passed = False

if all_passed:
    print('\\n🎉 所有模块导入成功！')
else:
    print('\\n⚠️  有模块导入失败')
    sys.exit(1)
"

# 启动服务
echo ""
echo "🚀 启动服务..."
echo "   访问地址: http://localhost:8002"
echo "   API文档: http://localhost:8002/docs"
echo "   按 Ctrl+C 停止"
echo ""

cd "$(dirname "$0")"

python -c "
import asyncio
import sys
import os
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
        
        print('\\n🌐 Web服务信息:')
        print(f'   标题: {app.title}')
        print(f'   版本: {app.version}')
        
        print('\\n📡 可用API端点:')
        for route in app.routes:
            if hasattr(route, 'methods'):
                methods = ','.join(route.methods)
                path = route.path
                print(f'   {methods:8} {path}')
        
        print('\\n' + '=' * 60)
        print('🔄 服务运行中...')
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
        print('\\n🛑 接收到停止信号')
    except Exception as e:
        print(f'\\n❌ 启动失败: {e}')
        import traceback
        traceback.print_exc()
    
    print('\\n👋 服务已停止')

if __name__ == '__main__':
    asyncio.run(main())
"

echo ""
echo "👋 服务已退出"
