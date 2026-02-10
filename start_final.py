#!/usr/bin/env python3
"""
启动修复后的完整 theme_service
"""
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

async def start_service():
    print("=" * 60)
    print("🚀 AI题材引擎服务 (theme_service)")
    print("=" * 60)
    print("版本: 1.0.0 (修复完成版)")
    print("模式: 模拟数据模式")
    print("=" * 60)
    
    try:
        # 导入配置
        from theme_service.config import settings
        print(f"📋 配置信息:")
        print(f"   数据库: {settings.DATABASE_URL[:40]}...")
        print(f"   集成模式: {settings.INTEGRATION_MODE}")
        print(f"   服务端口: {settings.PORT}")
        
        # 创建数据处理管道
        print("\n🔧 初始化组件...")
        
        # 1. 初始化AI客户端
        from theme_service.services.ai_client import AIThemeClient
        ai_client = AIThemeClient(settings)
        print("   ✅ AI客户端就绪")
        
        # 2. 初始化主题发现引擎
        from theme_service.services.theme_discovery import ThemeDiscoveryEngine
        discovery_engine = ThemeDiscoveryEngine(ai_client)
        print("   ✅ 主题发现引擎就绪")
        
        # 3. 初始化主题映射器
        from theme_service.services.theme_mapper import ThemeMapper
        theme_mapper = ThemeMapper()
        print("   ✅ 主题映射器就绪")
        
        # 4. 启动FastAPI服务
        import uvicorn
        from theme_service.app import app
        
        print("\n🌐 启动Web服务...")
        print(f"   访问地址: http://localhost:{settings.PORT}")
        print(f"   API文档: http://localhost:{settings.PORT}/docs")
        print("\n📋 可用API端点:")
        print("   GET  /              - 服务信息")
        print("   GET  /health        - 健康检查")
        print("   GET  /api/themes    - 获取主题列表")
        print("\n🔄 服务运行中...")
        print("   按 Ctrl+C 停止")
        print("=" * 60)
        
        # 配置服务器
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=settings.PORT,
            reload=False,
            log_level="info"
        )
        
        server = uvicorn.Server(config)
        
        # 运行服务器
        await server.serve()
        
    except KeyboardInterrupt:
        print("\n🛑 接收到停止信号")
    except Exception as e:
        print(f"\n❌ 启动失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n👋 服务已停止")

if __name__ == "__main__":
    asyncio.run(start_service())
