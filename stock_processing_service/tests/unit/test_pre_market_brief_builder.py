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

    async def get_pre_market_review_events(self, feed_date, limit=200, start_at=None, end_at=None):
        return self.review[:limit]


class _WriteGateway:
    def __init__(self):
        self.docs = []

    async def upsert_pre_market_brief_snapshot(self, doc, force=False):
        self.docs.append({"doc": doc, "force": force})
        return 1


class _ZeroWriteGateway(_WriteGateway):
    async def upsert_pre_market_brief_snapshot(self, doc, force=False):
        self.docs.append({"doc": doc, "force": force})
        return 0


class _UnverifiedWriteGateway(_WriteGateway):
    async def get_pre_market_brief_snapshot(self, trade_date):
        return None


class _SubjectReadGateway(_ReadGateway):
    def __init__(self, subject_events=None, fallback_matched=None, review=None):
        super().__init__(matched=fallback_matched, review=review)
        self.subject_events = subject_events or []
        self.used_subject_events = False
        self.used_legacy_events = False

    async def get_pre_market_subject_events(self, feed_date, source=None, limit=200, start_at=None, end_at=None):
        self.used_subject_events = True
        return self.subject_events[:limit]

    async def get_intel_news_events(self, feed_date):
        self.used_legacy_events = True
        return await super().get_intel_news_events(feed_date)


class _OpportunityBuilder:
    async def build(self, *, trade_date, matched_themes, matched_events):
        return [
            {
                "subject_key": matched_themes[0]["subject_key"],
                "theme_name": matched_themes[0]["theme_name"],
                "stocks": [{"stock_id": "000001.SZ", "level": "A", "score": 86.5}],
            }
        ]


class _IntelAnnouncementGateway(_ReadGateway):
    async def get_intel_announcement_events(
        self,
        feed_date,
        limit=200,
        matched_only=False,
        start_time=None,
        end_time=None,
    ):
        rows = [
            {
                "event_id": 701,
                "stock_code": "000001",
                "stock_name": "平安银行",
                "title": "重大合同公告",
                "summary": "签署重大合同",
                "event_type": "major_contract",
                "event_level": "important",
                "publish_time": "2026-05-15T16:00:00+08:00",
                "confidence": 0.8,
                "impact_score": 80,
                "theme_matched": True,
                "matched_subjects": [{"subject_key": "theme-a", "subject_name": "机器人"}],
                "source_trace_id": "trace-a",
            },
            {
                "event_id": 702,
                "stock_code": "000002",
                "stock_name": "万科A",
                "title": "普通公告",
                "summary": "普通事项",
                "event_type": "other",
                "event_level": "normal",
                "publish_time": "2026-05-15T17:00:00+08:00",
                "confidence": 0.6,
                "impact_score": 30,
                "theme_matched": False,
                "matched_subjects": [],
                "source_trace_id": "trace-b",
            },
        ]
        if matched_only:
            rows = [row for row in rows if row["theme_matched"]]
        return rows[:limit]


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
async def test_pre_market_brief_builder_fails_when_snapshot_write_affects_zero_rows():
    read = _ReadGateway(
        matched=[
            {
                "item_id": "event:101:theme-a",
                "title": "卫星互联网事件",
                "theme_subject_keys": ["theme-a"],
                "theme_names": ["卫星互联网"],
            }
        ]
    )
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=_ZeroWriteGateway())

    with pytest.raises(RuntimeError, match="write skipped or failed"):
        await builder.rebuild(date(2026, 5, 16), dry_run=False)


@pytest.mark.asyncio
async def test_pre_market_brief_builder_fails_when_snapshot_write_cannot_be_read_back():
    read = _ReadGateway(
        matched=[
            {
                "item_id": "event:101:theme-a",
                "title": "卫星互联网事件",
                "theme_subject_keys": ["theme-a"],
                "theme_names": ["卫星互联网"],
            }
        ]
    )
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=_UnverifiedWriteGateway())

    with pytest.raises(RuntimeError, match="write verification failed"):
        await builder.rebuild(date(2026, 5, 16), dry_run=False)


