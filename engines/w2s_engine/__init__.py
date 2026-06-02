"""P2-3: W2SEngine facade.

Wraps existing W2SUnifiedAlertService.
Facade first — delegates to legacy, no scorer rewrite.
"""
from engines.w2s_engine.service import W2SEngine, W2SSignal

__all__ = ["W2SEngine", "W2SSignal"]
