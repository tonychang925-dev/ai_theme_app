"""P1-A 行情采集运行时 — 管理 collector 生命周期."""
from __future__ import annotations

import logging

from stock_processing_service.collectors.jyhf_market_collector import JyhfMarketCollector
from stock_processing_service.sinks.jyhf_market_db_sink import JyhfMarketDbSink
from stock_processing_service.sinks.jyhf_market_redis_pusher import JyhfMarketRedisPusher
from stock_processing_service.integrations.jyhf_market.config import load_config

logger = logging.getLogger("sps.jyhf_market.runtime")

_collector: JyhfMarketCollector | None = None


def get_jyhf_market_collector() -> JyhfMarketCollector:
    global _collector
    if _collector is None:
        config = load_config()
        config.runtime_dir.mkdir(parents=True, exist_ok=True)
        db_sink = JyhfMarketDbSink(config.pg_dsn) if config.allow_push_db else None
        redis_pusher = JyhfMarketRedisPusher(config.redis_url, config.redis_stream_market, config.redis_stream_maxlen) if config.allow_push_redis else None
        _collector = JyhfMarketCollector(config=config, db_sink=db_sink, redis_pusher=redis_pusher)
        logger.info("JyhfMarketCollector created (db=%s redis=%s)", db_sink is not None, redis_pusher is not None)
    return _collector
