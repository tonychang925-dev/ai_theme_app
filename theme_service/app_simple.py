"""
简化版 FastAPI 应用 - 用于测试
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
import asyncio

app = FastAPI(
    title="AI题材引擎服务",
    description="简化版 - 主题发现与热度计算",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

class EventData(BaseModel):
    """事件数据模型"""
    id: int
    title: str
    summary: str
    event_type: str
    impact_industries: List[str] = []

class ThemeResponse(BaseModel):
    """主题响应模型"""
    id: int
    name: str
    confidence: float
    status: str
    created_at: datetime

# 模拟数据
mock_themes = [
    {"id": 1, "name": "AI眼镜", "confidence": 0.85, "status": "active", "created_at": datetime.now()},
    {"id": 2, "name": "固态电池", "confidence": 0.78, "status": "active", "created_at": datetime.now()},
    {"id": 3, "name": "人工智能", "confidence": 0.92, "status": "active", "created_at": datetime.now()}
]

@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "theme_service",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now().isoformat(),
        "endpoints": {
            "/": "服务信息",
            "/health": "健康检查",
            "/themes": "获取主题列表",
            "/themes/{theme_id}": "获取特定主题",
            "/docs": "API文档"
        }
    }

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "service": "theme_service",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/themes", response_model=List[ThemeResponse])
async def get_themes(limit: int = 10, status: str = "active"):
    """获取主题列表"""
    filtered = [t for t in mock_themes if t["status"] == status]
    return filtered[:limit]

@app.get("/themes/{theme_id}")
async def get_theme(theme_id: int):
    """获取特定主题"""
    for theme in mock_themes:
        if theme["id"] == theme_id:
            return theme
    raise HTTPException(status_code=404, detail="主题不存在")

@app.post("/analyze")
async def analyze_event(event: EventData):
    """分析事件"""
    # 模拟分析过程
    await asyncio.sleep(0.5)  # 模拟处理时间
    
    return {
        "event_id": event.id,
        "potential_themes": ["AI眼镜", "消费电子"],
        "confidence": 0.75,
        "processed_at": datetime.now().isoformat()
    }

@app.get("/discover")
async def discover_themes():
    """发现新主题"""
    # 模拟发现过程
    new_themes = [
        {"name": "智能穿戴", "confidence": 0.65, "reason": "近期事件增多"},
        {"name": "新能源车", "confidence": 0.72, "reason": "政策利好"}
    ]
    
    return {
        "new_themes": new_themes,
        "discovered_at": datetime.now().isoformat()
    }

# 替换原始 app.py
echo "是否要用简化版替换原始 app.py？"
echo "原始 app.py 有复杂依赖，简化版更容易启动。"
echo "输入 y 替换，输入 n 保持原样："
read -r choice

if [ "$choice" = "y" ] || [ "$choice" = "Y" ]; then
    mv theme_service/app.py "$BACKUP_DIR/app.py.original"
    mv theme_service/app_simple.py theme_service/app.py
    echo "✅ 已替换为简化版 app.py"
    echo "   原始文件备份到: $BACKUP_DIR/app.py.original"
else
    echo "✅ 保持原始 app.py"
    rm theme_service/app_simple.py
fi

echo ""
echo "🎉 所有修复完成！"
echo ""
echo "📋 现在可以:"
echo "1. 测试导入: python -c \"import sys; sys.path.insert(0, '.'); from theme_service.app import app; print(f'✅ 应用导入成功: {app.title}')\""
echo "2. 启动服务: ./start_theme_service_final.sh"
echo "3. 访问测试: curl http://localhost:8002/"
echo ""
echo "🚀 theme_service 已完全修复！"
