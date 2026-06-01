import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import logging
from datetime import datetime, date, time
import pandas as pd
import os
import hashlib
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncpg
import re  # 引入正则模块

from news_crawler_service.services.news_crawler_service import get_news_crawler_service

DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"  # 替换为你的数据库连接信息

app = FastAPI()
logger = logging.getLogger(__name__)

CSV_FILE_PATH = "data/stock_cls_telegram.csv"


def normalize_cls_item(news: dict) -> dict:
    """把标准化新闻结构转换成旧的中文字段结构。"""
    return {
        "标题": news.get("title", news.get("标题", "")),
        "内容": news.get("content", news.get("内容", "")),
        "来源": news.get("source", news.get("来源", "财联社")),
        "发布日期": news.get("publish_date", news.get("发布日期", "")),
        "发布时间": news.get("publish_time", news.get("发布时间", "")),
        "市场": news.get("market", news.get("市场", "A股")),
        "URL": news.get("url", news.get("URL", "")),
    }

# 创建数据库连接池
async def get_db_connection():
    return await asyncpg.connect(DATABASE_URL)

# 创建原始新闻表（news_raw）
async def create_news_table():
    connection = await get_db_connection()
    try:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS news_raw (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                content TEXT,
                source VARCHAR(100),
                publish_date DATE,        -- 存储发布日期
                publish_time TIME,        -- 存储发布时间
                market VARCHAR(20),
                url TEXT,
                created_at TIMESTAMP DEFAULT now(),
                news_id TEXT UNIQUE NOT NULL
            );
        """)
    finally:
        await connection.close()

async def save_news_to_db(news_list):
    if not news_list:
        return

    connection = await get_db_connection()
    try:
        for news in news_list:
            # 生成新闻的唯一ID
            news_id = generate_news_id(news)

            # 获取新闻的发布日期和发布时间
            publish_date_str = news.get('发布日期', '')
            publish_time_str = news.get('发布时间', '')

            # 处理发布日期
            if publish_date_str:
                try:
                    publish_date = datetime.strptime(publish_date_str, "%Y-%m-%d").date()  # 确保是日期格式
                except ValueError:
                    logger.warning("Error parsing date: %s", publish_date_str)
                    publish_date = None
            else:
                publish_date = None

            # 处理发布时间
            if publish_time_str:
                # 使用正则表达式检查时间格式是否为 HH:MM:SS
                time_pattern = r"^\d{2}:\d{2}:\d{2}$"  # 确保时间是 HH:MM:SS 格式
                if re.match(time_pattern, publish_time_str):
                    try:
                        publish_time = datetime.strptime(publish_time_str, "%H:%M:%S").time()  # 解析时间格式
                    except ValueError as e:
                        logger.warning("Error parsing publish time: %s", e)
                        publish_time = None  # 如果解析失败，设为 None
                else:
                    logger.warning("Invalid time format: %s", publish_time_str)
                    publish_time = None
            else:
                publish_time = None

            if not publish_time:
                logger.debug("Invalid publish time: %s", publish_time_str)

            # 插入新闻数据到数据库，避免重复
            await connection.execute("""
                INSERT INTO news_raw (title, content, source, publish_date, publish_time, market, url, news_id)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (news_id) DO NOTHING
            """, 
            news.get('标题'), 
            news.get('内容'), 
            news.get('来源'), 
            publish_date,  # 发布日期（转换为 datetime.date 类型）
            publish_time,  # 发布具体时间（转换为 time 类型）
            news.get('市场'), 
            news.get('URL'), 
            news_id
            )
        
        logger.info("Saved %s records to database.", len(news_list))
    except Exception as e:
        logger.exception("Error saving news to DB: %s", e)
    finally:
        await connection.close()

# 生成新闻的唯一ID
def generate_news_id(news):
    title = news.get('标题', '')  # 使用正确的字段名
    date = news.get('发布日期', '')  # 使用正确的字段名
    return hashlib.md5(f"{title}{date}".encode('utf-8')).hexdigest()

@app.get("/cls_telegraph")
async def get_cls_telegraph(symbol: str = "全部", limit: int = 100):
    """CLS 电报接口。

    symbol:
    - `重点`: 默认模式，返回更精简的重要电报
    - `全部`: 返回更完整的页面抓取结果

    limit:
    - 单次返回上限，默认 100，最大 200
    """
    try:
        logger.info("Fetching news for symbol=%s", symbol)
        limit = max(1, min(int(limit), 200))
        service = get_news_crawler_service()
        result = await service.crawl_real_news(symbol=symbol, limit=limit)
        if result.get("status") != "success":
            return JSONResponse(status_code=502, content={"error": result.get("error", "CLS fetch failed")})
        raw_list = (result.get("response") or {}).get("news_list", [])
        news_list = [normalize_cls_item(item) for item in raw_list]
        has_more = bool((result.get("response") or {}).get("has_more", False))
        
        # 格式化日期时间
        for news in news_list:
            for key, value in news.items():
                if isinstance(value, datetime):
                    news[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(value, date):
                    news[key] = value.strftime("%Y-%m-%d")
                elif isinstance(value, time):
                    news[key] = value.strftime("%H:%M:%S")
        
        logger.info(
            "[cls_telegraph] summary symbol=%s limit=%s count=%s has_more=%s",
            symbol,
            limit,
            len(news_list),
            has_more,
        )
        return JSONResponse(content={
            "symbol": symbol,
            "limit": limit,
            "count": len(news_list),
            "has_more": has_more,
            "data": news_list,
        })
    except Exception as e:
        logger.exception("Error in /cls_telegraph: %s", e)
        return JSONResponse(status_code=500, content={"error": str(e)})

async def fetch_cls_telegraph(symbol: str = "全部", limit: int = 100):
    """内部抓取入口，参数语义同 `get_cls_telegraph`。"""
    try:
        logger.info("Fetching news for symbol=%s", symbol)
        limit = max(1, min(int(limit), 200))
        service = get_news_crawler_service()
        result = await service.crawl_real_news(symbol=symbol, limit=limit)
        if result.get("status") != "success":
            logger.warning("Error fetching data: %s", result.get("error", "CLS fetch failed"))
            return []

        raw_list = (result.get("response") or {}).get("news_list", [])
        news_list = [normalize_cls_item(item) for item in raw_list]
        has_more = bool((result.get("response") or {}).get("has_more", False))
        
        # 格式化日期时间
        for news in news_list:
            for key, value in news.items():
                if isinstance(value, datetime):
                    news[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(value, date):
                    news[key] = value.strftime("%Y-%m-%d")
                elif isinstance(value, time):
                    news[key] = value.strftime("%H:%M:%S")
            # 格式化发布日期字段
            if '发布日期' in news and news['发布日期']:
                news['发布日期'] = pd.to_datetime(news['发布日期']).strftime("%Y-%m-%d")

        logger.info(
            "[cls_telegraph] summary symbol=%s limit=%s count=%s has_more=%s",
            symbol,
            limit,
            len(news_list),
            has_more,
        )
        return {
            "symbol": symbol,
            "limit": limit,
            "count": len(news_list),
            "has_more": has_more,
            "data": news_list,
        }
    except Exception as e:
        logger.exception("Error fetching data: %s", e)
        return {
            "symbol": symbol,
            "limit": limit,
            "count": 0,
            "has_more": False,
            "data": [],
        }

async def save_news_to_csv(news_list):
    if not news_list:
        return

    if not os.path.exists(CSV_FILE_PATH):
        for news in news_list:
            news['news_id'] = generate_news_id(news)
        
        df = pd.DataFrame(news_list)
        df.to_csv(CSV_FILE_PATH, index=False)
        logger.info("CSV file created and saved %s records.", len(news_list))
    else:
        try:
            df_existing = pd.read_csv(CSV_FILE_PATH, on_bad_lines='skip')
        except pd.errors.ParserError as e:
            logger.exception("Error reading CSV file: %s", e)
            return

        if 'news_id' not in df_existing.columns:
            df_existing['news_id'] = None

        existing_ids = set(df_existing['news_id'])

        new_news = []
        for news in news_list:
            news_id = generate_news_id(news)
            if news_id not in existing_ids:
                news['news_id'] = news_id
                new_news.append(news)

        if new_news:
            df_new = pd.DataFrame(new_news)
            df_new.to_csv(CSV_FILE_PATH, mode='a', header=False, index=False)
            logger.info("Saved %s new records to CSV.", len(new_news))

async def task_fetch_and_save():
    logger.info("Starting to fetch and save news...")
    payload = await fetch_cls_telegraph(symbol="全部", limit=100)
    news_list = payload.get("data", [])
    if news_list:
        logger.info("Fetched %s news, now saving...", len(news_list))
        await save_news_to_db(news_list)
    else:
        logger.info("No new news to save.")

def schedule_task():
    loop = asyncio.get_event_loop()
    scheduler = BackgroundScheduler()
    
    scheduler.add_job(func=lambda: loop.create_task(task_fetch_and_save()), trigger=IntervalTrigger(minutes=1), max_instances=1)
    scheduler.start()

@app.on_event("startup")
async def on_startup():
    # 创建表
    await create_news_table()  # 确保创建表
    # 启动定时任务
    schedule_task()
    logger.info("Scheduler started. Data collection is running every minute.")



