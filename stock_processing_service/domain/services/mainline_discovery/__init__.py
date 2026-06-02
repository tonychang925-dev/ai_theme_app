"""Mainline Discovery — Phase 1 of trading system architecture.

Distinguishes true mainlines from noise/hotspots/rotation themes.
Core principle: dual-threshold confirmation
  logic_score >= 65 AND market_acceptance >= 65 AND leader_alive=true
"""

from .models import (
    MainlineDiscoveryReview,
    MainlineDiscoveryDiagnostics,
    MainlineEvent,
    MainlineEventSeries,
    MainlineLogicEvidence,
    MainlineMarketAcceptance,
    MainlineSubjectBinding,
)

__all__ = [
    "MainlineDiscoveryReview",
    "MainlineDiscoveryDiagnostics",
    "MainlineEvent",
    "MainlineEventSeries",
    "MainlineLogicEvidence",
    "MainlineMarketAcceptance",
    "MainlineSubjectBinding",
]
