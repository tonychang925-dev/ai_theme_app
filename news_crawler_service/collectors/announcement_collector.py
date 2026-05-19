# ai_theme_app/news_crawler_service/collectors/announcement_collector.py
"""
Phase 6A: 一手公告采集器

直接从巨潮资讯 (cninfo) HTTP API 抓取沪深京 A 股公告。
只负责抓取 + 标准化，不写入数据库。

职责边界：
  Collector 只负责：抓取 + 标准化 → 输出 RawIntelDocumentDTO dict list
  Collector 不负责：入库、去重、写 DB（由 RawIntelIngestionService 负责）

数据源：
  巨潮资讯 hisAnnouncement/query 接口，覆盖沪深京全部 A 股公告。

MVP 限制：
  - 只抓标题、公告类型、股票代码、股票名称、发布时间、PDF URL
  - 不做 PDF 下载/解析
  - 默认抓取最近 1 天，默认最多 30 页（900 条）
"""

import asyncio
import hashlib
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_PDF_BASE = "http://static.cninfo.com.cn/"
DEFAULT_PAGE_SIZE = 30
DEFAULT_MAX_PAGES = 30  # MVP 上限：30 页 × 30 条 = 900 条公告
DEFAULT_DAYS_BACK = 1

# UTC+8 时区
TZ_CN = timezone(timedelta(hours=8))


