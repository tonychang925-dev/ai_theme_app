from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.infrastructure.gateway_adapters.db_stock_object_gateway import DBStockObjectGateway
from stock_processing_service.infrastructure.gateway_adapters.db_theme_data_gateway import DBThemeDataGateway
from stock_processing_service.infrastructure.gateway_adapters.redis_cache_gateway import RedisCacheGateway
from stock_processing_service.infrastructure.gateway_adapters.redis_event_bus_gateway import RedisEventBusGateway


class _FakeDb:
    async def get_subject_stock_pool_by_trade_date(self, trade_date):
        return [{"trade_date": trade_date, "stock_id": "000001.SZ", "stock_name": "平安银行"}]

    async def get_subject_context_by_subject_keys(self, subject_keys, trade_date):
        return [{"subject_key": subject_keys[0], "trade_date": trade_date}]

    async def get_trade_calendar(self, trade_date):
        return {"trade_date": trade_date, "is_open": True}

    async def get_stock_daily_bars(self, trade_date, stock_ids=None):
        return [{"trade_date": trade_date, "stock_id": (stock_ids or ["000001.SZ"])[0]}]

    async def get_stock_auction_snapshot(self, trade_date, stock_ids=None):
        return [{"trade_date": trade_date, "stock_id": (stock_ids or ["000001.SZ"])[0], "snapshot_type": "daily_proxy"}]

    async def get_prior_stock_daily_snapshots(self, trade_date, lookback_days, stock_ids=None):
        return [{"trade_date": trade_date, "stock_id": "000001.SZ"}]

    async def get_existing_pre_market_brief_snapshot(self, trade_date):
        return {"trade_date": trade_date, "payload": {"k": 1}}

    async def get_existing_post_market_recap_snapshot(self, trade_date):
        return {"trade_date": trade_date, "payload": {"theme_events": [], "stock_abnormal_event_rows": [], "theme_stock_leaderboard_rows": []}}

    async def get_all_active_themes(self, limit=5000):
        return [{"id": 1, "name": "人工智能"}]

    async def upsert_stock_daily_strategy_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_subject_stock_daily_snapshot_rows(self, rows):
        return len(rows)

    async def upsert_stock_abnormal_event_rows(self, rows):
        return len(rows)

    async def upsert_theme_stock_leaderboard_rows(self, rows):
        return len(rows)

    async def upsert_pre_market_brief_snapshot(self, doc):
        return 1

    async def upsert_post_market_recap_snapshot(self, doc):
        return 1


class _FakeCache:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, ex=None):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)
        return 1

    async def invalidate_pattern(self, pattern):
        self.data.clear()
        return 1


class _FakeStream:
    async def publish_to_stream(self, topic, payload):
        return "1-0"

    async def subscribe(self, topic, handler, consumer_group):
        await handler({"topic": topic, "group": consumer_group})


@pytest.mark.asyncio
async def test_db_theme_data_gateway_read_contract():
    adapter = DBThemeDataGateway(db_gateway=_FakeDb())
    rows = await adapter.get_subject_stock_pool_by_trade_date(date(2026, 4, 22))
    assert rows and rows[0]["stock_id"] == "000001.SZ"


@pytest.mark.asyncio
async def test_db_stock_object_gateway_write_contract():
    adapter = DBStockObjectGateway(db_gateway=_FakeDb())
    n = await adapter.upsert_stock_daily_strategy_snapshot_rows(
        [{"trade_date": date(2026, 4, 22), "stock_id": "000001.SZ"}]
    )
    assert n == 1


def test_db_stock_object_gateway_has_no_truth_table_write_method():
    adapter = DBStockObjectGateway(db_gateway=_FakeDb())
    assert not hasattr(adapter, "upsert_stock_daily_snapshot_rows")


@pytest.mark.asyncio
async def test_redis_cache_gateway_contract():
    adapter = RedisCacheGateway(cache_client=_FakeCache())
    await adapter.set("k", {"v": 1}, ttl_seconds=60)
    assert await adapter.get("k") == {"v": 1}
    assert await adapter.delete("k") == 1


@pytest.mark.asyncio
async def test_redis_event_bus_gateway_contract():
    adapter = RedisEventBusGateway(stream_gateway=_FakeStream())
    msg_id = await adapter.publish("stream:test", {"k": 1})
    assert msg_id == "1-0"

    seen = {}

    async def _handler(payload):
        seen.update(payload)

    await adapter.subscribe("stream:test", _handler, "cg1")
    assert seen.get("group") == "cg1"
