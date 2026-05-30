"""Tests for MajorEventClassifier — PR-4A."""
import pytest
from stock_processing_service.domain.services.mainline_discovery.major_event_classifier import (
    MajorEventClassifier,
    MajorEventClassification,
)


class TestMajorEventClassifier:

    def test_national_policy_triggers_fast_line(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "国务院印发卫星互联网产业发展规划",
             "summary": "推动商业航天和卫星互联网规模化应用", "event_type": "policy"},
            {"event_id": "e2", "title": "发改委设立专项产业基金",
             "summary": "支持航天产业链发展", "event_type": "policy"},
        ]
        result = c.classify(events)
        assert result.is_fast_line_trigger is True
        assert result.major_event_score >= 90
        assert result.trigger_type == "major_policy"
        assert len(result.supporting_event_ids) == 2
        assert result.method == "rule_keyword_v1"

    def test_geopolitical_conflict_triggers(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "以伊冲突升级 原油价格暴涨",
             "summary": "中东地缘冲突加剧", "event_type": "conflict"},
        ]
        result = c.classify(events)
        assert result.is_fast_line_trigger is True
        assert result.trigger_type == "geopolitical_conflict"

    def test_technology_breakthrough_triggers(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "国产GPU实现重大技术突破",
             "summary": "首次达到国际先进水平，里程碑事件", "event_type": "tech"},
        ]
        result = c.classify(events)
        assert result.is_fast_line_trigger is True
        assert result.trigger_type == "technology_breakthrough"

    def test_multiple_triggers_picks_highest(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "国务院政策出台",
             "summary": "重大政策", "event_type": "policy"},
            {"event_id": "e2", "title": "技术突破纪录",
             "summary": "技术里程碑", "event_type": "tech"},
        ]
        result = c.classify(events)
        # major_policy has higher base score than technology_breakthrough
        assert result.trigger_type == "major_policy"

    def test_ordinary_media_does_not_trigger(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "某公司发布季度财报",
             "summary": "营收增长10%", "event_type": "company"},
        ]
        result = c.classify(events)
        assert result.is_fast_line_trigger is False
        assert result.major_event_level == "C"

    def test_empty_events_no_trigger(self):
        c = MajorEventClassifier()
        result = c.classify([])
        assert result.is_fast_line_trigger is False
        assert result.supporting_event_ids == []

    def test_score_increases_with_more_matches(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "国务院一号文件",
             "summary": "政策", "event_type": "policy"},
            {"event_id": "e2", "title": "发改委配套细则",
             "summary": "政策", "event_type": "policy"},
            {"event_id": "e3", "title": "工信部实施方案",
             "summary": "政策", "event_type": "policy"},
        ]
        result = c.classify(events)
        assert result.is_fast_line_trigger is True
        # base 92 + 3*2=6 → 98 capped at 98
        assert result.major_event_score == 98.0

    def test_event_series_boosts_score(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "国务院政策",
             "summary": "重大政策", "event_type": "policy"},
        ]
        series = [{"consistency_score": 75}]
        result = c.classify(events, event_series=series)
        assert result.is_fast_line_trigger is True
        # base 92 + 1*2=2 + series_bonus 3 = 97
        assert result.major_event_score >= 95

    def test_scoring_not_trigger_without_enough_events(self):
        c = MajorEventClassifier()
        events = [
            {"event_id": "e1", "title": "某公司成立新事业部",
             "summary": "公司内部调整", "event_type": "company"},
        ]
        result = c.classify(events)
        assert result.is_fast_line_trigger is False
        assert result.major_event_score < 85

    def test_to_dict(self):
        result = MajorEventClassification(
            major_event_score=92, major_event_level="A",
            is_fast_line_trigger=True, trigger_type="major_policy",
            supporting_event_ids=["e1"], reason="重大政策"
        )
        d = result.to_dict()
        assert d["major_event_score"] == 92
        assert d["is_fast_line_trigger"] is True
        assert d["method"] == "rule_keyword_v1"
