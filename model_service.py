import asyncio
import asyncpg
import os
import time
import logging
from fastapi import FastAPI
from openai import OpenAI

# ========================
# 基础配置
# ========================

DATABASE_URL = "postgresql://postgres:zxbzj~925@localhost/stock_data"

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set")

if not DEEPSEEK_API_KEY:
    raise RuntimeError("DEEPSEEK_API_KEY not set")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ========================
# 初始化 LLM Client
# ========================

openai_client = OpenAI(
    api_key=OPENAI_API_KEY
)

deepseek_client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)

# ========================
# FastAPI
# ========================

app = FastAPI()

AVAILABLE_MODELS = ["openai", "deepseek"]
current_model = "deepseek"  # 默认优先 DeepSeek（更省钱）

# ========================
# 模型切换接口
# ========================

@app.get("/set_model")
async def set_model(model: str):
    global current_model
    if model not in AVAILABLE_MODELS:
        return {"error": f"Model must be one of {AVAILABLE_MODELS}"}
    current_model = model
    return {"message": f"Current model set to {model}"}

# ========================
# DB
# ========================

async def get_db_connection():
    return await asyncpg.connect(DATABASE_URL)

async def create_news_event_table():
    conn = await get_db_connection()
    try:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS news_event (
            id SERIAL PRIMARY KEY,
            news_id INT REFERENCES news_raw(id),
            event_type VARCHAR(50),
            impact_industries TEXT[],
            direction VARCHAR(10),
            confidence FLOAT,
            summary TEXT,
            created_at TIMESTAMP DEFAULT now()
        );
        """)
        logger.info("news_event table ready")
    finally:
        await conn.close()

async def fetch_news_data():
    conn = await get_db_connection()
    try:
        rows = await conn.fetch("SELECT id, title, content FROM news_raw")
        return [dict(r) for r in rows]
    finally:
        await conn.close()

async def save_event_to_db(event, news_id):
    conn = await get_db_connection()
    try:
        await conn.execute("""
        INSERT INTO news_event
        (news_id, event_type, impact_industries, direction, confidence, summary)
        VALUES ($1,$2,$3,$4,$5,$6)
        """,
        news_id,
        event["event_type"],
        event["impact_industries"],
        event["direction"],
        event["confidence"],
        event["summary"])
        logger.info(f"Saved event for news {news_id}")
    finally:
        await conn.close()

# ========================
# Prompt & Parser
# ========================

def build_prompt(news):
    return f"""
请从以下新闻中提炼结构化事件信息，并严格按格式输出：

事件类型: <政策 / 技术 / 财报 / 产业 / 资本 / 其他>
影响行业: <逗号分隔>
方向: <利好 / 利空 / 中性>
摘要: <一句话>

标题：{news['title']}
内容：{news['content']}
"""

def parse_event(text: str):
    result = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("事件类型"):
            result["event_type"] = line.split(":",1)[1].strip()
        elif line.startswith("影响行业"):
            result["impact_industries"] = [
                x.strip() for x in line.split(":",1)[1].split(",")
            ]
        elif line.startswith("方向"):
            result["direction"] = line.split(":",1)[1].strip()
        elif line.startswith("摘要"):
            result["summary"] = line.split(":",1)[1].strip()

    if len(result) < 4:
        return None

    result["confidence"] = 0.85
    return result

# ========================
# 核心：AI 理解（含降级）
# ========================

async def ai_understand_event(news):
    prompt = build_prompt(news)
    delay = 5

    for _ in range(3):
        try:
            if current_model == "openai":
                resp = openai_client.chat.completions.create(
                    model="gpt-4.1-mini",
                    messages=[{"role":"user","content":prompt}],
                    temperature=0.2,
                )
                return parse_event(resp.choices[0].message.content)

            if current_model == "deepseek":
                resp = deepseek_client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[{"role":"user","content":prompt}],
                    temperature=0.2,
                )
                return parse_event(resp.choices[0].message.content)

        except Exception as e:
            logger.error(f"{current_model} error: {e}")
            await asyncio.sleep(delay)
            delay *= 2

    return None

# ========================
# 主流程
# ========================

async def process_news():
    news_list = await fetch_news_data()
    for news in news_list:
        logger.info(f"Processing news {news['id']}")
        event = await ai_understand_event(news)
        if event:
            await save_event_to_db(event, news["id"])

async def scheduler():
    while True:
        await process_news()
        await asyncio.sleep(300)

# ========================
# Startup
# ========================

@app.on_event("startup")
async def startup():
    await create_news_event_table()
    asyncio.create_task(scheduler())
    logger.info("model_service started")




