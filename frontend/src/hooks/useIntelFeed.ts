import { useEffect, useMemo, useState, useRef, useCallback } from 'react';
import type {
  IntelFeedEvent,
  IntelFeedItem,
  IntelFeedView,
  IntelItemType,
  IntelSession,
  SSEConnectionState,
} from '../lib/api';
import { fetchRecapDefaults, createIntelStreamManager, fetchWorkspaceIntelContext } from '../lib/api';
import { useApi } from '../lib/hooks/useApi';

interface UseIntelFeedOptions {
  initialDate?: string;
  initialType?: IntelItemType;
  initialSession?: IntelSession;
  initialSelectedItemId?: string | null;
  limit?: number;
  subjectKey?: string | null;
}

interface UseIntelFeedReturn {
  // Filter state
  date: string;
  setDate: (date: string) => void;
  type: IntelItemType;
  setType: (type: IntelItemType) => void;
  session: IntelSession;
  setSession: (session: IntelSession) => void;

  // Data state
  payload: IntelFeedView | null;
  loading: boolean;
  error: string | null;
  setPayload: (data: IntelFeedView | null | ((prev: IntelFeedView | null) => IntelFeedView | null)) => void;
  fetchIntelFeedData: () => Promise<IntelFeedView | null>;

  // UI state
  selectedItemId: string | null;
  setSelectedItemId: (id: string | null) => void;

  // Real-time state
  liveStatus: 'connecting' | 'live' | 'fallback';
  liveNewCount: number;
  sseConnectionState: SSEConnectionState | null;
  streamDiagnostics: {
    fallbackActive: boolean;
    fallbackReason: string | null;
    streamRecoveredAt: string | null;
  };
  recapDates: { postMarket: string; preMarket: string };

  // Functions
  mergeIncomingItems: (incomingItems: IntelFeedItem[]) => void;
  applyFeedData: (data: IntelFeedView) => void;
}

