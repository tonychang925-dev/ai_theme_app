from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stock_processing_service.application.jobs import (
    BuildDailySnapshotJob,
    BuildIdentityJob,
    BuildMainlineStateJob,
    BuildPostMarketRecapJob,
    BuildPreMarketBriefJob,
    RunQualityGateJob,
    RunReconciliationJob,
)
from stock_processing_service.application.jobs.build_dragon_tiger_object_job import (
    BuildDragonTigerObjectJob,
)
from stock_processing_service.application.jobs.build_auction_watch_universe_job import (
    BuildAuctionWatchUniverseJob,
)
from stock_processing_service.application.jobs.build_tushare_daily_bar_job import (
    BuildTushareDailyBarJob,
)
from stock_processing_service.application.use_cases import BuildStrongStockTrackingUseCase
from stock_processing_service.infrastructure.gateway_adapters.db_stock_object_gateway import DBStockObjectGateway
from stock_processing_service.infrastructure.gateway_adapters.db_theme_data_gateway import DBThemeDataGateway
from stock_processing_service.infrastructure.gateway_adapters.redis_cache_gateway import RedisCacheGateway
from stock_processing_service.infrastructure.gateway_adapters.stock_event_gateway_adapter import (
    StockEventGatewayAdapter,
)
from stock_processing_service.infrastructure.gateway_adapters.stock_idempotency_gateway_adapter import (
    StockIdempotencyGatewayAdapter,
)
from stock_processing_service.ports.database_gateway_stock_facade import DatabaseGatewayStockFacade


@dataclass
class StockProcessingContainer:
    build_strong_stock_tracking: BuildStrongStockTrackingUseCase
    build_daily_snapshot: BuildDailySnapshotJob
    build_mainline_state: Any  # BuildMainlineStateJob
    build_post_market_recap: BuildPostMarketRecapJob
    build_pre_market_brief: BuildPreMarketBriefJob
    build_identity: BuildIdentityJob
    run_quality_gate: RunQualityGateJob
    run_reconciliation: RunReconciliationJob
    build_dragon_tiger_object: BuildDragonTigerObjectJob
    build_tushare_daily_bar: BuildTushareDailyBarJob
    build_auction_watch_universe: BuildAuctionWatchUniverseJob


def build_container(
    db_gateway: DatabaseGatewayStockFacade, cache_client: Any | None = None
) -> StockProcessingContainer:
    theme_data_gateway = DBThemeDataGateway(db_gateway=db_gateway)
    stock_object_gateway = DBStockObjectGateway(db_gateway=db_gateway)
    cache_gateway = RedisCacheGateway(cache_client=cache_client) if cache_client else None
    event_gateway = StockEventGatewayAdapter(db_gateway=db_gateway)
    idempotency_gateway = StockIdempotencyGatewayAdapter(db_gateway=db_gateway)

    return StockProcessingContainer(
        build_strong_stock_tracking=BuildStrongStockTrackingUseCase(
            read_ports=theme_data_gateway,
            write_ports=stock_object_gateway,
            cache_ports=cache_gateway,
        ),
        build_daily_snapshot=BuildDailySnapshotJob(
            read_port=theme_data_gateway,
            write_port=stock_object_gateway,
            event_port=event_gateway,
            idempotency_port=idempotency_gateway,
            cache_port=cache_gateway,
        ),
        build_mainline_state=(
            _mainline_state_job := BuildMainlineStateJob(
                read_port=theme_data_gateway,
                write_port=stock_object_gateway,
                event_port=event_gateway,
            )
        ),
        build_identity=(
            _identity_job := BuildIdentityJob(
                read_port=theme_data_gateway,
                write_port=stock_object_gateway,
                event_port=event_gateway,
                idempotency_port=idempotency_gateway,
            )
        ),
        build_post_market_recap=BuildPostMarketRecapJob(
            read_port=theme_data_gateway,
            write_port=stock_object_gateway,
            event_port=event_gateway,
            idempotency_port=idempotency_gateway,
            cache_port=cache_gateway,
            identity_job=_identity_job,
            mainline_state_job=_mainline_state_job,
        ),
        build_pre_market_brief=BuildPreMarketBriefJob(
            read_port=theme_data_gateway,
            write_port=stock_object_gateway,
            event_port=event_gateway,
            idempotency_port=idempotency_gateway,
            cache_port=cache_gateway,
        ),
        run_quality_gate=RunQualityGateJob(),
        run_reconciliation=RunReconciliationJob(),
        build_dragon_tiger_object=BuildDragonTigerObjectJob(
            write_port=stock_object_gateway,
        ),
        build_tushare_daily_bar=BuildTushareDailyBarJob(
            write_port=stock_object_gateway,
        ),
        build_auction_watch_universe=BuildAuctionWatchUniverseJob(
            read_port=theme_data_gateway,
            write_port=stock_object_gateway,
        ),
    )
