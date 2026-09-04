"""Deterministic Market fixture passing through production M1A/M1B seams."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta

from stock_processing_service.application.services.julia_domain_adapter import DomainIntelligenceAdapter
from stock_processing_service.application.services.julia_domain_adapter.contracts import AdapterRequest

CST = timezone(timedelta(hours=8))


class FixedClock:
    def now(self):
        return datetime(2026, 9, 4, 11, 30, tzinfo=CST)


class MarketGatewayFixture:
    def __init__(self, *, event="default", relations="default", event_error=None, relation_error=None):
        self.event = self._event() if event == "default" else event
        self.relations = [self._relation()] if relations == "default" else relations
        self.event_error = event_error
        self.relation_error = relation_error
        self.event_calls = []
        self.relation_calls = []

    async def get_news_event_for_match(self, event_id):
        self.event_calls.append(event_id)
        if self.event_error is not None:
            raise self.event_error
        return self.event

    async def get_event_subject_mappings_by_event_ids(self, event_ids):
        self.relation_calls.append(event_ids)
        if self.relation_error is not None:
            raise self.relation_error
        return self.relations

    def _event(self):
        return {
            "id": 501,
            "news_id": 901,
            "source_category": "news",
            "event_type": "product_launch",
            "summary": "Company released a new product.",
            "direction": 1,
            "confidence": 0.88,
            "source_trace_id": "news_event:901:product_launch",
            "event_time": datetime(2026, 9, 3, 9, 30, tzinfo=CST),
            "created_at": datetime(2026, 9, 3, 9, 31, tzinfo=CST),
            "entities": None,
            "causal_claim": None,
            "evidence_set": None,
            "raw_event_json": {},
            "title": "Company released a new product",
            "content": "Company released a new product",
            "source_name": "source-a",
            "source_url": "https://trusted.example/page",
            "publish_date": datetime(2026, 9, 3).date(),
            "publish_time": None,
        }

    def _relation(self):
        return {
            "id": 1,
            "event_id": 501,
            "news_id": 901,
            "subject_key": "ar_glasses",
            "subject_name": "AR Glasses",
            "relation_type": "primary",
            "confidence": 0.93,
            "match_reason": "product maps to subject",
            "evidence_json": {"summary": "new product"},
            "source": "theme_match_engine",
            "source_trace_id": "trace-map-1",
            "run_id": "run-map-1",
            "created_at": datetime(2026, 9, 3, 9, 35, tzinfo=CST),
            "updated_at": datetime(2026, 9, 3, 9, 36, tzinfo=CST),
        }


def read_market_event(gateway):
    adapter = DomainIntelligenceAdapter(database_gateway=gateway, clock=FixedClock())
    return asyncio.run(adapter.execute(AdapterRequest(
        operation="market.event.read",
        arguments={"event_id": 501},
        correlation_id="corr-market-f1",
        idempotency_key="idem-market-f1",
        requested_at="2026-09-04T11:29:00+08:00",
        schema_version="1.0",
    )))


def partial_event_gateway():
    gateway = MarketGatewayFixture()
    gateway.event["source_name"] = None
    return gateway


def relation_failure_gateway():
    return MarketGatewayFixture(event_error=None, relation_error=ConnectionError("relation table unavailable"))
