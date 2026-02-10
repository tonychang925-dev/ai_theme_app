#!/usr/bin/env python3
"""
最终启动脚本 - 修复所有问题后
"""
import asyncio
import sys
import os
import logging

# 添加当前目录到路径
sys.path.insert(0, os.getcwd())

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

async def main():
    try:
        print('=' * 60)
        print('🚀 AI题材引擎服务 (修复完成版)')
        print('=' * 60)
        
        # 导入配置
        from theme_service.config import settings
        print('📋 配置信息:')
        print(f'   数据库: {settings.DATABASE_URL[:40]}...')
        print(f'   模式: {settings.INTEGRATION_MODE}')
        print(f'   端口: {settings.PORT}')
        
        # 导入应用
        from theme_service.app import app
        print('\n🌐 Web服务:')
        print(f'   标题: {app.title}')
        print(f'   版本: {app.version}')
        
        # 显示路由
        print('\n📡 可用API端点:')
        routes_by_path = {}
        for route in app.routes:
            if hasattr(route, 'methods') and hasattr(route, 'path'):
                path = route.path
                methods = ','.join(route.methods)
                routes_by_path[path] = methods
        
        for path in sorted(routes_by_path.keys()):
            print(f'   {routes_by_path[path]:8} {path}')
        
        print('\n' + '=' * 60)
        print('✅ 服务准备就绪')
        print('🔄 启动服务器...')
        print('=' * 60)
        print('访问地址: http://localhost:8002')
        print('API文档: http://localhost:8002/docs')
        print('健康检查: http://localhost:8002/health')
        print('按 Ctrl+C 停止服务')
        print('=' * 60)
        
        # 导入 uvicorn
        import uvicorn
        
        # 启动服务器
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=settings.PORT,
            reload=True,  # 开发模式启用热重载
            log_level="info"
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

if __name__ == "__main__":
    # 检查uvicorn是否安装
    try:
        import uvicorn
    except ImportError:
        print('❌ uvicorn 未安装，正在安装...')
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "uvicorn[standard]"])
    
    asyncio.run(main())
