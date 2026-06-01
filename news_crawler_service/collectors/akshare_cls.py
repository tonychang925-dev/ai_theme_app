# ai_theme_app/news_crawler_service/collectors/akshare_cls.py
import asyncio
import hashlib
import logging
from datetime import datetime, date, time
from html import unescape
from typing import List, Dict, Any, Optional
import re

import pandas as pd
import requests

from ..collectors.base import BaseCollector
from ..models.news_raw import NewsRawItem
from ..config import settings

logger = logging.getLogger(__name__)

CLS_PAGE_URLS = (
    "https://m.cls.cn/telegraph",
    "https://www.cls.cn/telegraph",
)
CLS_MAX_ITEMS = 60
CLS_CACHE_TTL_SECONDS = 60

CLS_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

CLS_ITEM_RE = re.compile(
    r"(?P<time>\d{2}:\d{2})"
    r"【(?P<title>.+?)】"
    r"财联社(?P<month>\d{1,2})月(?P<day>\d{1,2})日电[，,]?"
    r"(?P<content>.*?)(?=(?:\n\d{2}:\d{2}【)|\Z)",
    re.S,
)
CLS_PAGE_DATE_RE = re.compile(r"(?P<year>\d{4})[-/\.年](?P<month>\d{1,2})[-/\.月](?P<day>\d{1,2})")

