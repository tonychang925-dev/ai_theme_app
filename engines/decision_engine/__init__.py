"""P2-4: DecisionEngine facade.

Combines MarketState / SupportSignal / W2SSignal into
standardized SignalDecision outputs.
Facade only — no scorer rewrite, no production replacement.
"""
from engines.decision_engine.service import DecisionEngine

__all__ = ["DecisionEngine"]
