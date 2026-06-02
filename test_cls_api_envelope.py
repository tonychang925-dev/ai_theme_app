import importlib
import sys
import types

from fastapi.testclient import TestClient


apscheduler_module = types.ModuleType("apscheduler")
schedulers_module = types.ModuleType("apscheduler.schedulers")
background_module = types.ModuleType("apscheduler.schedulers.background")
triggers_module = types.ModuleType("apscheduler.triggers")
interval_module = types.ModuleType("apscheduler.triggers.interval")


class DummyBackgroundScheduler:
    def add_job(self, *args, **kwargs):
        return None

    def start(self):
        return None


class DummyIntervalTrigger:
    def __init__(self, *args, **kwargs):
        return None


background_module.BackgroundScheduler = DummyBackgroundScheduler
interval_module.IntervalTrigger = DummyIntervalTrigger
schedulers_module.background = background_module
triggers_module.interval = interval_module
apscheduler_module.schedulers = schedulers_module
apscheduler_module.triggers = triggers_module

sys.modules.setdefault("apscheduler", apscheduler_module)
sys.modules.setdefault("apscheduler.schedulers", schedulers_module)
sys.modules.setdefault("apscheduler.schedulers.background", background_module)
sys.modules.setdefault("apscheduler.triggers", triggers_module)
sys.modules.setdefault("apscheduler.triggers.interval", interval_module)

app_module = importlib.import_module("app")


class FakeNewsCrawlerService:
    async def crawl_real_news(self, symbol: str = "重点", limit: int = 10):
        return {
            "status": "success",
            "response": {
                "news_count": 2,
                "has_more": True,
                "news_list": [
                    {
                        "title": "电报A",
                        "content": "内容A",
                        "source": "akshare_cls",
                        "publish_date": "2026-05-31",
                        "publish_time": "05:20:00",
                        "market": "A股",
                        "url": "https://m.cls.cn/telegraph",
                    },
                    {
                        "title": "电报B",
                        "content": "内容B",
                        "source": "akshare_cls",
                        "publish_date": "2026-05-31",
                        "publish_time": "05:19:00",
                        "market": "A股",
                        "url": "https://www.cls.cn/telegraph",
                    },
                ],
            },
        }


class LimitAwareFakeNewsCrawlerService:
    def __init__(self):
        self.calls = []
        self.items = [
            {
                "title": "电报A",
                "content": "内容A",
                "source": "akshare_cls",
                "publish_date": "2026-05-31",
                "publish_time": "05:20:00",
                "market": "A股",
                "url": "https://m.cls.cn/telegraph",
            },
            {
                "title": "电报B",
                "content": "内容B",
                "source": "akshare_cls",
                "publish_date": "2026-05-31",
                "publish_time": "05:19:00",
                "market": "A股",
                "url": "https://www.cls.cn/telegraph",
            },
        ]

    async def crawl_real_news(self, symbol: str = "重点", limit: int = 10):
        self.calls.append({"symbol": symbol, "limit": limit})
        limited = self.items[:limit]
        return {
            "status": "success",
            "response": {
                "news_count": len(limited),
                "has_more": len(self.items) > limit,
                "news_list": limited,
            },
        }


def test_cls_telegraph_response_envelope(monkeypatch):
    monkeypatch.setattr(app_module, "get_news_crawler_service", lambda: FakeNewsCrawlerService())

    client = TestClient(app_module.app)
    response = client.get("/cls_telegraph", params={"symbol": "全部", "limit": 2})

    assert response.status_code == 200
    payload = response.json()

    assert payload["symbol"] == "全部"
    assert payload["limit"] == 2
    assert payload["count"] == 2
    assert payload["has_more"] is True
    assert len(payload["data"]) == 2
    assert payload["data"][0]["标题"] == "电报A"
    assert payload["data"][0]["发布日期"] == "2026-05-31"


def test_cls_telegraph_limit_boundary(monkeypatch):
    service = LimitAwareFakeNewsCrawlerService()
    monkeypatch.setattr(app_module, "get_news_crawler_service", lambda: service)

    client = TestClient(app_module.app)
    response = client.get("/cls_telegraph", params={"symbol": "重点", "limit": 1})

    assert response.status_code == 200
    payload = response.json()

    assert service.calls == [{"symbol": "重点", "limit": 1}]
    assert payload["symbol"] == "重点"
    assert payload["limit"] == 1
    assert payload["count"] == 1
    assert payload["has_more"] is True
    assert len(payload["data"]) == 1
    assert payload["data"][0]["标题"] == "电报A"


def test_cls_telegraph_logs_summary(monkeypatch, caplog):
    monkeypatch.setattr(app_module, "get_news_crawler_service", lambda: FakeNewsCrawlerService())

    client = TestClient(app_module.app)
    with caplog.at_level("INFO"):
        response = client.get("/cls_telegraph", params={"symbol": "全部", "limit": 2})

    assert response.status_code == 200
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "[cls_telegraph] summary" in messages
    assert "symbol=全部" in messages
    assert "limit=2" in messages
    assert "count=2" in messages
    assert "has_more=True" in messages
