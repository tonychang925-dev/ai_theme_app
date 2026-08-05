"""MCP Server — ai_theme_app Market Brain → Julia Core Cognitive Companion.

Exposes 5 read-only tools via MCP protocol.
ai_theme_app owns: facts, evidence, signals.
Julia owns: interpretation, reasoning, companionship.
"""
from __future__ import annotations

from mcp_server.tools.theme_status import query_theme_status
from mcp_server.tools.alerts import list_active_alerts
from mcp_server.tools.snapshot import review_market_snapshot
from mcp_server.tools.subscription import subscribe_agent_channel
from mcp_server.tools.explain import explain_decision

MCP_TOOLS = {
    "query_theme_status": query_theme_status,
    "list_active_alerts": list_active_alerts,
    "review_market_snapshot": review_market_snapshot,
    "subscribe_agent_channel": subscribe_agent_channel,
    "explain_decision": explain_decision,
}

# All tools are READ-ONLY. No execute_order, no modify_strategy.
# This is enforced at the tool level — each tool only reads from the Market Brain.
