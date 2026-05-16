from __future__ import annotations

from datetime import date

import pytest

from stock_processing_service.application.services.pre_market_brief_builder import PreMarketBriefBuilder


class _ReadGateway:
    def __init__(self, matched=None, review=None):
        self.matched = matched or []
        self.review = review or []

    async def get_intel_news_events(self, feed_date):
        return self.matched

    async def get_pre_market_review_events(self, feed_date, limit=200):
        return self.review[:limit]


class _WriteGateway:
    def __init__(self):
        self.docs = []

    async def upsert_pre_market_brief_snapshot(self, doc, force=False):
        self.docs.append({"doc": doc, "force": force})
        return 1


class _OpportunityBuilder:
    async def build(self, *, trade_date, matched_themes, matched_events):
        return [
            {
                "subject_key": matched_themes[0]["subject_key"],
                "theme_name": matched_themes[0]["theme_name"],
                "stocks": [{"stock_id": "000001.SZ", "level": "A", "score": 86.5}],
            }
        ]


@pytest.mark.asyncio
async def test_pre_market_brief_builder_aggregates_db_events_and_writes_snapshot():
    read = _ReadGateway(
        matched=[
            {
                "item_id": "event:101:theme-a",
                "occurred_at": "2026-05-16T07:30:00",
                "title": "卫星互联网事件",
                "summary": "事件摘要",
                "theme_subject_keys": ["theme-a"],
                "theme_names": ["卫星互联网"],
                "confidence": 0.86,
                "impact_score": 90,
                "source_type": "event_theme_map",
            },
            {
                "item_id": "event:102:theme-a",
                "occurred_at": "2026-05-16T07:40:00",
                "title": "卫星互联网补充事件",
                "summary": "补充摘要",
                "theme_subject_keys": ["theme-a"],
                "theme_names": ["卫星互联网"],
                "confidence": 0.76,
                "impact_score": 70,
                "source_type": "event_theme_map",
            },
        ],
        review=[
            {
                "event_id": 201,
                "title": "待复核事件",
                "summary": "需要人工判断",
                "theme_name": "候选题材",
                "confidence": 0.61,
                "reason": "theme_match_human_review",
            }
        ],
    )
    write = _WriteGateway()
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=write)

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=False)

    assert payload["version"] == "pre_market_brief.v1"
    assert payload["sections"]["event_driven_opportunities"] == []
    assert len(payload["sections"]["major_events"]) == 2
    assert payload["sections"]["matched_themes"] == [
        {
            "subject_key": "theme-a",
            "theme_name": "卫星互联网",
            "event_count": 2,
            "latest_event_title": "卫星互联网补充事件",
            "confidence": 0.86,
            "impact_score": 90.0,
            "event_ids": [101, 102],
        }
    ]
    assert len(payload["sections"]["review_events"]) == 1
    assert payload["diagnostics"]["source"] == "db"
    assert payload["diagnostics"]["matched_event_count"] == 2
    assert len(write.docs) == 1
    assert write.docs[0]["doc"]["payload"] == payload


@pytest.mark.asyncio
async def test_pre_market_brief_builder_falls_back_to_decision_stream_for_unknown_and_review():
    async def _decision_reader(feed_date, limit):
        return [
            {
                "decision_id": "d-match",
                "action": "update_theme",
                "event_id": 301,
                "event_data": {"event_id": 301, "title": "匹配事件", "summary": "ok"},
                "theme_data": {"subject_key": "theme-b", "name": "机器人"},
                "confidence": 0.78,
                "match_result": {"decision": "MATCH"},
            },
            {
                "decision_id": "d-review",
                "action": "human_review",
                "event_id": 302,
                "event_data": {"event_id": 302, "title": "复核事件"},
                "theme_data": {"name": "候选机器人"},
                "confidence": 0.62,
                "match_result": {"decision": "HUMAN_REVIEW"},
            },
            {
                "decision_id": "d-unknown",
                "action": "publish_clustering",
                "event_id": 303,
                "event_data": {"event_id": 303, "title": "未知事件"},
                "match_result": {"decision": "UNKNOWN"},
            },
        ]

    read = _ReadGateway()
    write = _WriteGateway()
    builder = PreMarketBriefBuilder(
        read_gateway=read,
        write_gateway=write,
        decision_stream_reader=_decision_reader,
    )

    payload = await builder.rebuild(date(2026, 5, 16))

    assert payload["diagnostics"]["source"] == "decision_stream_fallback"
    assert len(payload["sections"]["matched_themes"]) == 1
    assert payload["sections"]["review_events"][0]["event_id"] == 302
    assert payload["sections"]["unknown_watch"][0]["event_id"] == 303
    assert {row["risk_type"] for row in payload["sections"]["risk_alerts"]} == {
        "human_review_pending",
        "unknown_event_watch",
    }


@pytest.mark.asyncio
async def test_pre_market_brief_builder_dry_run_does_not_write():
    read = _ReadGateway(
        matched=[
            {
                "item_id": "event:401:theme-c",
                "title": "事件",
                "theme_subject_keys": ["theme-c"],
                "theme_names": ["算力"],
            }
        ]
    )
    write = _WriteGateway()
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=write)

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=True)

    assert payload["diagnostics"]["matched_event_count"] == 1
    assert write.docs == []


@pytest.mark.asyncio
async def test_pre_market_brief_builder_optionally_adds_event_driven_opportunities():
    read = _ReadGateway(
        matched=[
            {
                "item_id": "event:501:theme-a",
                "title": "机器人事件",
                "theme_subject_keys": ["theme-a"],
                "theme_names": ["机器人"],
                "confidence": 0.86,
            }
        ]
    )
    write = _WriteGateway()
    builder = PreMarketBriefBuilder(
        read_gateway=read,
        write_gateway=write,
        opportunity_builder=_OpportunityBuilder(),
    )

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=True)

    assert payload["sections"]["event_driven_opportunities"][0]["stocks"][0]["level"] == "A"
    assert payload["diagnostics"]["opportunity_count"] == 1
