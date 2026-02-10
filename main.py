from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def read_root():
    return {"message": "AI题材系统已启动"}

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict
from collections import Counter
import re
import jieba

app = FastAPI()

class NewsItem(BaseModel):
    title: str
    content: str

class AnalyzeRequest(BaseModel):
    news: List[NewsItem]

class AnalyzeResponse(BaseModel):
    hotspots: Dict[str, int]

def simple_keyword_extraction(text: str) -> List[str]:
    # 用jieba分词，过滤长度小于2的词
    words = [w for w in jieba.cut(text) if len(w) >= 2]
    return words

@app.post("/analyze_news", response_model=AnalyzeResponse)
def analyze_news(req: AnalyzeRequest):
    all_keywords = []
    for item in req.news:
        all_keywords.extend(simple_keyword_extraction(item.title + " " + item.content))
    counter = Counter(all_keywords)
    # 取出现频率最高的10个词作为热点关键词
    hotspots = dict(counter.most_common(10))
    return AnalyzeResponse(hotspots=hotspots)

import requests
from fastapi import FastAPI

app = FastAPI()

NEWS_API_KEY = "你的API_KEY"
NEWS_API_URL = "https://newsapi.org/v2/top-headlines"

@app.get("/fetch_news")
def fetch_news(country: str = "us", category: str = "business"):
    params = {
        "apiKey": NEWS_API_KEY,
        "country": country,
        "category": category,
        "pageSize": 10  # 返回10条新闻
    }
    resp = requests.get(NEWS_API_URL, params=params)
    data = resp.json()
    if data.get("status") != "ok":
        return {"error": "无法获取新闻"}
    articles = data.get("articles", [])
    # 返回标题和内容简要
    news_list = [{"title": art["title"], "content": art.get("description") or ""} for art in articles]
    return {"news": news_list}
