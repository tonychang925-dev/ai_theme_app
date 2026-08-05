"""Tool 4: subscribe_agent_channel — Julia subscribes to domains of interest."""
from __future__ import annotations

from core.contracts.decision_envelope import ChannelState

# In-memory subscription store (Phase 2: migrate to Redis)
_subscriptions: dict[str, set[str]] = {}


def subscribe_agent_channel(channels: list[str], agent_id: str = "julia") -> ChannelState:
    """Subscribe Julia to specific market observation channels.

    Julia subscribes to domains, not individual stocks. E.g.:
      ["AI_AGENT", "SEMICONDUCTOR", "RISK_ALERT"]
    """
    if agent_id not in _subscriptions:
        _subscriptions[agent_id] = set()

    for ch in channels:
        _subscriptions[agent_id].add(ch)

    return ChannelState(
        subscribed=tuple(sorted(_subscriptions[agent_id])),
        active=True,
    )


def unsubscribe_agent_channel(channels: list[str], agent_id: str = "julia") -> ChannelState:
    """Remove channels from subscription."""
    if agent_id in _subscriptions:
        for ch in channels:
            _subscriptions[agent_id].discard(ch)

    return ChannelState(
        subscribed=tuple(sorted(_subscriptions.get(agent_id, set()))),
        active=True,
    )


def get_channels(agent_id: str = "julia") -> ChannelState:
    """Get current subscriptions."""
    return ChannelState(
        subscribed=tuple(sorted(_subscriptions.get(agent_id, set()))),
        active=True,
    )
