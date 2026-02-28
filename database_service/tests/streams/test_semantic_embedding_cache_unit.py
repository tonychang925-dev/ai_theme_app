from __future__ import annotations

import numpy as np
import pytest

from theme_service.matchers.semantic_matcher import TransformerSemanticMatcher


def _themes():
    return [
        {
            "code": "T001",
            "name": "商业航天",
            "description": "商业航天产业",
            "keywords": ["航天", "火箭"],
            "level2_category": "科技",
            "level3_category": "商业航天",
        },
        {
            "code": "T002",
            "name": "卫星互联网",
            "description": "卫星互联网产业",
            "keywords": ["卫星", "互联网"],
            "level2_category": "科技",
            "level3_category": "卫星互联网",
        },
    ]


def test_semantic_embedding_disk_cache_reuse(tmp_path, monkeypatch):
    encode_calls = {"count": 0}

    def _fake_load_model(self):
        self.model = object()

    def _fake_encode(self, text):
        encode_calls["count"] += 1
        base = float(len(text))
        return np.asarray([base, base / 10.0, 1.0], dtype=np.float32)

    monkeypatch.setattr(TransformerSemanticMatcher, "_load_semantic_model", _fake_load_model)
    monkeypatch.setattr(TransformerSemanticMatcher, "_encode", _fake_encode)

    cfg = {
        "enable_redis_embedding_cache": False,
        "enable_embedding_disk_cache": True,
        "embedding_cache_dir": str(tmp_path / "semantic_cache"),
    }

    matcher1 = TransformerSemanticMatcher(cfg)
    matcher1.initialize(_themes(), [])
    assert encode_calls["count"] == 2
    assert len(matcher1.theme_embeddings) == 2

    matcher2 = TransformerSemanticMatcher(cfg)
    matcher2.initialize(_themes(), [])
    assert encode_calls["count"] == 2, "second initialize should reuse persisted embedding cache"
    assert len(matcher2.theme_embeddings) == 2


class _FakeRedisPipeline:
    def __init__(self, client):
        self._client = client
        self._ops = []

    def setex(self, key, ttl, value):
        self._ops.append((key, value))
        return self

    def execute(self):
        for key, value in self._ops:
            self._client.store[key] = value
        self._ops.clear()
        return True


class _FakeRedisClient:
    def __init__(self):
        self.store = {}

    def ping(self):
        return True

    def mget(self, keys):
        return [self.store.get(k) for k in keys]

    def pipeline(self, transaction=False):
        return _FakeRedisPipeline(self)


@pytest.fixture
def fake_redis_client():
    return _FakeRedisClient()


def test_semantic_embedding_redis_cache_reuse(monkeypatch, fake_redis_client):
    encode_calls = {"count": 0}

    def _fake_load_model(self):
        self.model = object()

    def _fake_encode(self, text):
        encode_calls["count"] += 1
        base = float(len(text))
        return np.asarray([base, base / 10.0, 1.0], dtype=np.float32)

    class _FakeRedisModule:
        class Redis:
            @staticmethod
            def from_url(*args, **kwargs):
                return fake_redis_client

    monkeypatch.setattr(TransformerSemanticMatcher, "_load_semantic_model", _fake_load_model)
    monkeypatch.setattr(TransformerSemanticMatcher, "_encode", _fake_encode)
    monkeypatch.setattr("redis.Redis", _FakeRedisModule.Redis, raising=False)

    cfg = {
        "enable_redis_embedding_cache": True,
        "redis_cache_url": "redis://fake:6379/0",
        "redis_key_prefix": "db:",
        "enable_embedding_disk_cache": False,
    }

    matcher1 = TransformerSemanticMatcher(cfg)
    matcher1.initialize(_themes(), [])
    assert encode_calls["count"] == 2
    assert len(fake_redis_client.store) > 0
    assert any(k.startswith("db:semantic_embedding:") for k in fake_redis_client.store.keys())

    matcher2 = TransformerSemanticMatcher(cfg)
    matcher2.initialize(_themes(), [])
    assert encode_calls["count"] == 2, "second initialize should reuse redis embedding cache"
