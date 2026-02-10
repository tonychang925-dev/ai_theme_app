#!/usr/bin/env python3
"""
启动 AI事件抽取服务
"""
import uvicorn
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from model_service.config import settings

if __name__ == "__main__":
    print(f"🚀 启动 AI事件抽取服务")
    print(f"   地址: http://{settings.HOST}:{settings.PORT}")
    print(f"   API文档: http://{settings.HOST}:{settings.PORT}/docs")
    print("   按 Ctrl+C 停止")
    print("-" * 50)
    
    uvicorn.run(
        "model_service.app:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=True
    )
