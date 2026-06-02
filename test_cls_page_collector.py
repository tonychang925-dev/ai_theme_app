import pytest

from news_crawler_service.collectors.akshare_cls import AkshareClsCollector


SAMPLE_CLS_HTML = """
<html>
  <body>
    2026-05-31 星期日
    <div>05:20【黎巴嫩总理指责以色列实施“焦土政策”】财联社5月31日电，据央视新闻，当地时间30日，黎巴嫩总理萨拉姆发表全国电视讲话，指责以色列在黎南部实施“焦土政策”。</div>
  </body>
</html>
"""

SAMPLE_CLS_HTML_SECOND = """
<html>
  <body>
    2026-05-31 星期日
    <div>05:20【黎巴嫩总理指责以色列实施“焦土政策”】财联社5月31日电，据央视新闻，当地时间30日，黎巴嫩总理萨拉姆发表全国电视讲话，指责以色列在黎南部实施“焦土政策”。</div>
    <div>04:11【美国马萨诸塞州东部地区传出巨响 原因不明】财联社5月31日电，当地时间5月30日午后，美国东北部马萨诸塞州东部多地有居民报告听到一巨大声响，目前声响来源尚不明确，暂无危险报告。</div>
  </body>
</html>
"""


def build_cls_html(message_count: int, start_minute: int = 59) -> str:
    lines = ["<html><body>", "2026-05-31 星期日"]
    for index in range(message_count):
        minute = (start_minute - index) % 60
        hour = 5 - ((start_minute - index) // 60)
        lines.append(
            f'<div>{hour:02d}:{minute:02d}【标题{index + 1}】财联社5月31日电，内容{index + 1}。</div>'
        )
    lines.append("</body></html>")
    return "\n".join(lines)


class FakeResponse:
    def __init__(self, text: str, url: str):
        self.text = text
        self.url = url

    def raise_for_status(self):
        return None


class CountingResponseFactory:
    def __init__(self, html_map):
        self.html_map = html_map
        self.calls = 0

    def __call__(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls += 1
        html = self.html_map["m"] if "m.cls.cn" in url else self.html_map["www"]
        return FakeResponse(html, url)


class AlternatingResponseFactory:
    def __init__(self, first_html_map, second_html_map):
        self.first_html_map = first_html_map
        self.second_html_map = second_html_map
        self.calls = 0

    def __call__(self, url, headers=None, timeout=None, allow_redirects=True):
        self.calls += 1
        html_map = self.first_html_map if self.calls <= 2 else self.second_html_map
        html = html_map["m"] if "m.cls.cn" in url else html_map["www"]
        return FakeResponse(html, url)


@pytest.mark.asyncio
async def test_cls_page_collector_parses_telegraph(monkeypatch):
    collector = AkshareClsCollector(request_interval=0, max_retries=1)

    def fake_get(url, headers=None, timeout=None, allow_redirects=True):
        return FakeResponse(SAMPLE_CLS_HTML, url)

    import news_crawler_service.collectors.akshare_cls as cls_module

    monkeypatch.setattr(cls_module.requests, "get", fake_get)

    items = await collector.fetch()

    assert len(items) == 1
    item = items[0]
    assert item.title == "黎巴嫩总理指责以色列实施“焦土政策”"
    assert "焦土政策" in item.content
    assert item.publish_date.isoformat() == "2026-05-31"
    assert item.publish_time.isoformat().startswith("05:20")
    assert item.source == "akshare_cls"


@pytest.mark.asyncio
async def test_cls_page_health_check(monkeypatch):
    collector = AkshareClsCollector(request_interval=0, max_retries=1)

    def fake_get(url, headers=None, timeout=None, allow_redirects=True):
        return FakeResponse(SAMPLE_CLS_HTML, url)

    import news_crawler_service.collectors.akshare_cls as cls_module

    monkeypatch.setattr(cls_module.requests, "get", fake_get)

    assert await collector.health_check() is True


@pytest.mark.asyncio
async def test_cls_page_collector_merges_and_dedupes(monkeypatch):
    collector = AkshareClsCollector(request_interval=0, max_retries=1)

    def fake_get(url, headers=None, timeout=None, allow_redirects=True):
        if "m.cls.cn" in url:
            return FakeResponse(SAMPLE_CLS_HTML, url)
        return FakeResponse(SAMPLE_CLS_HTML_SECOND, url)

    import news_crawler_service.collectors.akshare_cls as cls_module

    monkeypatch.setattr(cls_module.requests, "get", fake_get)

    items = await collector.fetch()

    assert len(items) == 2
    assert items[0].publish_time.isoformat().startswith("05:20")
    assert items[1].publish_time.isoformat().startswith("04:11")


@pytest.mark.asyncio
async def test_cls_page_collector_uses_cache(monkeypatch):
    collector = AkshareClsCollector(request_interval=0, max_retries=1)
    factory = CountingResponseFactory({"m": SAMPLE_CLS_HTML, "www": SAMPLE_CLS_HTML_SECOND})

    import news_crawler_service.collectors.akshare_cls as cls_module

    monkeypatch.setattr(cls_module.requests, "get", factory)

    first = await collector.fetch()
    second = await collector.fetch()

    assert len(first) == 2
    assert len(second) == 2
    # CDP health check adds 1 extra call per non-cached fetch
    # first: 1 (CDP check) + 2 (HTTP) = 3, second: cache hit = 0
    assert factory.calls == 3


@pytest.mark.asyncio
async def test_cls_page_collector_reuses_cache_when_content_unchanged(monkeypatch):
    collector = AkshareClsCollector(request_interval=0, max_retries=1)
    factory = AlternatingResponseFactory(
        {"m": build_cls_html(40), "www": build_cls_html(40, start_minute=19)},
        {"m": build_cls_html(40), "www": build_cls_html(40, start_minute=19)},
    )

    import news_crawler_service.collectors.akshare_cls as cls_module

    monkeypatch.setattr(cls_module.requests, "get", factory)

    first = await collector.fetch()
    collector._cache_at = 0.0
    second = await collector.fetch()

    assert len(first) == 30
    assert len(second) == 30
    # CDP health check adds 1 extra call per non-cached fetch
    # first: 1 (CDP) + 2 (HTTP) = 3, second: 1 (CDP) + 2 (HTTP) = 3
    assert factory.calls == 6
    assert collector._cache_fingerprint != ""


@pytest.mark.asyncio
async def test_cls_page_collector_symbol_modes(monkeypatch):
    collector = AkshareClsCollector(request_interval=0, max_retries=1)
    factory = CountingResponseFactory(
        {
            "m": build_cls_html(40),
            "www": build_cls_html(40, start_minute=19),
        }
    )

    import news_crawler_service.collectors.akshare_cls as cls_module

    monkeypatch.setattr(cls_module.requests, "get", factory)

    collector.symbol = "重点"
    important = await collector.fetch()

    collector._cache_at = 0.0
    collector._cache_df = collector._cache_df.iloc[0:0]
    collector.symbol = "全部"
    all_items = await collector.fetch()

    assert len(important) == 30
    assert len(all_items) == 60
