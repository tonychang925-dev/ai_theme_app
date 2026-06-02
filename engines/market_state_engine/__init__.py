"""P2-1: MarketStateEngine facade.

Wraps existing IntradayMinuteStateBuilder.
Facade first — delegates to legacy, no rewrite.
"""
from engines.market_state_engine.service import MarketStateEngine, MarketState

__all__ = ["MarketStateEngine", "MarketState"]
