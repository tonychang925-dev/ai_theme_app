# model_service/app.py
#!/usr/bin/env python3
"""
AI事件抽取服务 - 修复导入版
"""
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Dict, Any
import asyncio
from datetime import datetime
import uvicorn

from .database import DatabaseManager as db_manager
from .services.ai_extractor import ai_extractor

app = FastAPI(title="AI事件抽取服务")

class NewsItem(BaseModel):
    news_id: str
    title: str
    content: str
    source: str
    publish_date: str

class ProcessNewsRequest(BaseModel):
    news_list: List[NewsItem]

@app.on_event("startup")
async def startup_event():
    """启动时初始化"""
    print("🚀 启动 model_service...")
    await db_manager.initialize_db()
    print("✅ 数据库初始化完成")

@app.post("/api/process-news")
async def process_news(request: ProcessNewsRequest, background_tasks: BackgroundTasks):
    """处理新闻列表"""
    print(f"📥 收到处理请求: {len(request.news_list)} 条新闻")
    
    # 异步处理
    background_tasks.add_task(process_news_batch, request.news_list)
    
    return {
        "status": "processing",
        "message": f"开始处理 {len(request.news_list)} 条新闻",
        "received_at": datetime.now().isoformat()
    }

async def process_news_batch(news_list: List[NewsItem]):
    """批量处理新闻"""
    try:
        print(f"🔍 开始AI事件抽取: {len(news_list)} 条新闻")
        
        # 转换为字典列表
        news_dicts = [news.dict() for news in news_list]
        
        # 调用AI抽取器
        events = await ai_extractor.extract_events_from_news(news_dicts)
        
        print(f"✅ AI事件抽取完成: {len(events)} 个事件")
        
        # 保存到数据库
        if events:
            saved_count = await db_manager.save_events(events)
            print(f"💾 数据库保存完成: {saved_count}/{len(events)} 个事件")
        else:
            print("⚠️  没有提取到事件，跳过保存")
        
    except Exception as e:
        print(f"❌ 批处理失败: {e}")
        import traceback
        traceback.print_exc()

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "ai_event_extractor",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/stats")
async def get_stats():
    """获取统计信息"""
    return {
        "service": "AI事件抽取服务",
        "version": "1.0.0",
        "endpoints": [
            {"path": "/api/process-news", "method": "POST", "description": "处理新闻"},
            {"path": "/health", "method": "GET", "description": "健康检查"}
        ]
    }

if __name__ == "__main__":
    print("🚀 启动 AI事件抽取服务")
    print("   地址: http://0.0.0.0:8001")
    print("   API文档: http://0.0.0.0:8001/docs")
    print("   按 Ctrl+C 停止")
    print("--------------------------------------------------")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8001,
        reload=True  # 启用热重载
    )
