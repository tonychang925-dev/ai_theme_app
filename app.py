import asyncio
from fastapi import FastAPI
from fastapi.responses import JSONResponse
import akshare as ak
import traceback
from datetime import datetime, date, time
import pandas as pd
import os
import hashlib
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import asyncpg
import re  # 引入正则模块

DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"  # 替换为你的数据库连接信息

app = FastAPI()

CSV_FILE_PATH = "data/stock_cls_telegram.csv"

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
                    print(f"Error parsing date: {publish_date_str}")
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
                        print(f"Error parsing publish time: {e}")
                        publish_time = None  # 如果解析失败，设为 None
                else:
                    print(f"Invalid time format: {publish_time_str}")
                    publish_time = None
            else:
                publish_time = None

            if not publish_time:
                print(f"Invalid publish time: {publish_time_str}")  # 添加日志以便调试

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
        
        print(f"Saved {len(news_list)} records to database.")
    except Exception as e:
        print(f"Error saving news to DB: {e}")
    finally:
        await connection.close()

# 生成新闻的唯一ID
def generate_news_id(news):
    title = news.get('标题', '')  # 使用正确的字段名
    date = news.get('发布日期', '')  # 使用正确的字段名
    return hashlib.md5(f"{title}{date}".encode('utf-8')).hexdigest()

@app.get("/cls_telegraph")
async def get_cls_telegraph(symbol: str = "全部"):
    try:
        print("Fetching news for symbol:", symbol)  # Added debug print
        df = ak.stock_info_global_cls(symbol=symbol)
        news_list = df.to_dict(orient="records")
        
        # 格式化日期时间
        for news in news_list:
            for key, value in news.items():
                if isinstance(value, datetime):
                    news[key] = value.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(value, date):
                    news[key] = value.strftime("%Y-%m-%d")
                elif isinstance(value, time):
                    news[key] = value.strftime("%H:%M:%S")
        
        print("News fetched:", len(news_list))  # Debug print
        return JSONResponse(content={"data": news_list})
    except Exception as e:
        error_message = traceback.format_exc()
        print("Error:", error_message)
        return JSONResponse(status_code=500, content={"error": str(e)})

async def fetch_cls_telegraph(symbol: str = "全部"):
    try:
        print(f"Fetching news for symbol: {symbol}")  # Debug print
        df = ak.stock_info_global_cls(symbol=symbol)
        
        # 输出列名来检查数据结构
        print("Columns in the fetched DataFrame:", df.columns)

        news_list = df.to_dict(orient="records")
        
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
            if '发布日期' in news:
                news['发布日期'] = pd.to_datetime(news['发布日期']).strftime("%Y-%m-%d")

        print(f"Fetched {len(news_list)} news records.")  # Debug print
        return news_list
    except Exception as e:
        print("Error fetching data:", e)
        return []

async def save_news_to_csv(news_list):
    if not news_list:
        return

    if not os.path.exists(CSV_FILE_PATH):
        for news in news_list:
            news['news_id'] = generate_news_id(news)
        
        df = pd.DataFrame(news_list)
        df.to_csv(CSV_FILE_PATH, index=False)
        print(f"CSV file created and saved {len(news_list)} records.")
    else:
        try:
            df_existing = pd.read_csv(CSV_FILE_PATH, on_bad_lines='skip')
        except pd.errors.ParserError as e:
            print(f"Error reading CSV file: {e}")
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
            print(f"Saved {len(new_news)} new records to CSV.")

async def task_fetch_and_save():
    print("Starting to fetch and save news...")
    news_list = await fetch_cls_telegraph(symbol="全部")
    if news_list:
        print(f"Fetched {len(news_list)} news, now saving...")
        await save_news_to_db(news_list)
    else:
        print("No new news to save.")

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
    print("Scheduler started. Data collection is running every minute.")










