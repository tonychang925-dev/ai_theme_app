from __future__ import annotations

from stock_processing_service.application.services.akshare_realtime_news_collector import (
    AkShareRealtimeNewsCollector,
)


def test_akshare_realtime_news_collector_builds_replay_compatible_payload():
    collector = AkShareRealtimeNewsCollector(
        redis_url="redis://127.0.0.1:6379/0",
        stream="stream:news:raw",
        run_id="realtime_test",
    )

    payload = collector._normalize_payload(
        {
            "news_id": "n1",
            "title": "算力产业链出现新催化",
            "content": "算力相关公司订单增加。",
            "source": "akshare_cls",
            "publish_date": "2026-05-20",
            "publish_time": "07:30:00",
            "url": "https://example.test/news/1",
        }
    )

    assert payload["news_id"] == "n1"
    assert payload["external_id"] == "n1"
    assert payload["source"] == "akshare_realtime"
    assert payload["source_channel"] == "akshare_realtime"
    assert payload["publish_date"] == "2026-05-20"
    assert payload["publish_time"] == "07:30:00"
    assert payload["run_id"] == "realtime_test"
    assert payload["type"] == "raw_news"