@pytest.mark.asyncio
async def test_pre_market_brief_builder_prefers_event_subject_map_rows():
    read = _SubjectReadGateway(
        subject_events=[
            {
                "event_id": 501,
                "occurred_at": "2026-05-16T07:50:00",
                "title": "JYHF subject 事件",
                "summary": "新链 subject 映射",
                "subject_key": "9030409",
                "theme_name": "AR眼镜",
                "confidence": 0.88,
                "source_type": "event_subject_map",
            }
        ],
        fallback_matched=[
            {
                "item_id": "event:999:legacy",
                "title": "旧链事件",
                "theme_subject_keys": ["legacy"],
                "theme_names": ["旧题材"],
            }
        ],
    )
    write = _WriteGateway()
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=write)

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=True)

    assert read.used_subject_events is True
    assert read.used_legacy_events is False
    assert payload["sections"]["matched_themes"][0]["subject_key"] == "9030409"
    assert payload["sections"]["matched_themes"][0]["theme_name"] == "AR眼镜"


@pytest.mark.asyncio
async def test_pre_market_brief_builder_keeps_primary_match_and_filters_low_value_major_events():
    read = _SubjectReadGateway(
        subject_events=[
            {
                "event_id": 601,
                "title": "同一事件高置信主匹配",
                "summary": "产业催化",
                "subject_key": "theme-primary",
                "theme_name": "主题材",
                "confidence": 0.95,
                "source_type": "event_subject_map",
            },
            {
                "event_id": 601,
                "title": "同一事件高置信主匹配",
                "summary": "产业催化",
                "subject_key": "theme-related",
                "theme_name": "关联题材",
                "confidence": 0.84,
                "source_type": "event_subject_map",
            },
            {
                "event_id": 602,
                "title": "某公司股东拟减持不超3%股份",
                "summary": "减持公告",
                "subject_key": "theme-noise",
                "theme_name": "噪声题材",
                "confidence": 0.96,
                "source_type": "event_subject_map",
            },
        ]
    )
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=_WriteGateway())

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=True)

    assert [row["subject_key"] for row in payload["sections"]["major_events"]] == ["theme-primary"]
    assert [row["subject_key"] for row in payload["sections"]["matched_themes"]] == ["theme-primary"]


@pytest.mark.asyncio
async def test_pre_market_brief_builder_splits_raw_and_matched_intel_announcements():
    builder = PreMarketBriefBuilder(
        read_gateway=_IntelAnnouncementGateway(),
        write_gateway=_WriteGateway(),
    )

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=True)

    assert len(payload["sections"]["company_announcements_raw"]) == 2
    assert len(payload["sections"]["company_announcements_matched"]) == 1
    assert payload["sections"]["company_announcements"] == payload["sections"]["company_announcements_raw"]
    ann = payload["sections"]["company_announcements_matched"][0]["announcements"][0]
    assert ann["theme_matched"] is True
    assert ann["matched_subjects"][0]["subject_key"] == "theme-a"
    assert ann["source_stage"] == "matched_intel_join"
    assert payload["diagnostics"]["intel_announcement_raw_count"] == 2
    assert payload["diagnostics"]["intel_announcement_matched_count"] == 1


@pytest.mark.asyncio
async def test_pre_market_brief_builder_does_not_fallback_to_legacy_when_subject_map_empty():
    read = _SubjectReadGateway(
        subject_events=[],
        fallback_matched=[
            {
                "item_id": "event:999:legacy",
                "title": "旧链事件",
                "theme_subject_keys": ["legacy"],
                "theme_names": ["旧题材"],
            }
        ],
    )
    write = _WriteGateway()
    builder = PreMarketBriefBuilder(read_gateway=read, write_gateway=write)

    payload = await builder.rebuild(date(2026, 5, 16), dry_run=True)

    assert read.used_subject_events is True
    assert read.used_legacy_events is False
    assert payload["sections"]["major_events"] == []
    assert payload["sections"]["matched_themes"] == []
    assert payload["diagnostics"]["matched_event_count"] == 0


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
