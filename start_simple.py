#!/usr/bin/env python3
"""
极简启动脚本
"""
import asyncio
from fastapi import FastAPI
import uvicorn

# 创建极简应用
app = FastAPI(title="AI题材引擎", version="1.0.0")

@app.get("/")
async def root():
    return {"service": "theme_service", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/themes")
async def get_themes():
    return {"themes": ["AI眼镜", "固态电池", "人工智能"]}

if __name__ == "__main__":
    print("🚀 启动极简版 theme_service")
    print("   地址: http://localhost:8002")
    print("   端点: /, /health, /themes")
    print("   按 Ctrl+C 停止")
    
    uvicorn.run(app, host="0.0.0.0", port=8002)
