from __future__ import annotations

import pytest

from theme_service.repositories.theme_profile_repository import ThemeProfileRepository

pytestmark = pytest.mark.asyncio


class _FakeGateway:
    async def load_theme_match_profiles(self):
        return [
            {
                "subject_key": "1001",
                "subject_name": "旧题材A",
                "concept": "旧题材A",
                "must_terms": ["旧A"],
                "strong_terms": [],
                "should_terms": [],
                "not_terms": [],
                "weak_terms": [],
                "negative_terms": [],
                "search_text": "旧A",
                "quality": "v1",
            },
            {
                "subject_key": "1002",
                "subject_name": "旧题材B",
                "concept": "旧题材B",
                "must_terms": ["旧B"],
                "strong_terms": [],
                "should_terms": [],
                "not_terms": [],
                "weak_terms": [],
                "negative_terms": [],
                "search_text": "旧B",
                "quality": "v1",
            },
        ]

    async def load_theme_profile_v2_profiles(self, status="draft", subject_keys=None):
        assert status == "draft"
        assert subject_keys == ["1001"]
        return [
            {
                "subject_key": "1001",
                "subject_name": "新题材A",
                "aliases": ["新A"],
                "entity_anchors": ["实体A"],
                "domain_anchors": ["领域A"],
                "product_anchors": ["产品A"],
                "technology_anchors": [],
                "must_terms": ["新A"],
                "strong_terms": ["实体A"],
                "should_terms": ["领域A"],
                "support_terms": [],
                "weak_terms": [],
                "no_anchor_terms": [],
                "negative_terms": ["非A"],
                "boundary_rules": {},
                "eval_metrics": {"generation_mode": "manual_ai"},
            }
        ]


async def test_theme_profile_repository_v2_overlay_keeps_v1_fallback(monkeypatch):
    monkeypatch.setenv("THEME_PROFILE_VERSION", "v2")
    monkeypatch.setenv("THEME_PROFILE_V2_SUBJECT_KEYS", "1001")
    monkeypatch.setenv("THEME_PROFILE_V2_STATUS", "draft")
    monkeypatch.setenv("THEME_PROFILE_V2_FALLBACK_TO_V1", "true")

    profiles = await ThemeProfileRepository(_FakeGateway()).load_active_profiles()
    by_key = {profile.subject_key: profile for profile in profiles}

    assert by_key["1001"].subject_name == "新题材A"
    assert by_key["1001"].quality == "v2"
    assert by_key["1002"].subject_name == "旧题材B"
    assert by_key["1002"].quality == "v1"


async def test_theme_profile_repository_v1_default(monkeypatch):
    monkeypatch.delenv("THEME_PROFILE_VERSION", raising=False)

    profiles = await ThemeProfileRepository(_FakeGateway()).load_active_profiles()

    assert {profile.subject_name for profile in profiles} == {"旧题材A", "旧题材B"}
