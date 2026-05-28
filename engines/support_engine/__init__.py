"""P2-2: SupportEngine facade.

Wraps existing KlineBreakDetector.
Facade first — delegates to legacy, no rewrite.
"""
from engines.support_engine.service import SupportEngine, SupportSignal

__all__ = ["SupportEngine", "SupportSignal"]
