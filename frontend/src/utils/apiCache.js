const API_CACHE_PREFIX = "api_cache_";
const API_CACHE_BYPASS_PATHS = [
  "/api/v2/post_market_snapshot",
  "/api/v2/daily-review-v2",
];

function isQuotaExceededError(error) {
  if (!error || typeof error !== "object") return false;
  const anyError = error;
  return (
    anyError.name === "QuotaExceededError" ||
    anyError.code === 22 ||
    anyError.code === 1014
  );
}

function isStorageAvailable(storage) {
  return !!storage && typeof storage.getItem === "function" && typeof storage.setItem === "function" && typeof storage.removeItem === "function";
}

function parseCacheEntry(raw) {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") return null;
    const timestamp = Number(parsed.timestamp);
    return Number.isFinite(timestamp) ? { data: parsed.data, timestamp } : null;
  } catch {
    return null;
  }
}

function listApiCacheKeys(storage) {
  if (!isStorageAvailable(storage)) return [];
  const keys = [];
  for (let index = 0; index < storage.length; index += 1) {
    const key = storage.key(index);
    if (key && key.startsWith(API_CACHE_PREFIX)) keys.push(key);
  }
  return keys;
}

function shouldBypassApiCache(urlText) {
  if (typeof urlText !== "string" || !urlText) return false;
  return API_CACHE_BYPASS_PATHS.some((path) => urlText.includes(path));
}

function purgeApiCacheForUrl(storage, urlText) {
  if (!isStorageAvailable(storage) || typeof urlText !== "string" || !urlText) return 0;
  const prefix = `${API_CACHE_PREFIX}${urlText}_`;
  let removed = 0;
  const keys = listApiCacheKeys(storage).filter((key) => key.startsWith(prefix));
  for (const key of keys) {
    try {
      storage.removeItem(key);
      removed += 1;
    } catch {
      // ignore
    }
  }
  return removed;
}

function purgeAllApiCacheEntries(storage) {
  if (!isStorageAvailable(storage)) return 0;
  const keys = listApiCacheKeys(storage);
  let removed = 0;
  for (const key of keys) {
    try {
      storage.removeItem(key);
      removed += 1;
    } catch {
      // ignore
    }
  }
  return removed;
}

function evictOldestApiCacheEntries(storage, maxEvictions = 8) {
  if (!isStorageAvailable(storage) || maxEvictions <= 0) return 0;
  const entries = listApiCacheKeys(storage)
    .map((key) => {
      const parsed = parseCacheEntry(storage.getItem(key));
      return parsed ? { key, timestamp: parsed.timestamp } : { key, timestamp: 0 };
    })
    .sort((left, right) => left.timestamp - right.timestamp);

  let evicted = 0;
  for (const entry of entries) {
    try {
      storage.removeItem(entry.key);
      evicted += 1;
    } catch {
      // ignore
    }
    if (evicted >= maxEvictions) break;
  }
  return evicted;
}

function safeSetApiCache(storage, cacheKey, payload, options = {}) {
  const { maxPayloadBytes = 250_000, evictBatchSize = 8 } = options;
  if (!isStorageAvailable(storage) || typeof cacheKey !== "string" || !cacheKey.startsWith(API_CACHE_PREFIX)) {
    return { written: false, skipped: "storage_unavailable" };
  }

  const serialized = typeof payload === "string" ? payload : JSON.stringify(payload);
  if (serialized.length > maxPayloadBytes) {
    return { written: false, skipped: "payload_too_large" };
  }

  try {
    storage.setItem(cacheKey, serialized);
    return { written: true, evicted: 0 };
  } catch (error) {
    if (!isQuotaExceededError(error)) {
      return { written: false, skipped: "set_failed" };
    }
  }

  const evicted = evictOldestApiCacheEntries(storage, evictBatchSize);
  if (evicted <= 0) {
    return { written: false, skipped: "quota_exceeded" };
  }

  try {
    storage.setItem(cacheKey, serialized);
    return { written: true, evicted };
  } catch (error) {
    return {
      written: false,
      skipped: isQuotaExceededError(error) ? "quota_exceeded" : "set_failed",
      evicted,
    };
  }
}

export { API_CACHE_PREFIX, evictOldestApiCacheEntries, listApiCacheKeys, parseCacheEntry, purgeAllApiCacheEntries, purgeApiCacheForUrl, safeSetApiCache, shouldBypassApiCache, isQuotaExceededError };
