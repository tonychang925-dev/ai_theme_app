from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NotionPublishResult:
    page_id: str
    page_url: str
    action: str
    report_id: str
    report_type: str
    trade_date: str