class AkshareClsCollector(BaseCollector):
    """财联社电报采集器（页面抓取版）"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.symbol = "重点"  # 默认只返回重要电报；"全部" 表示保留更完整的页面结果
        self.last_request_time = 0
        self._cache_at = 0.0
        self._cache_df = pd.DataFrame()
        self._cache_fingerprint = ""
        
    @property
    def source_name(self) -> str:
        return "akshare_cls"
    
    async def fetch(self) -> List[NewsRawItem]:
        """执行抓取任务，返回标准化新闻列表"""
        news_items = []
        
        try:
            # 1. 遵守请求间隔（防反爬）
            await self._respect_request_interval()
            
            # 2. 在线程池中执行同步的akshare调用
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(
                None, 
                self._fetch_cls_page_data
            )
            
            if df is not None and not df.empty:
                # 3. 转换为标准化数据模型
                news_items = await self._convert_to_news_items(df)
                
                logger.info(
                    "[%s] success count=%s symbol=%s request_interval=%s",
                    self.source_name,
                    len(news_items),
                    self._normalize_symbol(),
                    self.request_interval,
                )
            else:
                logger.info("[%s] no data", self.source_name)
                
        except Exception as e:
            logger.exception("[%s] fetch failed: %s", self.source_name, e)
            # 这里可以触发重试或熔断逻辑
            
        return news_items
    
    def _fetch_akshare_data(self) -> pd.DataFrame:
        """兼容旧接口名的同步抓取入口。"""
        return self._fetch_cls_page_data()

    def _fetch_cls_page_data(self) -> pd.DataFrame:
        """抓取 CLS 电报页面并解析为 DataFrame。

        优先使用 CDP (Chrome DevTools Protocol) 方式——可正确渲染 Next.js CSR 页面。
        CDP 不可用时降级到 HTTP 页面抓取。
        """
        now = datetime.now().timestamp()
        # ── 阶段 1: 本地缓存（CDP 和 HTTP 共用）──
        if (
            not self._cache_df.empty
            and (now - self._cache_at) < CLS_CACHE_TTL_SECONDS
        ):
            logger.info("[%s] cache hit rows=%s", self.source_name, len(self._cache_df))
            cached = self._apply_symbol_filter(self._cache_df.copy())
            self._log_snapshot("cache-hit", cached, cached=True)
            return cached

        # ── 阶段 2: CDP 采集（首选）──
        cdp_df = self._try_cdp_fetch()
        if not cdp_df.empty:
            self._cache_at = now
            self._cache_df = cdp_df.copy()
            self._cache_fingerprint = "cdp"
            filtered = self._apply_symbol_filter(cdp_df)
            self._log_snapshot("cdp-fetch", filtered, cached=False)
            return filtered

        # ── 阶段 3: HTTP 页面抓取（降级）──
        logger.info("[%s] CDP unavailable, falling back to HTTP page scraping", self.source_name)
        return self._fetch_cls_page_http()

    def _try_cdp_fetch(self) -> pd.DataFrame:
        """尝试通过 CDP 采集。失败返回空 DataFrame。"""
        try:
            from news_crawler_service.collectors.cls_cdp import ClsCdpCollector

            cdp = ClsCdpCollector()
            limit = 30 if self._normalize_symbol() == "重点" else 60
            df = cdp.fetch_df(limit=limit)
            if df is not None and not df.empty:
                logger.info(
                    "[%s] CDP fetch success rows=%s columns=%s",
                    self.source_name,
                    len(df),
                    list(df.columns),
                )
                return df
            else:
                logger.info("[%s] CDP fetch returned empty", self.source_name)
        except ImportError:
            logger.debug("[%s] CDP module not available", self.source_name)
        except Exception as exc:
            logger.warning("[%s] CDP fetch failed: %s", self.source_name, exc)
        return pd.DataFrame()

    def _fetch_cls_page_http(self) -> pd.DataFrame:
        """HTTP 页面抓取（降级方案）。"""
        now = datetime.now().timestamp()

        frames = []
        page_fingerprints = []
        for url in CLS_PAGE_URLS:
            try:
                response = requests.get(
                    url,
                    headers=CLS_REQUEST_HEADERS,
                    timeout=self.request_interval,
                )
                response.raise_for_status()

                df = self._parse_cls_page(response.text, source_url=response.url)
                page_fingerprints.append(self._fingerprint_text(response.text, response.url))
                if df is not None and not df.empty:
                    logger.info(
                        "[%s] HTTP page fetched url=%s rows=%s columns=%s shape=%s",
                        self.source_name,
                        response.url,
                        len(df),
                        list(df.columns),
                        df.shape,
                    )
                    frames.append(df)
                else:
                    logger.info("[%s] HTTP page parsed empty url=%s", self.source_name, response.url)

            except Exception as e:
                logger.warning("[%s] HTTP fetch url failed url=%s err=%s", self.source_name, url, e)

        if not frames:
            return pd.DataFrame()

        incoming_fingerprint = self._fingerprint_pages(page_fingerprints)
        if (
            self._cache_df is not None
            and not self._cache_df.empty
            and incoming_fingerprint == self._cache_fingerprint
        ):
            self._cache_at = now
            logger.info("[%s] HTTP page unchanged reuse fingerprint cache", self.source_name)
            cached = self._apply_symbol_filter(self._cache_df.copy())
            self._log_snapshot("fingerprint-hit", cached, cached=True)
            return cached

        merged = pd.concat(frames, ignore_index=True)
        merged = self._normalize_cls_frame(merged)
        self._cache_at = now
        self._cache_df = merged.copy()
        self._cache_fingerprint = incoming_fingerprint
        filtered = self._apply_symbol_filter(merged)
        self._log_snapshot("fresh-fetch", filtered, cached=False)
        return filtered

    def _apply_symbol_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        """根据 symbol 语义控制输出范围。"""
        if df.empty:
            return df

        symbol = self._normalize_symbol()
        if symbol == "全部":
            return df.head(CLS_MAX_ITEMS)

        # 重点模式保守截断，避免过多普通电报挤占下游处理能力
        return df.head(min(30, CLS_MAX_ITEMS))

    def _parse_cls_page(self, html_text: str, source_url: str = "") -> pd.DataFrame:
        """将 CLS 页面 HTML 解析为结构化 DataFrame。"""
        text = self._html_to_text(html_text)
        if not text.strip():
            return pd.DataFrame()

        publish_date = self._extract_page_date(text)
        items = []

        for match in CLS_ITEM_RE.finditer(text):
            title = self._clean_text(match.group("title"))
            content = self._clean_text(match.group("content"))
            publish_time = f"{int(match.group('time')[:2]):02d}:{int(match.group('time')[3:5]):02d}"
            month = int(match.group("month"))
            day = int(match.group("day"))
            item_date = publish_date or date.today()
            if item_date.month != month or item_date.day != day:
                try:
                    item_date = date(item_date.year, month, day)
                except ValueError:
                    item_date = publish_date or date.today()

            items.append({
                "标题": title,
                "内容": content or title,
                "发布日期": item_date.isoformat(),
                "发布时间": publish_time,
                "市场": "A股",
                "URL": source_url,
            })

        if items:
            return pd.DataFrame(items)
        return pd.DataFrame()

    def _normalize_cls_frame(self, df: pd.DataFrame) -> pd.DataFrame:
        """排序并去除重复电报。"""
        if df.empty:
            return df

        result = df.copy()
        for col in ("标题", "内容", "发布日期", "发布时间", "市场", "URL"):
            if col not in result.columns:
                result[col] = ""

        result["发布日期"] = result["发布日期"].astype(str)
        result["发布时间"] = result["发布时间"].astype(str)
        result["_sort_key"] = result["发布日期"] + " " + result["发布时间"]
        result = result.drop_duplicates(subset=["标题", "发布日期", "发布时间"], keep="first")
        result = result.sort_values(by=["_sort_key", "标题"], ascending=[False, False])
        result = result.drop(columns=["_sort_key"])
        result = result.reset_index(drop=True)
        return result

    def _html_to_text(self, html_text: str) -> str:
        """提取页面可见文本。"""
        cleaned = re.sub(r"(?is)<(script|style|noscript).*?>.*?</\\1>", "\n", html_text)
        cleaned = re.sub(r"(?i)<br\\s*/?>", "\n", cleaned)
        cleaned = re.sub(r"(?i)</(p|div|li|section|article|h[1-6])>", "\n", cleaned)
        cleaned = re.sub(r"(?is)<[^>]+>", "", cleaned)
        cleaned = unescape(cleaned)
        cleaned = cleaned.replace("\r", "\n")
        lines = [self._clean_text(line) for line in cleaned.split("\n")]
        lines = [line for line in lines if line]
        return "\n".join(lines)

    def _extract_page_date(self, text: str) -> Optional[date]:
        """从页面顶部提取日期。"""
        for line in text.splitlines()[:20]:
            match = CLS_PAGE_DATE_RE.search(line)
            if match:
                try:
                    return date(
                        int(match.group("year")),
                        int(match.group("month")),
                        int(match.group("day")),
                    )
                except ValueError:
                    continue

        today_match = re.search(r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})", text)
        if today_match:
            try:
                return date(
                    int(today_match.group("year")),
                    int(today_match.group("month")),
                    int(today_match.group("day")),
                )
            except ValueError:
                return None
        return None

    def _clean_text(self, value: Any) -> str:
        """统一清理空白与不可见字符。"""
        return re.sub(r"\s+", " ", str(value).replace("\u3000", " ")).strip()

    def _fingerprint_text(self, html_text: str, source_url: str) -> str:
        """生成单页内容指纹。"""
        normalized = self._html_to_text(html_text)
        payload = f"{source_url}\n{normalized}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _fingerprint_pages(self, fingerprints: list[str]) -> str:
        """生成多页合并内容指纹。"""
        payload = "|".join(sorted(fingerprints))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _normalize_symbol(self) -> str:
        """归一化 symbol 输入，保留现有调用兼容性。"""
        raw = self.symbol if self.symbol is not None else "重点"
        text = self._clean_text(raw)
        if text in {"全部", "all", "ALL", "*"}:
            return "全部"
        return "重点"

    def _log_snapshot(self, stage: str, df: pd.DataFrame, cached: bool) -> None:
        """输出结构化采集摘要，便于日志监控。"""
        symbol = self._normalize_symbol()
        summary = {
            "stage": stage,
            "source": self.source_name,
            "symbol": symbol,
            "limit_mode": "full" if symbol == "全部" else "priority",
            "count": int(len(df)) if df is not None else 0,
            "cached": cached,
            "cache_age_sec": round(datetime.now().timestamp() - self._cache_at, 2) if self._cache_at else None,
            "fingerprint": self._cache_fingerprint[:12] if self._cache_fingerprint else "",
        }
        logger.info("[%s] snapshot %s", self.source_name, summary)
    
    async def _convert_to_news_items(self, df: pd.DataFrame) -> List[NewsRawItem]:
        """将DataFrame转换为NewsRawItem列表"""
        news_items = []
        
        for _, row in df.iterrows():
            try:
                # 解析发布日期
                publish_date = self._parse_publish_date(row)
                
                # 解析发布时间
                publish_time = self._parse_publish_time(row)
                
                # 创建标准化新闻对象
                news_item = NewsRawItem(
                    title=str(row.get('标题', '无标题')).strip(),
                    content=str(row.get('内容', '')).strip(),
                    source=self.source_name,
                    publish_date=publish_date,
                    publish_time=publish_time,
                    market=str(row.get('市场', 'A股')),
                    url=str(row.get('URL', '')),
                )
                
                news_items.append(news_item)
                
            except Exception as e:
                logger.warning("[%s] parse row failed: %s", self.source_name, e)
                continue
        
        return news_items
    
    def _parse_publish_date(self, row) -> date:
        """解析发布日期"""
        date_str = str(row.get('发布日期', ''))
        
        if not date_str:
            return date.today()
        
        try:
            # 尝试多种日期格式
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            return date.today()
        except Exception:
            return date.today()
    
    def _parse_publish_time(self, row) -> time:
        """解析发布时间"""
        time_str = str(row.get('发布时间', ''))
        
        if not time_str:
            return time(0, 0, 0)
        
        try:
            # 清理时间字符串
            time_str = time_str.strip()
            
            # 处理常见的时间格式
            if ':' in time_str:
                parts = time_str.split(':')
                if len(parts) >= 2:
                    hour = int(parts[0])
                    minute = int(parts[1])
                    second = int(parts[2]) if len(parts) >= 3 else 0
                    
                    # 验证时间合理性
                    if 0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59:
                        return time(hour, minute, second)
            
            return time(0, 0, 0)
        except Exception:
            return time(0, 0, 0)
    
    async def _respect_request_interval(self):
        """遵守请求间隔，防反爬"""
        current_time = datetime.now().timestamp()
        elapsed = current_time - self.last_request_time
        
        if elapsed < settings.REQUEST_INTERVAL_SECONDS:
            sleep_time = settings.REQUEST_INTERVAL_SECONDS - elapsed
            await asyncio.sleep(sleep_time)
        
        self.last_request_time = datetime.now().timestamp()
    
    async def health_check(self) -> bool:
        """健康检查：测试 CLS 页面是否可抓取。"""
        try:
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, self._fetch_cls_page_data)
            return df is not None and not df.empty
        except Exception:
            return False

# 方便导入的实例
akshare_collector = AkshareClsCollector(
    request_interval=settings.REQUEST_INTERVAL_SECONDS,
    max_retries=settings.MAX_RETRY_TIMES
)
