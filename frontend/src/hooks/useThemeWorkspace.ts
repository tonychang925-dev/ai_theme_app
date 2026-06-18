import { useCallback, useMemo } from 'react';
import { fetchThemeWorkspace } from '../lib/api';
import { useApi } from '../lib/hooks/useApi';

interface UseThemeWorkspaceOptions {
  tradeDate?: string;
}

export function useThemeWorkspace(subjectKey: string, options: UseThemeWorkspaceOptions = {}) {
  const { tradeDate } = options;

  // Data fetching with useApi
  const fetcher = useCallback(() => fetchThemeWorkspace(subjectKey, tradeDate || undefined), [subjectKey, tradeDate]);

  const {
    data: payload,
    loading,
    error,
    setData: setPayload,
    execute: fetchThemeWorkspaceData,
  } = useApi(fetcher, {
    initialData: null,
    immediate: true,
    deps: [subjectKey, tradeDate],
  });

  // Derived data
  const historyItems = useMemo(() => Array.isArray(payload?.history) ? payload.history : [], [payload]);
  const childItems = useMemo(() => Array.isArray(payload?.children) ? payload.children : [], [payload]);
  const stockItems = useMemo(() => Array.isArray(payload?.stocks) ? payload.stocks : [], [payload]);
  const graph = (payload?.graph ?? null) as Record<string, unknown> | null;
  const analytics = payload?.analytics ?? null;
  const summaryRow = analytics?.summary ?? null;
  const recentRankRows = useMemo(() => Array.isArray(analytics?.recent_rank) ? analytics.recent_rank : [], [analytics]);
  const leaderStocks = useMemo(() => Array.isArray(analytics?.leader_stocks) ? analytics.leader_stocks : [], [analytics]);
  const diagnostics = payload?.diagnostics;
  const themeName = typeof payload?.detail?.theme_name === 'string' ? payload.detail.theme_name : subjectKey;
  const summary = typeof payload?.detail?.summary === 'string' ? payload.detail.summary : '';
  const detailHtml = typeof payload?.detail?.detail_html === 'string' ? payload.detail.detail_html : '';
  const reasonShort = typeof payload?.detail?.reason_short === 'string' ? payload.detail.reason_short : '';
  const nodeLevel = typeof payload?.detail?.node_level === 'string' ? payload.detail.node_level : '';
  const parentSubjectKey = typeof payload?.detail?.parent_subject_key === 'string' ? payload.detail.parent_subject_key : '';
  const historyCount = typeof payload?.detail?.history_count === 'number' ? payload.detail.history_count : 0;
  const childrenCount = typeof payload?.detail?.children_count === 'number' ? payload.detail.children_count : 0;
  const stockCount = typeof payload?.detail?.stock_count === 'number' ? payload.detail.stock_count : 0;
  const bindingStatus = typeof payload?.detail?.binding_status === 'string' ? payload.detail.binding_status : '--';
  const effectiveTradeDate = String(analytics?.trade_date ?? payload?.trade_date ?? tradeDate ?? '').trim();

  // Computed ranked leader stocks
  const rankedLeaderStocks = useMemo(() => {
    const toNumber = (value: unknown) => {
      const n = Number(value ?? 0);
      return Number.isFinite(n) ? n : 0;
    };
    return [...leaderStocks].sort((a, b) => {
      const flowDiff = toNumber(b.main_net_inflow) - toNumber(a.main_net_inflow);
      if (flowDiff !== 0) return flowDiff;
      return toNumber(b.pct_chg) - toNumber(a.pct_chg);
    });
  }, [leaderStocks]);

  // Trend stats
  const trendStats = useMemo(() => {
    if (recentRankRows.length === 0) {
      return {
        maxAbsPct: 0,
        positiveDays: 0,
        latestPct: 0,
        latestHisPct: 0,
      };
    }
    const toNumber = (value: unknown) => {
      const n = Number(value ?? 0);
      return Number.isFinite(n) ? n : 0;
    };
    const pctValues = recentRankRows.map((item) => Math.abs(toNumber(item.pct_chg)));
    return {
      maxAbsPct: Math.max(...pctValues, 1),
      positiveDays: recentRankRows.filter((item) => toNumber(item.pct_chg) > 0).length,
      latestPct: toNumber(recentRankRows[0]?.pct_chg),
      latestHisPct: toNumber(recentRankRows[0]?.his_pct_chg),
    };
  }, [recentRankRows]);

  return {
    // Core state
    payload,
    loading,
    error,
    setPayload,
    fetchThemeWorkspaceData,

    // Derived data
    historyItems,
    childItems,
    stockItems,
    graph,
    analytics,
    summaryRow,
    recentRankRows,
    leaderStocks,
    rankedLeaderStocks,
    diagnostics,
    themeName,
    summary,
    detailHtml,
    reasonShort,
    nodeLevel,
    parentSubjectKey,
    historyCount,
    childrenCount,
    stockCount,
    bindingStatus,
    effectiveTradeDate,
    trendStats,

    // Subject key and trade date
    subjectKey,
    tradeDate,
  };
}
