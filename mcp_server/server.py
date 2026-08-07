"""MCP Server — ai_theme_app Market Brain → Julia Core Cognitive Companion.

Exposes 7 read-only tools via MCP protocol:
  - Fact layer: market.context.snapshot (market facts, no interpretation)
  - Judgment layer: market.workbench.review (workbench interpretation to verify)
  - Intelligence layer: review_market_snapshot, list_active_alerts (approved conclusions)
  - Legacy: query_theme_status, subscribe_agent_channel, explain_decision

ai_theme_app owns: facts, evidence, signals.
Julia owns: interpretation, reasoning, independent judgment.
"""
from __future__ import annotations

from mcp_server.tools.theme_status import query_theme_status
from mcp_server.tools.alerts import list_active_alerts
from mcp_server.tools.snapshot import review_market_snapshot
from mcp_server.tools.subscription import subscribe_agent_channel
from mcp_server.tools.explain import explain_decision
from mcp_server.tools.market_context import market_context_snapshot
from mcp_server.tools.workbench_review import market_workbench_review
from mcp_server.tools.research_tools import (
    market_stock_history,
    market_stock_auction,
    market_theme_constituents,
    market_theme_capital,
    market_regime_read,
)

MCP_TOOLS = {
    # ── Fact layer ──
    "market_context_snapshot": market_context_snapshot,

    # ── Judgment layer ──
    "market_workbench_review": market_workbench_review,

    # ── Research layer (M3.2.7) ──
    "market_stock_history": market_stock_history,
    "market_stock_auction": market_stock_auction,
    "market_theme_constituents": market_theme_constituents,
    "market_theme_capital": market_theme_capital,
    "market_regime_read": market_regime_read,

    # ── Intelligence layer ──
    "review_market_snapshot": review_market_snapshot,
    "list_active_alerts": list_active_alerts,

    # ── Legacy ──
    "query_theme_status": query_theme_status,
    "subscribe_agent_channel": subscribe_agent_channel,
    "explain_decision": explain_decision,
}

# All tools are READ-ONLY. No execute_order, no modify_strategy.
# This is enforced at the tool level — each tool only reads from the Market Brain.
