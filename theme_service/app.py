"""
theme_service FastAPI 应用 - P2.phase1 只读 API 版
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

from theme_service.repositories.phase1_read_repository import Phase1ReadRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("theme_service")

phase1_repo = Phase1ReadRepository()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await phase1_repo.initialize()
    try:
        yield
    finally:
        await phase1_repo.close()

# 创建应用
app = FastAPI(
    title="AI题材引擎服务",
    description="主题发现、热度计算、生命周期管理",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
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
            {"path": "/intel/feed", "method": "GET", "description": "情报流聚合接口"},
            {"path": "/themes", "method": "GET", "description": "获取主题列表"},
            {"path": "/themes/rank", "method": "GET", "description": "题材榜单"},
            {"path": "/themes/{subject_key}", "method": "GET", "description": "题材详情"},
            {"path": "/themes/{subject_key}/children", "method": "GET", "description": "子题材关系"},
            {"path": "/themes/{subject_key}/history", "method": "GET", "description": "题材历史"},
            {"path": "/themes/{subject_key}/stocks", "method": "GET", "description": "题材股票映射"},
            {"path": "/stocks/{stock_id}/themes", "method": "GET", "description": "股票反查题材"},
            {"path": "/api/theme_match", "method": "POST", "description": "主题匹配（调试用）"},
            {"path": "/api/theme_details", "method": "POST", "description": "获取主题详情（调试用）"},
            {"path": "/api/theme_update", "method": "POST", "description": "更新主题字段（调试用）"},
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


@app.get("/intel/feed")
async def get_intel_feed(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    rows = await phase1_repo.fetch_intel_feed(
        feed_date=date,
        session=session,
        item_type=type,
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )
    return {
        "items": rows,
        "count": len(rows),
        "date": date,
        "session": session,
        "type": type,
        "subject_key": subject_key,
        "stock_id": stock_id,
    }

@app.get("/themes")
async def get_themes(
    limit: int = Query(default=50, ge=1, le=500),
    binding_status: Optional[str] = Query(default=None),
):
    rows = await phase1_repo.fetch_theme_list(limit=limit, binding_status=binding_status)
    return {"items": rows, "count": len(rows), "binding_status": binding_status}


@app.get("/themes/rank")
async def get_theme_rank(
    limit: int = Query(default=50, ge=1, le=500),
    rank_date: Optional[str] = None,
):
    rows = await phase1_repo.fetch_rank(limit=limit, rank_date=rank_date)
    return {"items": rows, "count": len(rows), "rank_date": rank_date}


@app.get("/themes/{subject_key}/children")
async def get_theme_children(
    subject_key: str,
    relation_type: Optional[str] = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
):
    rows = await phase1_repo.fetch_children(
        subject_key=subject_key,
        relation_type=relation_type,
        limit=limit,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"children not found for subject_key={subject_key}")
    return {
        "subject_key": subject_key,
        "relation_type": relation_type,
        "items": rows,
        "count": len(rows),
    }


@app.get("/themes/{subject_key}/history")
async def get_theme_history(
    subject_key: str,
    limit: int = Query(default=100, ge=1, le=1000),
):
    rows = await phase1_repo.fetch_history(subject_key=subject_key, limit=limit)
    if not rows:
        raise HTTPException(status_code=404, detail=f"history not found for subject_key={subject_key}")
    return {"subject_key": subject_key, "items": rows, "count": len(rows)}


@app.get("/themes/{subject_key}")
async def get_theme_detail(subject_key: str):
    row = await phase1_repo.fetch_theme_detail(subject_key=subject_key)
    if not row:
        raise HTTPException(status_code=404, detail=f"theme not found for subject_key={subject_key}")
    return row


@app.get("/themes/{subject_key}/stocks")
async def get_theme_stocks(
    subject_key: str,
    mapping_scope: str = Query(default="pool", pattern="^(pool|leader_overlay|all)$"),
    include_leaders: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
):
    rows = await phase1_repo.fetch_stocks_by_theme(
        subject_key=subject_key,
        mapping_scope=mapping_scope,
        include_leaders=include_leaders,
        limit=limit,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"stocks not found for subject_key={subject_key}")
    return {
        "subject_key": subject_key,
        "mapping_scope": mapping_scope,
        "include_leaders": include_leaders,
        "items": rows,
        "count": len(rows),
    }


@app.get("/stocks/{stock_id}/themes")
async def get_stock_themes(
    stock_id: str,
    mapping_scope: str = Query(default="pool", pattern="^(pool|leader_overlay|all)$"),
    include_leaders: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=1000),
):
    rows = await phase1_repo.fetch_themes_by_stock(
        stock_id=stock_id,
        mapping_scope=mapping_scope,
        include_leaders=include_leaders,
        limit=limit,
    )
    if not rows:
        raise HTTPException(status_code=404, detail=f"themes not found for stock_id={stock_id}")
    return {
        "stock_id": stock_id,
        "mapping_scope": mapping_scope,
        "include_leaders": include_leaders,
        "items": rows,
        "count": len(rows),
    }

@app.post("/api/theme_match")
async def theme_match(payload: Dict[str, Any]):
    """
    主题匹配端点 - 模拟匹配功能

    为了支持实时链路调试，提供简单的主题匹配功能。
    实际项目中应该使用完整的主题匹配引擎。
    """
    try:
        # 从payload中提取参数
        event_data = payload.get("event_data", {})
        limit = payload.get("limit", 5)

        # 模拟主题匹配逻辑
        event_title = event_data.get("title", "")
        event_content = event_data.get("content", "")
        event_keywords = event_data.get("keywords", [])

        # 简单的关键词匹配逻辑
        matched_themes = []

        # 模拟匹配一些主题
        if any(kw in event_title.lower() for kw in ["ai", "人工智能", "智能"]):
            matched_themes.append({
                "theme_id": 1001,
                "name": "人工智能",
                "confidence": 0.85,
                "match_type": "keyword",
                "matched_keywords": ["AI", "人工智能"]
            })

        if any(kw in event_title.lower() for kw in ["电池", "新能源", "储能"]):
            matched_themes.append({
                "theme_id": 1002,
                "name": "固态电池",
                "confidence": 0.78,
                "match_type": "keyword",
                "matched_keywords": ["电池", "新能源"]
            })

        if any(kw in event_title.lower() for kw in ["眼镜", "ar", "增强现实"]):
            matched_themes.append({
                "theme_id": 1003,
                "name": "AI眼镜",
                "confidence": 0.72,
                "match_type": "keyword",
                "matched_keywords": ["眼镜", "AR"]
            })

        # 限制返回数量
        matched_themes = matched_themes[:limit]

        logger.info(f"主题匹配成功: 事件 '{event_title[:50]}...' 匹配到 {len(matched_themes)} 个主题")

        return {
            "matched_themes": matched_themes,
            "event_id": event_data.get("id", "unknown"),
            "request_id": event_data.get("request_id", "unknown"),
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"主题匹配异常: {e}")
        raise HTTPException(status_code=500, detail=f"主题匹配失败: {str(e)}")

@app.post("/api/theme_details")
async def theme_details(theme_ids: List[int]):
    """
    获取主题详情
    """
    try:
        themes = []
        for theme_id in theme_ids:
            # 模拟主题详情
            if theme_id == 1001:
                themes.append({
                    "theme_id": 1001,
                    "name": "人工智能",
                    "description": "人工智能技术及应用",
                    "status": "active",
                    "created_at": "2024-01-01T00:00:00",
                    "keywords": ["AI", "人工智能", "机器学习", "深度学习"]
                })
            elif theme_id == 1002:
                themes.append({
                    "theme_id": 1002,
                    "name": "固态电池",
                    "description": "固态电池技术及产业链",
                    "status": "active",
                    "created_at": "2024-01-01T00:00:00",
                    "keywords": ["电池", "新能源", "储能", "固态电池"]
                })
            elif theme_id == 1003:
                themes.append({
                    "theme_id": 1003,
                    "name": "AI眼镜",
                    "description": "AI眼镜及增强现实技术",
                    "status": "active",
                    "created_at": "2024-01-01T00:00:00",
                    "keywords": ["眼镜", "AR", "增强现实", "智能穿戴"]
                })
            else:
                themes.append({
                    "theme_id": theme_id,
                    "name": f"主题{theme_id}",
                    "description": "模拟主题",
                    "status": "active",
                    "created_at": datetime.now().isoformat(),
                    "keywords": ["模拟"]
                })

        return {"themes": themes}

    except Exception as e:
        logger.error(f"获取主题详情异常: {e}")
        raise HTTPException(status_code=500, detail=f"获取主题详情失败: {str(e)}")

@app.post("/api/theme_update")
async def theme_update(theme_id: int, updates: Dict[str, Any]):
    """
    更新主题字段
    """
    try:
        logger.info(f"主题更新: theme_id={theme_id}, updates={updates}")
        return {
            "success": True,
            "theme_id": theme_id,
            "updated_fields": list(updates.keys()),
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"主题更新异常: {e}")
        raise HTTPException(status_code=500, detail=f"主题更新失败: {str(e)}")

@app.post("/analyze")
async def analyze_event(event: dict):
    raise HTTPException(status_code=501, detail="analyze endpoint is not enabled in P2.phase1 read-only mode")

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
