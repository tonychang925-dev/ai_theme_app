from .brief_snapshot_dto import BriefSnapshotDTO
from .input_dto import TradeDateInput, WindowInput
from .mainline_context_dto import MainlineCycleDTO, MainlineIdentityDTO
from .output_dto import BuildResult
from .one_to_two_dto import (
    OneToTwoFeatures,
    OneToTwoSetupPlanDTO,
    RuleResult,
    ScoreResult,
    SetupPlanCandidate,
)
from .post_market_setup_context_dto import (
    PostMarketSetupFactContext,
    SetupFactContextBuildError,
    SourceStatus,
)
from .post_market_daily_review_v2 import (
    DailyReviewDiagnostics,
    EvidenceGroup,
    EvidenceItem,
    EvidenceLayerReview,
    ModuleCoverage,
    D1Narrative,
    MarketHotspotOverview,
    MarketHotspotRepresentativeStock,
    MarketHotspotRow,
    MarketHotspotNarrative,
    MarketOverviewNarrative,
    MainlineNarrative,
    PostMarketDailyReviewV2,
)
from .prior_snapshot_dto import PriorSnapshotDTO
from .recap_snapshot_dto import RecapSnapshotDTO
from .stock_auction_dto import StockAuctionDTO
from .stock_bar_dto import StockBarDTO
from .subject_context_dto import SubjectContextDTO
from .subject_event_stats_dto import SubjectEventStatsDTO
from .subject_stock_pool_dto import SubjectStockPoolDTO
from .trade_calendar_dto import TradeCalendarDTO

# Backward-compatible aliases
SnapshotDocDTO = BriefSnapshotDTO
StockDailyBarDTO = StockBarDTO
SubjectStockPoolRowDTO = SubjectStockPoolDTO

__all__ = [
    "TradeDateInput",
    "WindowInput",
    "BuildResult",
    "PostMarketDailyReviewV2",
    "DailyReviewDiagnostics",
    "EvidenceGroup",
    "EvidenceItem",
    "EvidenceLayerReview",
    "ModuleCoverage",
    "D1Narrative",
    "MarketHotspotOverview",
    "MarketHotspotRepresentativeStock",
    "MarketHotspotRow",
    "MarketHotspotNarrative",
    "MarketOverviewNarrative",
    "MainlineNarrative",
    "OneToTwoFeatures",
    "OneToTwoSetupPlanDTO",
    "RuleResult",
    "ScoreResult",
    "SetupPlanCandidate",
    "PostMarketSetupFactContext",
    "SetupFactContextBuildError",
    "SourceStatus",
    "TradeCalendarDTO",
    "StockBarDTO",
    "StockAuctionDTO",
    "SubjectStockPoolDTO",
    "SubjectContextDTO",
    "SubjectEventStatsDTO",
    "PriorSnapshotDTO",
    "BriefSnapshotDTO",
    "RecapSnapshotDTO",
    "MainlineIdentityDTO",
    "MainlineCycleDTO",
    "SnapshotDocDTO",
    "StockDailyBarDTO",
    "SubjectStockPoolRowDTO",
]
