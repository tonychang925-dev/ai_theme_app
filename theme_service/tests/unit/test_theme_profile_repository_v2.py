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


class _FakeGatewayNoV2:
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
            }
        ]


class _CountingGateway(_FakeGateway):
    def __init__(self):
        self.v1_load_count = 0
        self.v2_load_count = 0

    async def load_theme_match_profiles(self):
        self.v1_load_count += 1
        return await super().load_theme_match_profiles()

    async def load_theme_profile_v2_profiles(self, status="draft", subject_keys=None):
        self.v2_load_count += 1
        return await super().load_theme_profile_v2_profiles(status=status, subject_keys=subject_keys)


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


async def test_theme_profile_repository_infers_legacy_numeric_subject_name(monkeypatch):
    monkeypatch.delenv("THEME_PROFILE_VERSION", raising=False)

    class Gateway:
        async def load_theme_match_profiles(self):
            return [
                {
                    "subject_key": "9060949",
                    "subject_name": "9060949",
                    "concept": "",
                    "profile_summary": "9060949：一、SpaceX产业动态 2026年1月22日 马斯克推进SpaceX IPO。",
                    "profile_core_anchors": ["火箭发射", "卫星互联网"],
                    "must_terms": ["星舰"],
                    "strong_terms": ["星链"],
                    "should_terms": [],
                    "not_terms": [],
                    "weak_terms": [],
                    "negative_terms": [],
                    "search_text": "",
                    "quality": "v1",
                }
            ]

    profiles = await ThemeProfileRepository(Gateway()).load_active_profiles()

    assert len(profiles) == 1
    assert profiles[0].subject_key == "9060949"
    assert profiles[0].subject_name == "SpaceX产业动态"
    assert profiles[0].concept == "SpaceX产业动态"
    assert "9060949" not in profiles[0].aliases


async def test_theme_profile_repository_v2_require_loaded_raises_when_gateway_missing(monkeypatch):
    monkeypatch.setenv("THEME_PROFILE_VERSION", "v2")
    monkeypatch.setenv("THEME_PROFILE_V2_REQUIRE_LOADED", "true")

    with pytest.raises(RuntimeError, match="load_theme_profile_v2_profiles"):
        await ThemeProfileRepository(_FakeGatewayNoV2()).load_active_profiles()


async def test_theme_profile_repository_caches_active_profiles(monkeypatch):
    monkeypatch.setenv("THEME_PROFILE_VERSION", "v2")
    monkeypatch.setenv("THEME_PROFILE_V2_SUBJECT_KEYS", "1001")
    monkeypatch.setenv("THEME_PROFILE_V2_STATUS", "draft")
    monkeypatch.setenv("THEME_PROFILE_V2_FALLBACK_TO_V1", "true")
    monkeypatch.setenv("THEME_PROFILE_CACHE_TTL_SECONDS", "300")
    gateway = _CountingGateway()
    repo = ThemeProfileRepository(gateway)

    first = await repo.load_active_profiles()
    second = await repo.load_active_profiles()

    assert first is second
    assert gateway.v1_load_count == 1
    assert gateway.v2_load_count == 1
    assert repo.get_cache_stats()["profile_cache_hit_count"] == 1
    assert repo.get_cache_stats()["profile_cache_miss_count"] == 1


async def test_theme_profile_repository_clear_cache_forces_reload(monkeypatch):
    monkeypatch.setenv("THEME_PROFILE_VERSION", "v2")
    monkeypatch.setenv("THEME_PROFILE_V2_SUBJECT_KEYS", "1001")
    monkeypatch.setenv("THEME_PROFILE_V2_STATUS", "draft")
    monkeypatch.setenv("THEME_PROFILE_V2_FALLBACK_TO_V1", "true")
    gateway = _CountingGateway()
    repo = ThemeProfileRepository(gateway)

    await repo.load_active_profiles()
    repo.clear_cache()
    await repo.load_active_profiles()

    assert gateway.v1_load_count == 2
    assert gateway.v2_load_count == 2


async def test_theme_profile_repository_caches_profile_map(monkeypatch):
    monkeypatch.setenv("THEME_PROFILE_VERSION", "v2")
    monkeypatch.setenv("THEME_PROFILE_V2_SUBJECT_KEYS", "1001")
    monkeypatch.setenv("THEME_PROFILE_V2_STATUS", "draft")
    monkeypatch.setenv("THEME_PROFILE_V2_FALLBACK_TO_V1", "true")
    gateway = _CountingGateway()
    repo = ThemeProfileRepository(gateway)

    first = await repo.load_active_profile_map()
    second = await repo.load_active_profile_map()

    assert first is second
    assert set(first) == {"1001", "1002"}
    assert gateway.v1_load_count == 1
    assert gateway.v2_load_count == 1
    assert repo.get_cache_stats()["profile_map_cache_hit_count"] == 1
    assert repo.get_cache_stats()["profile_map_cache_miss_count"] == 1
