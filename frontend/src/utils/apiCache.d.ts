export declare const API_CACHE_PREFIX: string;

export declare function isQuotaExceededError(error: unknown): boolean;

export declare function parseCacheEntry(raw: string | null): { data: unknown; timestamp: number } | null;

export declare function listApiCacheKeys(storage: Storage): string[];

export declare function evictOldestApiCacheEntries(storage: Storage, maxEvictions?: number): number;

export declare function shouldBypassApiCache(urlText: string): boolean;

export declare function purgeApiCacheForUrl(storage: Storage, urlText: string): number;

export declare function purgeAllApiCacheEntries(storage: Storage): number;

export declare function safeSetApiCache(
  storage: Storage,
  cacheKey: string,
  payload: unknown,
  options?: { maxPayloadBytes?: number; evictBatchSize?: number },
): { written: boolean; skipped?: string; evicted?: number };
