/**
 * 通用的API数据获取钩子
 *
 * 封装异步数据获取逻辑，统一处理加载状态、错误状态和数据缓存。
 */

import { useState, useCallback, useEffect, useRef } from 'react';

export interface UseApiOptions<T> {
  /** 初始数据 */
  initialData?: T | null;
  /** 是否立即执行（默认true） */
  immediate?: boolean;
  /** 依赖数组，变化时重新执行 */
  deps?: any[];
  /** 是否启用缓存（默认false） */
  cache?: boolean;
  /** 缓存过期时间（毫秒） */
  cacheExpiry?: number;
  /** 错误重试次数（默认0） */
  retryCount?: number;
  /** 重试延迟（毫秒，默认1000） */
  retryDelay?: number;
}

export interface UseApiResult<T> {
  /** 数据 */
  data: T | null;
  /** 加载状态 */
  loading: boolean;
  /** 错误信息 */
  error: string | null;
  /** 手动触发数据获取 */
  execute: (...args: any[]) => Promise<T | null>;
  /** 手动设置数据 */
  setData: (data: T | null | ((prev: T | null) => T | null)) => void;
  /** 手动设置错误 */
  setError: (error: string | null) => void;
  /** 重置状态（清空数据和错误） */
  reset: () => void;
}

/**
 * 缓存管理器
 */
class ApiCache {
  private cache = new Map<string, { data: any; timestamp: number; expiry: number }>();

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) return null;

    const now = Date.now();
    if (now - entry.timestamp > entry.expiry) {
      this.cache.delete(key);
      return null;
    }

    return entry.data;
  }

  set<T>(key: string, data: T, expiry: number): void {
    this.cache.set(key, {
      data,
      timestamp: Date.now(),
      expiry
    });
  }

  clear(): void {
    this.cache.clear();
  }

  delete(key: string): void {
    this.cache.delete(key);
  }
}

// 全局缓存实例
const globalCache = new ApiCache();

/**
 * 生成缓存键
 */
function generateCacheKey(fetcher: Function, args: any[]): string {
  const argsString = JSON.stringify(args);
  const fetcherName = fetcher.name || 'anonymous';
  return `${fetcherName}:${argsString}`;
}

/**
 * 主钩子函数
 */
export function useApi<T>(
  fetcher: (...args: any[]) => Promise<T>,
  options: UseApiOptions<T> = {}
): UseApiResult<T> {
  const {
    initialData = null,
    immediate = true,
    deps = [],
    cache = false,
    cacheExpiry = 5 * 60 * 1000, // 5分钟
    retryCount = 0,
    retryDelay = 1000
  } = options;

  const [data, setData] = useState<T | null>(initialData);
  const [loading, setLoading] = useState<boolean>(immediate);
  const [error, setError] = useState<string | null>(null);

  const retryCountRef = useRef(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const cacheKeyRef = useRef<string | null>(null);

  const execute = useCallback(async (...args: any[]): Promise<T | null> => {
    // 取消之前的请求
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }

    // 创建新的AbortController
    abortControllerRef.current = new AbortController();

    // 生成缓存键
    const cacheKey = cache ? generateCacheKey(fetcher, args) : null;
    cacheKeyRef.current = cacheKey;

    // 检查缓存
    if (cache && cacheKey) {
      const cached = globalCache.get<T>(cacheKey);
      if (cached !== null) {
        setData(cached);
        setLoading(false);
        setError(null);
        return cached;
      }
    }

    setLoading(true);
    setError(null);
    retryCountRef.current = 0;

    const executeWithRetry = async (attempt: number): Promise<T | null> => {
      try {
        const result = await fetcher(...args);

        // 存储到缓存
        if (cache && cacheKey) {
          globalCache.set(cacheKey, result, cacheExpiry);
        }

        setData(result);
        setLoading(false);
        setError(null);
        retryCountRef.current = 0;

        return result;
      } catch (err: any) {
        // 如果是取消请求，不视为错误
        if (err.name === 'AbortError') {
          return null;
        }

        // 检查是否应该重试
        if (attempt < retryCount) {
          retryCountRef.current = attempt + 1;
          await new Promise(resolve => setTimeout(resolve, retryDelay));
          return executeWithRetry(attempt + 1);
        }

        // 最终失败
        const errorMessage = err?.message || '未知错误';
        setError(errorMessage);
        setLoading(false);

        return null;
      }
    };

    return executeWithRetry(0);
  }, [fetcher, cache, cacheExpiry, retryCount, retryDelay]);

  // 立即执行效果
  useEffect(() => {
    if (immediate) {
      execute();
    }

    return () => {
      // 清理：取消进行中的请求
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [execute, immediate, ...deps]);

  const reset = useCallback(() => {
    setData(initialData);
    setError(null);
    setLoading(false);

    // 清理缓存
    if (cacheKeyRef.current) {
      globalCache.delete(cacheKeyRef.current);
    }
  }, [initialData]);

  return {
    data,
    loading,
    error,
    execute,
    setData,
    setError,
    reset
  };
}

/**
 * 简化的数据获取钩子（无缓存和重试）
 */
export function useFetch<T>(
  fetcher: (...args: any[]) => Promise<T>,
  deps: any[] = []
): UseApiResult<T> {
  return useApi(fetcher, { deps });
}