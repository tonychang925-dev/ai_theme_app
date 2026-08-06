"""Tool: market.context.snapshot — Dynamic market facts from real data.

Binds to MarketContextExporter → DerivedContextReader (real DB data).
status: live / partial / unavailable. No hardcoded sample data.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))


def market_context_snapshot(trade_date: str | None = None) -> dict:
    td = trade_date or datetime.now(CST).strftime("%Y-%m-%d")
    from stock_processing_service.application.services.analyst_workbench.market_context_exporter import (
        MarketContextExporter,
    )
    return MarketContextExporter().export(td)


__all__ = ["market_context_snapshot"]
