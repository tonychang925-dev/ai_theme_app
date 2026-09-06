"""AT-R2 deterministic adapter operations.

No transport, MCP registration, Julia import, or natural-language routing.
"""

from .alerts import MarketAlertsOperation
from .event_read import MarketEventReadOperation
from .snapshot import MarketSnapshotOperation

__all__ = ["MarketAlertsOperation", "MarketEventReadOperation", "MarketSnapshotOperation"]
