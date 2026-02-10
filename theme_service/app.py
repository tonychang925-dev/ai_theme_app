"""
theme_service FastAPI 应用 - 简化修复版
"""
from fastapi import FastAPI
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("theme_service")

# 创建应用
app = FastAPI(
    title="AI题材引擎服务",
    description="主题发现、热度计算、生命周期管理",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "theme_service",
        "status": "running",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat(),
        "endpoints": [
            {"path": "/", "method": "GET", "description": "服务信息"},
            {"path": "/health", "method": "GET", "description": "健康检查"},
            {"path": "/themes", "method": "GET", "description": "获取主题列表"},
            {"path": "/analyze", "method": "POST", "description": "分析事件"},
            {"path": "/docs", "method": "GET", "description": "API文档"},
            {"path": "/redoc", "method": "GET", "description": "ReDoc文档"}
        ]
    }

@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "theme_service",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/themes")
async def get_themes(limit: int = 10, status: str = "active"):
    """获取主题列表（模拟）"""
    # 模拟数据
    themes = [
        {"id": 1, "name": "AI眼镜", "confidence": 0.85, "status": "active"},
        {"id": 2, "name": "固态电池", "confidence": 0.78, "status": "active"},
        {"id": 3, "name": "人工智能", "confidence": 0.92, "status": "active"}
    ]
    
    filtered = [t for t in themes if t["status"] == status]
    return {"themes": filtered[:limit], "count": len(filtered[:limit])}

@app.post("/analyze")
async def analyze_event(event: dict):
    """分析事件"""
    logger.info(f"分析事件: {event.get('title', '无标题')}")
    
    # 模拟分析结果
    return {
        "event_id": event.get("id"),
        "potential_themes": ["AI眼镜", "消费电子"],
        "confidence": 0.75,
        "processed_at": datetime.now().isoformat()
    }

# 避免导入 scheduler_loop 如果不需要
try:
    from theme_service.scheduler import scheduler_loop
    logger.info("调度器模块可用")
except ImportError as e:
    logger.warning(f"调度器导入失败: {e}")
    # 定义空函数作为回退
    async def scheduler_loop():
        pass

if __name__ == "__main__":
    import uvicorn
    print("启动 theme_service...")
    uvicorn.run(app, host="0.0.0.0", port=8002)