export function useIntelFeed(options: UseIntelFeedOptions = {}): UseIntelFeedReturn {
  const {
    initialDate,
    initialType = 'all',
    initialSession = 'all',
    initialSelectedItemId = null,
    limit = 50,
    subjectKey = null,
  } = options;

  function todayString() {
    return new Date().toISOString().slice(0, 10);
  }

  // Read initial state from URL or options
  const initialState = useMemo(() => {
    if (typeof window !== 'undefined') {
      const params = new URLSearchParams(window.location.search);
      return {
        date: params.get('date') || initialDate || todayString(),
        type: (params.get('type') as IntelItemType | null) || initialType,
        session: (params.get('session') as IntelSession | null) || initialSession,
        selectedItemId: params.get('item') || initialSelectedItemId,
      };
    }
    return {
      date: initialDate || todayString(),
      type: initialType,
      session: initialSession,
      selectedItemId: initialSelectedItemId,
    };
  }, [initialDate, initialType, initialSession, initialSelectedItemId]);

  // Filter state
  const [date, setDate] = useState(initialState.date);
  const [type, setType] = useState<IntelItemType>(initialState.type);
  const [session, setSession] = useState<IntelSession>(initialState.session);

  // Data fetching with useApi
  const fetcher = useCallback(async () => {
    const ctx = await fetchWorkspaceIntelContext({ date, session, limit });
    let rawItems = ctx.items || [];
    // 前端过滤：按 type 和 theme_name 过滤（后端 subject_key 为 None，不支持精确过滤）
    if (type !== 'all') {
      rawItems = rawItems.filter((item) => item.item_type === type);
    }
    if (subjectKey) {
      rawItems = rawItems.filter((item) =>
        (item.theme_names || []).some((name) => name === subjectKey)
      );
    }
    const data: IntelFeedView = {
      items: rawItems,
      count: rawItems.length,
      date: ctx.date || date,
      session,
      type,
      diagnostics: {
        partial: false,
        sources: [String(ctx.source || 'workspace_intel_context')],
      },
    };
    return data;
  }, [date, type, session, limit, subjectKey]);

  const {
    data: payload,
    loading,
    error,
    setData: setPayload,
    execute: fetchIntelFeedData,
  } = useApi(fetcher, {
    initialData: null,
    immediate: true,
    deps: [date, type, session, subjectKey],
  });

  // UI state
  const [selectedItemId, setSelectedItemId] = useState<string | null>(initialState.selectedItemId);

  // Real-time state
  const [liveStatus, setLiveStatus] = useState<'connecting' | 'live' | 'fallback'>('connecting');
  const [liveNewCount, setLiveNewCount] = useState(0);
  const [recapDates, setRecapDates] = useState<{ postMarket: string; preMarket: string }>({
    postMarket: initialState.date,
    preMarket: initialState.date,
  });
  const [sseConnectionState, setSseConnectionState] = useState<SSEConnectionState | null>(null);
  const [fallbackActive, setFallbackActive] = useState(false);
  const [fallbackReason, setFallbackReason] = useState<string | null>(null);
  const [streamRecoveredAt, setStreamRecoveredAt] = useState<string | null>(null);
  const sseManagerRef = useRef<ReturnType<typeof createIntelStreamManager> | null>(null);
  const [pollingInterval, setPollingInterval] = useState(30000); // 默认30秒
  const [pollingErrorCount, setPollingErrorCount] = useState(0);

  // Function to apply feed data and clear selection if needed
  const applyFeedData = useCallback((data: IntelFeedView) => {
    setPayload(data);
    if (selectedItemId && !data.items.some((item) => item.item_id === selectedItemId)) {
      setSelectedItemId(null);
    }
  }, [selectedItemId, setPayload]);

  // Function to merge incoming items (respects subjectKey filter)
  const mergeIncomingItems = useCallback((incomingItems: IntelFeedItem[]) => {
    if (incomingItems.length === 0) return;
    // 前端过滤：按 type 和 subjectKey 过滤 SSE 推送的 items
    let scopedItems = incomingItems;
    if (type !== 'all') {
      scopedItems = scopedItems.filter((item) => item.item_type === type);
    }
    if (subjectKey) {
      scopedItems = scopedItems.filter((item) =>
        (item.theme_names || []).some((name) => name === subjectKey)
      );
    }
    if (scopedItems.length === 0) return;
    setPayload((current) => {
      const currentItems = current?.items ?? [];
      const existingIds = new Set(currentItems.map((item) => item.item_id));
      // 内容去重：title+source_channel 防 JYHF CDP 重复发布
      const existingKeys = new Set(currentItems.map((item) => `${item.title}|${(item as any).source_channel || ''}`));
      const freshItems = scopedItems.filter((item) => {
        if (existingIds.has(item.item_id)) return false;
        const key = `${item.title}|${(item as any).source_channel || ''}`;
        if (existingKeys.has(key)) return false;
        existingKeys.add(key);
        return true;
      });
      if (freshItems.length === 0) return current;

      setLiveNewCount((value) => value + freshItems.length);

      return {
        items: [...freshItems, ...currentItems].slice(0, limit),
        count: Math.min(currentItems.length + freshItems.length, limit),
        date: current?.date ?? date,
        session: current?.session ?? session,
        type: current?.type ?? type,
        diagnostics: current?.diagnostics,
      };
    });
  }, [date, session, type, limit, subjectKey, setPayload]);

  // Fetch recap defaults
  useEffect(() => {
    let active = true;
    fetchRecapDefaults()
      .then((data) => {
        if (!active) return;
        setRecapDates({
          postMarket: data.latest_post_market_date || initialState.date,
          preMarket: data.latest_pre_market_date || initialState.date,
        });
      })
      .catch(() => {
        if (!active) return;
        setRecapDates({
          postMarket: initialState.date,
          preMarket: initialState.date,
        });
      });
    return () => {
      active = false;
    };
  }, [initialState.date]);

  // Reset liveNewCount when filters change
  useEffect(() => {
    setLiveNewCount(0);
  }, [date, type, session]);

  // 初始数据加载成功后标记为 live
  useEffect(() => {
    if (!loading && payload && payload.items.length > 0) {
      setLiveStatus('live');
    }
  }, [loading, payload]);

  // 实时采集栈状态（最高优先级，实时栈停止时强制红色）
  const [realtimeRunning, setRealtimeRunning] = useState(true);
  useEffect(() => {
    let active = true;
    const checkRealtime = async () => {
      try {
        const resp = await fetch('/api/v1/realtime/status');
        if (!active) return;
        const data = await resp.json();
        setRealtimeRunning(data?.running !== false);
      } catch {
        // 接口不可用时不改变状态
      }
    };
    checkRealtime();
    const timer = setInterval(checkRealtime, 30000);
    return () => { active = false; clearInterval(timer); };
  }, []);

  // 实时栈停止时强制 fallback
  const effectiveLiveStatus = !realtimeRunning ? 'fallback' : liveStatus;

  // SSE manager effect
  const normalizeIntelItem = useCallback((raw: IntelFeedEvent["item"]): IntelFeedItem | null => {
    if (!raw || typeof raw !== "object") return null;
    const themeSubjectKeys = Array.isArray(raw.theme_subject_keys) ? raw.theme_subject_keys : [];
    const themeNames = Array.isArray(raw.theme_names) ? raw.theme_names : [];
    const stockIds = Array.isArray(raw.stock_ids) ? raw.stock_ids : [];
    const stockNames = Array.isArray(raw.stock_names) ? raw.stock_names : [];
    if (!raw.item_id || !raw.item_type || !raw.occurred_at) return null;
    // 过滤 CNINFO 公告（source_channel=cninfo_announcement）
    if (String((raw as any).source_channel || "") === "cninfo_announcement") return null;
    return {
      item_id: String(raw.item_id),
      item_type: raw.item_type,
      occurred_at: String(raw.occurred_at),
      title: String(raw.title || raw.summary || ""),
      summary: String(raw.summary || raw.title || ""),
      theme_subject_keys: themeSubjectKeys.map((x) => String(x)),
      theme_names: themeNames.map((x) => String(x)),
      stock_ids: stockIds.map((x) => String(x)),
      stock_names: stockNames.map((x) => String(x)),
      confidence: raw.confidence ?? null,
      impact_score: raw.impact_score ?? null,
      source_type: String(raw.source_type || "unknown"),
      source_channel: raw.source_channel ? String(raw.source_channel) : undefined,
    };
  }, []);

  useEffect(() => {
    // 清理现有的SSE管理器
    if (sseManagerRef.current) {
      sseManagerRef.current.disconnect();
      sseManagerRef.current = null;
    }

    setSseConnectionState(null);
    setFallbackActive(false);
    setFallbackReason(null);
    setStreamRecoveredAt(null);

    // 创建SSE管理器实例
    const manager = createIntelStreamManager(
      { date, type, session },
      {
        onIntelItem: (event: IntelFeedEvent) => {
          const normalized = normalizeIntelItem(event?.item);
          if (normalized) {
            mergeIncomingItems([normalized]);
            setLiveStatus('live');
          }
        },
        onHeartbeat: () => {
          setLiveStatus('live');
        },
        onStateChange: (state: SSEConnectionState) => {
          setSseConnectionState(state);
          // 根据SSE管理器状态更新liveStatus
          if (state.status === 'connected') {
            setLiveStatus('live');
            if (fallbackActive) {
              setFallbackActive(false);
              setFallbackReason(null);
              setStreamRecoveredAt(new Date().toISOString());
            }
          } else if (state.status === 'error' || state.status === 'closed') {
            setLiveStatus('fallback');
            setFallbackActive(true);
            setFallbackReason(state.lastError || `sse_${state.status}`);
          } else if (state.status === 'connecting' || state.status === 'retrying') {
            setLiveStatus('connecting');
          }
        },
        onError: (error: Error) => {
          console.error('SSE连接错误:', error);
          setLiveStatus('fallback');
          setFallbackActive(true);
          setFallbackReason(error.message || 'sse_error');
        },
        onClose: () => {
          setLiveStatus('fallback');
          setFallbackActive(true);
          setFallbackReason('sse_closed');
        },
      },
      {
        // 配置选项：使用默认值，但可以在这里自定义
        maxRetries: 3,
        retryDelay: 1000,
        heartbeatTimeout: 45000,
        connectTimeout: 10000,
      }
    );

    sseManagerRef.current = manager;
    manager.connect();

    return () => {
      if (sseManagerRef.current) {
        sseManagerRef.current.disconnect();
        sseManagerRef.current = null;
      }
    };
  }, [date, type, session, subjectKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // Polling effect
  useEffect(() => {
    let active = true;
    let timeoutId: number | null = null;

    const poll = async () => {
      if (!active) return;
      // Only poll when stream is degraded/fallback.
      if (!fallbackActive) {
        timeoutId = window.setTimeout(poll, pollingInterval);
        return;
      }

      try {
        const ctx = await fetchWorkspaceIntelContext({
          date,
          session,
          limit,
        });
        let rawItems = ctx.items || [];
        if (type !== 'all') {
          rawItems = rawItems.filter((item) => item.item_type === type);
        }
        if (subjectKey) {
          rawItems = rawItems.filter((item) =>
            (item.theme_names || []).some((name) => name === subjectKey)
          );
        }
        const data: IntelFeedView = {
          items: rawItems,
          count: rawItems.length,
          date: ctx.date || date,
          session,
          type,
          diagnostics: {
            partial: false,
            sources: [String(ctx.source || 'workspace_intel_context')],
          },
        };
        const currentIds = new Set((payload?.items ?? []).map((item) => item.item_id));
        const freshItems = data.items.filter((item) => !currentIds.has(item.item_id));
        if (freshItems.length > 0) {
          mergeIncomingItems(freshItems);
        }

        // 成功：重置错误计数和间隔
        setPollingErrorCount(0);
        setPollingInterval(30000); // 恢复默认30秒间隔
      } catch (error) {
        console.error('轮询失败:', error);
        setLiveStatus('fallback');

        // 增加错误计数和间隔（智能退避）
        const newErrorCount = pollingErrorCount + 1;
        setPollingErrorCount(newErrorCount);

        // 退避策略：30秒 * 2^错误计数，最大5分钟（300000毫秒）
        const backoffInterval = Math.min(30000 * Math.pow(2, newErrorCount), 300000);
        setPollingInterval(backoffInterval);

        console.log(`轮询错误，下次间隔: ${backoffInterval}ms, 错误计数: ${newErrorCount}`);
      }

      // 安排下一次轮询
      if (active) {
        timeoutId = window.setTimeout(poll, pollingInterval);
      }
    };

    // 开始第一次轮询
    timeoutId = window.setTimeout(poll, pollingInterval);

    return () => {
      active = false;
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [date, type, session, payload, pollingInterval, pollingErrorCount, limit, mergeIncomingItems, subjectKey, fallbackActive]);

  // URL sync effect
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const params = new URLSearchParams();
    params.set('date', date);
    params.set('type', type);
    params.set('session', session);
    if (selectedItemId) {
      params.set('item', selectedItemId);
    }
    const next = `${window.location.pathname}?${params.toString()}`;
    window.history.replaceState({}, '', next);
  }, [date, type, session, selectedItemId]);

  return {
    // Filter state
    date,
    setDate,
    type,
    setType,
    session,
    setSession,

    // Data state
    payload,
    loading,
    error,
    setPayload,
    fetchIntelFeedData,

    // UI state
    selectedItemId,
    setSelectedItemId,

    // Real-time state
    liveStatus: effectiveLiveStatus,
    liveNewCount,
    sseConnectionState,
    streamDiagnostics: {
      fallbackActive,
      fallbackReason,
      streamRecoveredAt,
    },
    recapDates,

    // Functions
    mergeIncomingItems,
    applyFeedData,
  };
}
