import assert from "node:assert/strict";
import { evictOldestApiCacheEntries, purgeAllApiCacheEntries, shouldBypassApiCache, safeSetApiCache } from "../src/utils/apiCache.js";

class MockStorage {
  constructor(entries = []) {
    this._map = new Map(entries);
  }

  get length() {
    return this._map.size;
  }

  key(index) {
    return Array.from(this._map.keys())[index] ?? null;
  }

  getItem(key) {
    return this._map.has(key) ? this._map.get(key) : null;
  }

  setItem(key, value) {
    this._map.set(String(key), String(value));
  }

  removeItem(key) {
    this._map.delete(String(key));
  }
}

class QuotaStorage extends MockStorage {
  constructor(entries = [], limit = 0) {
    super(entries);
    this.limit = limit;
  }

  setItem(key, value) {
    const hasKey = this._map.has(String(key));
    const nextSize = this._map.size + (hasKey ? 0 : 1);
    if (this.limit > 0 && nextSize > this.limit) {
      const err = new Error("QuotaExceededError");
      err.name = "QuotaExceededError";
      err.code = 22;
      throw err;
    }
    super.setItem(key, value);
  }
}

function testLargePayloadIsSkipped() {
  const storage = new MockStorage();
  const result = safeSetApiCache(storage, "api_cache_/api/v2/post_market_snapshot?x=1_{}", {
    data: "x".repeat(300_000),
    timestamp: Date.now(),
  });
  assert.equal(result.written, false);
  assert.equal(result.skipped, "payload_too_large");
  assert.equal(storage.length, 0);
}

function testQuotaExceededEvictsAndFallsBack() {
  const oldCache = JSON.stringify({ data: { hello: "world" }, timestamp: 1 });
  const storage = new QuotaStorage([
    ["api_cache_/api/v2/old_1_{}", oldCache],
    ["api_cache_/api/v2/old_2_{}", oldCache],
  ], 2);

  const result = safeSetApiCache(storage, "api_cache_/api/v2/daily-review-v2?_{}", {
    data: { ok: true },
    timestamp: Date.now(),
  }, { evictBatchSize: 2 });

  assert.equal(result.written, true);
  assert.equal(storage.getItem("api_cache_/api/v2/daily-review-v2?_{}") != null, true);
}

function testEvictOldestApiCacheEntries() {
  const storage = new MockStorage([
    ["api_cache_/api/v2/a_{}", JSON.stringify({ data: 1, timestamp: 1 })],
    ["api_cache_/api/v2/b_{}", JSON.stringify({ data: 2, timestamp: 2 })],
    ["api_cache_/api/v2/c_{}", JSON.stringify({ data: 3, timestamp: 3 })],
  ]);

  const evicted = evictOldestApiCacheEntries(storage, 2);
  assert.equal(evicted, 2);
  assert.equal(storage.getItem("api_cache_/api/v2/a_{}"), null);
  assert.equal(storage.getItem("api_cache_/api/v2/b_{}"), null);
  assert.equal(storage.getItem("api_cache_/api/v2/c_{}") != null, true);
}

function testBypassPathsAndFullPurge() {
  assert.equal(shouldBypassApiCache("/api/v2/post_market_snapshot?trade_date=2026-06-12"), true);
  assert.equal(shouldBypassApiCache("/api/v2/daily-review-v2?date=2026-06-12"), true);
  assert.equal(shouldBypassApiCache("/api/v2/theme/workspace"), false);

  const storage = new MockStorage([
    ["api_cache_/api/v2/post_market_snapshot?trade_date=2026-06-12_{}", JSON.stringify({ data: 1, timestamp: 1 })],
    ["api_cache_/api/v2/daily-review-v2?date=2026-06-12_{}", JSON.stringify({ data: 2, timestamp: 2 })],
    ["other_key", "x"],
  ]);

  const removed = purgeAllApiCacheEntries(storage);
  assert.equal(removed, 2);
  assert.equal(storage.getItem("api_cache_/api/v2/post_market_snapshot?trade_date=2026-06-12_{}"), null);
  assert.equal(storage.getItem("api_cache_/api/v2/daily-review-v2?date=2026-06-12_{}"), null);
  assert.equal(storage.getItem("other_key"), "x");
}

testLargePayloadIsSkipped();
testQuotaExceededEvictsAndFallsBack();
testEvictOldestApiCacheEntries();
testBypassPathsAndFullPurge();

console.log("api-cache-guard: ok");
