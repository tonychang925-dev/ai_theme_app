"""Tool: market.context.snapshot — Dynamic market facts with runtime DB injection.

Async-safe. Configured via configure_market_context_exporter() at startup.
No pool injection → returns unavailable diagnostic, not silent fallback.
"""

from __future__ import annotations

from datetime import date, datetime, timezone, timedelta

CST = timezone(timedelta(hours=8))

_exporter: object | None = None


def configure_market_context_exporter(exporter) -> None:
    global _exporter
    _exporter = exporter


async def market_context_snapshot(trade_date: str | None = None) -> dict:
    """Return dynamic market context from configured exporter.

    If exporter not configured: returns unavailable diagnostic.
    If exporter configured but DB read fails: returns unavailable + error detail.
    Never silently falls back to hardcoded data.
    """
    if _exporter is None:
        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "status": "unavailable",
            "reason": "exporter_not_configured",
            "market_state": {}, "themes": [], "quality": {"coverage": 0.0, "source_quality": 0.0},
        }

    td = trade_date or datetime.now(CST).strftime("%Y-%m-%d")

    import asyncio
    from stock_processing_service.application.services.analyst_workbench.market_context_exporter import MarketContextExporter

    exporter = _exporter
    try:
        if asyncio.iscoroutinefunction(exporter.export):
            return await exporter.export(td)
        return exporter.export(td)
    except Exception as exc:
        return {
            "schema_version": "market-context.v1",
            "provider": "ai_theme_app",
            "trade_date": td,
            "status": "unavailable",
            "reason": "export_failed",
            "diagnostics": {"error_type": type(exc).__name__, "error": str(exc)},
            "market_state": {}, "themes": [], "quality": {"coverage": 0.0, "source_quality": 0.0},
        }


__all__ = ["market_context_snapshot", "configure_market_context_exporter"]