class AnnouncementCollector:
    """巨潮资讯公告采集器（MVP：只抓标题/类型/PDF链接）。

    用法：
        collector = AnnouncementCollector()
        docs = await collector.collect(days_back=1)
        # docs 是 dict list，每个 dict 对应 raw_intel_document 一行
    """

    def __init__(
        self,
        max_pages: int = DEFAULT_MAX_PAGES,
        page_size: int = DEFAULT_PAGE_SIZE,
        request_timeout: int = 30,
    ):
        self.max_pages = int(max_pages)
        self.page_size = int(page_size)
        self.request_timeout = int(request_timeout)

    # ---- 公开方法 ----------------------------------------------------------

    async def collect(self, days_back: int = DEFAULT_DAYS_BACK) -> List[Dict[str, Any]]:
        """增量抓取最近 N 天公告，返回 RawIntelDocumentDTO dict list。

        Args:
            days_back: 往前抓取天数，默认 1 天。

        Returns:
            list[dict]: 每个 dict 包含 raw_intel_document 所需字段。
        """
        end_date = date.today()
        start_date = end_date - timedelta(days=max(int(days_back), 1))

        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        logger.info(
            "AnnouncementCollector 开始抓取: %s ~ %s, max_pages=%s",
            start_str,
            end_str,
            self.max_pages,
        )

        # 在线程池中执行同步 HTTP 请求
        loop = asyncio.get_event_loop()
        raw_items = await loop.run_in_executor(
            None,
            self._fetch_all_pages,
            start_str,
            end_str,
        )

        # 标准化为 raw_intel_document dict
        docs: List[Dict[str, Any]] = []
        for item in raw_items:
            doc = self._standardize(item)
            if doc:
                docs.append(doc)

        logger.info("AnnouncementCollector 完成: 原始 %s 条, 标准化 %s 条", len(raw_items), len(docs))
        return docs

    # ---- 静态工具方法 ------------------------------------------------------

    @staticmethod
    def build_dedupe_key(source_system: str, source_type: str, source_id: str) -> str:
        """构建去重键：{source_system}:{source_type}:{source_id}"""
        return f"{source_system}:{source_type}:{source_id}"

    @staticmethod
    def compute_checksum(title: str, stock_code: str, publish_time: str) -> str:
        """内容校验：md5(title + stock_code + publish_time)"""
        raw = f"{title or ''}|{stock_code or ''}|{publish_time or ''}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    # ---- 内部方法 ----------------------------------------------------------

    def _fetch_all_pages(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        """同步抓取所有分页（在线程池中执行）。"""
        payload = {
            "pageNum": "1",
            "pageSize": str(self.page_size),
            "column": "szse",
            "tabName": "fulltext",
            "plate": "",
            "stock": "",
            "searchkey": "",
            "secid": "",
            "category": "",
            "trade": "",
            "seDate": f"{start_date}~{end_date}",
            "sortName": "",
            "sortType": "",
            "isHLtitle": "true",
        }

        all_items: List[Dict[str, Any]] = []

        # 第一页：获取总数
        try:
            r = requests.post(
                CNINFO_QUERY_URL,
                data=payload,
                timeout=self.request_timeout,
            )
            r.raise_for_status()
            data = r.json()
        except Exception as exc:
            logger.error("cninfo 第一页请求失败: %s", exc)
            return all_items

        total = int(data.get("totalAnnouncement", 0))
        if total == 0:
            logger.info("cninfo: 日期范围内无公告 %s ~ %s", start_date, end_date)
            return all_items

        total_pages = min(
            (total + self.page_size - 1) // self.page_size,
            self.max_pages,
        )
        page_items = data.get("announcements") or []
        all_items.extend(page_items)

        logger.info("cninfo: total=%s, pages=%s (上限%s)", total, total_pages, self.max_pages)

        # 后续页面
        for page in range(2, total_pages + 1):
            payload["pageNum"] = str(page)
            try:
                r = requests.post(
                    CNINFO_QUERY_URL,
                    data=payload,
                    timeout=self.request_timeout,
                )
                r.raise_for_status()
                page_data = r.json()
                page_items = page_data.get("announcements") or []
                all_items.extend(page_items)
            except Exception as exc:
                logger.warning("cninfo 第 %s 页请求失败: %s", page, exc)
                continue

        return all_items

    def _standardize(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """将 cninfo API 原始条目转换为 raw_intel_document dict。"""
        sec_code = str(item.get("secCode") or "").strip()
        sec_name = str(item.get("secName") or "").strip()
        title = str(item.get("announcementTitle") or "").strip()
        ann_time_raw = item.get("announcementTime")

        if not title:
            return None
        if not sec_code:
            return None

        # 解析公告时间（Unix 毫秒）
        publish_time = None
        publish_time_str = ""
        if ann_time_raw:
            try:
                ts = float(ann_time_raw) / 1000.0
                publish_time = datetime.fromtimestamp(ts, tz=TZ_CN)
                publish_time_str = publish_time.isoformat()
            except (ValueError, TypeError, OSError):
                pass

        # 构建 PDF URL
        adjunct_url = str(item.get("adjunctUrl") or "").strip()
        pdf_url = ""
        if adjunct_url:
            pdf_url = f"{CNINFO_PDF_BASE}{adjunct_url}"

        # 公告类型
        ann_type = item.get("announcementType")
        ann_type_name = str(item.get("announcementTypeName") or "").strip()

        # source_id：优先使用 announcementId，fallback 到 URL/标题 hash
        source_id = str(item.get("announcementId") or "")
        if not source_id:
            source_id = hashlib.md5(
                f"{sec_code}:{title}:{publish_time_str}".encode("utf-8")
            ).hexdigest()

        source_system = "cninfo"
        source_type = "announcement"

        # 检测市场
        market = self._detect_market(sec_code)

        doc: Dict[str, Any] = {
            "source_system": source_system,
            "source_type": source_type,
            "source_id": source_id,
            "source_url": "",
            "publish_time": publish_time,
            "fetch_time": datetime.now(TZ_CN),
            "market": market,
            "stock_code": sec_code,
            "stock_name": sec_name,
            "company_name": str(item.get("orgName") or sec_name).strip(),
            "title": title,
            "content_text": "",
            "content_html": "",
            "pdf_url": pdf_url,
            "pdf_path": "",
            "doc_type": "announcement",
            "doc_subtype": "",
            "announcement_type": ann_type_name or str(ann_type or ""),
            "report_period": "",
            "checksum": self.compute_checksum(title, sec_code, publish_time_str),
            "dedupe_key": self.build_dedupe_key(source_system, source_type, source_id),
            "parse_status": "raw",
            "llm_status": "pending",
            "stream_status": "pending",
        }
        return doc

    @staticmethod
    def _detect_market(sec_code: str) -> str:
        """根据股票代码前缀判断市场。"""
        if not sec_code:
            return ""
        code = sec_code.strip()
        if code.startswith(("60", "68")):
            return "SH"
        elif code.startswith(("00", "30", "002", "003", "300", "301")):
            return "SZ"
        elif code.startswith(("4", "8")):
            return "BJ"
        return ""
