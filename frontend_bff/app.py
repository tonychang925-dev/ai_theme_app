from contextlib import asynccontextmanager
import asyncio
import json
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse

from frontend_bff.repositories.bff_repository import FrontendBffRepository


bff_repo = FrontendBffRepository()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await bff_repo.initialize()
    try:
        yield
    finally:
        await bff_repo.close()


app = FastAPI(
    title="AI投资助理 Frontend BFF",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "frontend_bff"}


@app.get("/api/intel/feed")
async def get_intel_feed(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return await bff_repo.fetch_intel_feed_view(
        feed_date=date,
        session=session,
        item_type=type,
        subject_key=subject_key,
        stock_id=stock_id,
        limit=limit,
    )


@app.get("/api/intel/stream")
async def get_intel_stream(
    date: Optional[str] = Query(default=None),
    session: str = Query(default="all", pattern="^(all|pre|intra|post)$"),
    type: str = Query(default="all", pattern="^(all|event|theme_move|new_theme|stock_move)$"),
    subject_key: Optional[str] = Query(default=None),
    stock_id: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    async def event_generator():
        seen_item_ids: set[str] = set()
        heartbeat_interval = 15
        poll_interval = 5
        elapsed = 0

        while True:
            try:
                payload = await bff_repo.fetch_intel_feed_view(
                    feed_date=date,
                    session=session,
                    item_type=type,
                    subject_key=subject_key,
                    stock_id=stock_id,
                    limit=limit,
                )
                items = payload.get("items", [])
                fresh_items = []
                for item in items:
                    item_id = str(item.get("item_id") or "")
                    if not item_id or item_id in seen_item_ids:
                        continue
                    seen_item_ids.add(item_id)
                    fresh_items.append(item)

                for item in reversed(fresh_items):
                    body = {
                        "event_id": item.get("item_id"),
                        "occurred_at": item.get("occurred_at"),
                        "event_type": item.get("item_type"),
                        "item": item,
                    }
                    yield f"event: intel_item\ndata: {json.dumps(body, ensure_ascii=False)}\n\n"

                elapsed += poll_interval
                if elapsed >= heartbeat_interval:
                    yield "event: heartbeat\ndata: {\"status\":\"ok\"}\n\n"
                    elapsed = 0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                payload = {"status": "error", "message": str(exc)}
                yield f"event: heartbeat\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            await asyncio.sleep(poll_interval)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/theme-workspace/{subject_key}")
async def get_theme_workspace(
    subject_key: str,
    include_history: bool = Query(default=True),
    include_children: bool = Query(default=True),
    include_stocks: bool = Query(default=True),
    include_leaders: bool = Query(default=False),
    stock_mapping_scope: str = Query(default="pool", pattern="^(pool|leader_overlay|all)$"),
    history_limit: int = Query(default=20, ge=1, le=200),
    children_limit: int = Query(default=50, ge=1, le=500),
    stocks_limit: int = Query(default=50, ge=1, le=500),
):
    payload = await bff_repo.fetch_theme_workspace_view(
        subject_key=subject_key,
        include_history=include_history,
        include_children=include_children,
        include_stocks=include_stocks,
        include_leaders=include_leaders,
        stock_mapping_scope=stock_mapping_scope,
        history_limit=history_limit,
        children_limit=children_limit,
        stocks_limit=stocks_limit,
    )
    if not payload:
        raise HTTPException(status_code=404, detail=f"theme workspace not found for subject_key={subject_key}")
    return payload


@app.get("/api/stock-workspace/{stock_id}")
async def get_stock_workspace(
    stock_id: str,
    include_themes: bool = Query(default=True),
    include_leaders: bool = Query(default=False),
    mapping_scope: str = Query(default="pool", pattern="^(pool|leader_overlay|all)$"),
    themes_limit: int = Query(default=50, ge=1, le=500),
):
    payload = await bff_repo.fetch_stock_workspace_view(
        stock_id=stock_id,
        include_themes=include_themes,
        include_leaders=include_leaders,
        mapping_scope=mapping_scope,
        themes_limit=themes_limit,
    )
    if not payload:
        raise HTTPException(status_code=404, detail=f"stock workspace not found for stock_id={stock_id}")
    return payload


@app.get("/api/recap")
async def get_recap(
    date: str = Query(...),
    report_type: str = Query(default="post_market", pattern="^(pre_market|post_market)$"),
):
    return await bff_repo.fetch_recap_view(
        trade_date=date,
        report_type=report_type,
    )


@app.get("/api/recap/defaults")
async def get_recap_defaults():
    return await bff_repo.fetch_recap_defaults()
