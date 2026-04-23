export type IntelItemType = "all" | "event" | "event_review" | "theme_move" | "new_theme" | "stock_move";
export type IntelSession = "all" | "pre" | "intra" | "post";

export interface IntelFeedItem {
  item_id: string;
  item_type: "event" | "event_review" | "theme_move" | "new_theme" | "stock_move";
  occurred_at: string;
  title: string;
  summary: string;
  theme_subject_keys: string[];
  theme_names: string[];
  stock_ids: string[];
  stock_names: string[];
  confidence?: number | null;
  impact_score?: number | null;
  source_type: string;
  source_channel?: string;
}

export interface IntelFeedView {
  items: IntelFeedItem[];
  count: number;
  date?: string;
  session: IntelSession;
  type: IntelItemType;
  diagnostics?: {
    partial: boolean;
    sources: string[];
    source_channels?: string[];
    source_channel_counts?: Record<string, number>;
    fallback_from?: string | null;
  };
}

export interface IntelFeedEvent {
  event_id: string;
  occurred_at: string;
  event_type: "event" | "event_review" | "theme_move" | "new_theme" | "stock_move";
  item: IntelFeedItem;
  cursor?: string;
}

export interface StrongStockWatchItem {
  trade_date: string;
  stock_id: string;
  stock_name: string;
  subject_key?: string | null;
  theme_name?: string | null;
  watch_status: string;
  watch_score?: number | null;
  watch_priority?: number | null;
  relay_role?: string | null;
  pool_entry_type?: string | null;
  cycle_state?: string | null;
  mainline_strength_score?: number | null;
  fade_watch?: boolean;
  fade_confirmed?: boolean;
  promoted_to_candidate?: boolean;
  support_type?: string | null;
  support_level?: number | null;
  support_score?: number | null;
  watch_start_date?: string | null;
  last_trade_date?: string | null;
  watch_window_days?: number | null;
  pct_chg?: number | null;
  current_flag?: number | null;
  turnover_rate?: number | null;
  main_net_inflow?: number | null;
  selected_reason?: string;
  labels_json?: Record<string, unknown>;
  evidence_json?: Record<string, unknown>;
}

export interface StrongStockWatchView {
  date_from: string;
  date_to: string;
  window_days: number;
  latest_per_stock?: boolean;
  include_removed?: boolean;
  count: number;
  items: StrongStockWatchItem[];
  diagnostics?: {
    partial: boolean;
    source: string;
  };
}

export interface ThemeWorkspaceView {
  subject_key: string;
  trade_date?: string | null;
  detail: Record<string, unknown>;
  history?: Record<string, unknown>[] | null;
  children?: Record<string, unknown>[] | null;
  stocks?: Record<string, unknown>[] | null;
  analytics?: {
    trade_date?: string | null;
    summary?: Record<string, unknown> | null;
    recent_rank?: Record<string, unknown>[] | null;
    leader_stocks?: Record<string, unknown>[] | null;
  } | null;
  diagnostics?: {
    partial: boolean;
    missing_sections: string[];
  };
}

export type ThemeHistory = Record<string, unknown>;
export type ThemeChild = Record<string, unknown>;
export type ThemeStock = Record<string, unknown>;
export type ThemeRecentRank = Record<string, unknown>;
export type ThemeLeaderStock = Record<string, unknown>;
export type ThemeAnalyticsSummary = Record<string, unknown>;

export interface StockWorkspaceView {
  stock_id: string;
  stock_detail?: Record<string, unknown> | null;
  themes?: Record<string, unknown>[] | null;
  money_flow?: Record<string, unknown>[] | null;
  dragon_tiger?: Record<string, unknown>[] | null;
  auction_validation?: Record<string, unknown>[] | null;
  kline?: {
    position?: Record<string, unknown> | null;
    pattern?: Record<string, unknown> | null;
  } | null;
  diagnostics?: {
    partial: boolean;
    missing_sections: string[];
  };
}

export interface MarketReportSection {
  heading: string;
  items: string[];
}

export interface MarketReportView {
  report_type: "pre_market" | "post_market";
  trade_date: string;
  title: string;
  summary: string;
  highlights: string[];
  sections: MarketReportSection[];
}

export interface RecapDefaultsView {
  latest_post_market_date?: string | null;
  latest_pre_market_date?: string | null;
}

export interface CollectionAvailability {
  server_time: string;
  allowed: boolean;
  message: string;
  trade_date?: string | null;
}

export interface CollectionTaskItem {
  key: string;
  title: string;
  status: "pending" | "running" | "success" | "failed" | "cancelled" | "skipped";
  progress_percent: number;
  current_label?: string;
  error_message?: string;
}

export interface CollectionJobStatus {
  job_id: string;
  trade_date: string;
  status: "idle" | "running" | "success" | "failed" | "cancelled" | "paused";
  current_step?: string;
  total_steps: number;
  completed_steps: number;
  progress_percent: number;
  can_cancel: boolean;
  can_continue: boolean;
  logs: string[];
  tasks: CollectionTaskItem[];
  last_error?: {
    step: string;
    message: string;
    detail?: string;
  } | null;
}

export interface RealtimeCollectorActionPayload {
  with_frontend?: boolean;
  restart?: boolean;
  force?: boolean;
}

export interface RealtimeCollectorCommandResult {
  ok: boolean;
  return_code: number;
  stdout: string;
  stderr: string;
  command: string[];
}

export interface RealtimeCollectorLogs {
  log_dir: string;
  lines: number;
  files: Record<string, string[]>;
}

function normalizeRealtimeCollectorError(err: unknown, action: string): Error {
  if (err instanceof Error) {
    const lower = err.message.toLowerCase();
    if (
      lower.includes("failed to fetch") ||
      lower.includes("networkerror") ||
      lower.includes("network error") ||
      lower.includes("request failed: 500") ||
      lower.includes("econnrefused")
    ) {
      return new Error(
        `${action}失败: 无法连接前端BFF(127.0.0.1:8003)，请先启动 realtime stack（./scripts/run_realtime_stack.sh --with-frontend --restart）`,
      );
    }
    return err;
  }
  return new Error(`${action}失败: 未知网络异常`);
}

async function fetchJsonWithTimeout<T>(input: string, init?: RequestInit, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(input, { ...init, signal: controller.signal });
    if (!response.ok) {
      throw new Error(`request failed: ${response.status}`);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new Error(`request timeout after ${timeoutMs}ms`);
    }
    throw error;
  } finally {
    window.clearTimeout(timer);
  }
}

export async function fetchIntelFeed(params: {
  date?: string;
  type?: IntelItemType;
  session?: IntelSession;
  limit?: number;
}): Promise<IntelFeedView> {
  const query = new URLSearchParams();
  if (params.date) query.set("date", params.date);
  if (params.type) query.set("type", params.type);
  if (params.session) query.set("session", params.session);
  if (params.limit) query.set("limit", String(params.limit));

  try {
    return await fetchJsonWithTimeout<IntelFeedView>(`/api/intel/feed?${query.toString()}`, undefined, 10000);
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    throw new Error(`intel feed request failed: ${message}`);
  }
}

export async function fetchStrongStockWatch(params: {
  date?: string;
  windowDays?: number;
  limit?: number;
  latestPerStock?: boolean;
  includeRemoved?: boolean;
  stockId?: string;
}): Promise<StrongStockWatchView> {
  const query = new URLSearchParams();
  if (params.date) query.set("date", params.date);
  if (params.windowDays) query.set("window_days", String(params.windowDays));
  if (params.limit) query.set("limit", String(params.limit));
  if (params.latestPerStock !== undefined) query.set("latest_per_stock", String(params.latestPerStock));
  if (params.includeRemoved !== undefined) query.set("include_removed", String(params.includeRemoved));
  if (params.stockId) query.set("stock_id", params.stockId);

  try {
    const url = `/api/intel/strong-stocks/watch?${query.toString()}`;
    const getResp = await fetch(url, { method: "GET" });
    if (getResp.ok) {
      return (await getResp.json()) as StrongStockWatchView;
    }
    if (getResp.status === 405) {
      // 兼容旧网关/旧BFF仅放行POST的场景
      const postResp = await fetch(url, { method: "POST" });
      if (postResp.ok) {
        return (await postResp.json()) as StrongStockWatchView;
      }
      throw new Error(`request failed: ${postResp.status}`);
    }
    throw new Error(`request failed: ${getResp.status}`);
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    throw new Error(`strong stock watch request failed: ${message}`);
  }
}

export function openIntelStream(params: {
  date?: string;
  type?: IntelItemType;
  session?: IntelSession;
}): EventSource {
  const query = new URLSearchParams();
  if (params.date) query.set("date", params.date);
  if (params.type) query.set("type", params.type);
  if (params.session) query.set("session", params.session);
  query.set("limit", "20");
  return new EventSource(`/api/intel/stream?${query.toString()}`);
}

import { createSSEManager } from "./realtime/sseManager";
import type { SSEManagerOptions, SSEConnectionState, SSEEventHandlers } from "./realtime/sseManager";

// SSEManager相关导出
export type { SSEManagerOptions, SSEConnectionState, SSEEventHandlers } from "./realtime/sseManager";
export { SSEManager, createSSEManager } from "./realtime/sseManager";

/**
 * 创建Intel流SSE管理器实例
 *
 * 使用增强的SSE管理器，提供自动重试、心跳监控和连接状态管理。
 * 推荐在新的组件中使用此函数替代openIntelStream。
 */
export function createIntelStreamManager(
  params: {
    date?: string;
    type?: IntelItemType;
    session?: IntelSession;
  },
  eventHandlers?: SSEEventHandlers,
  options?: SSEManagerOptions
) {
  return createSSEManager(params, eventHandlers, options);
}

export async function fetchThemeWorkspace(subjectKey: string, tradeDate?: string): Promise<ThemeWorkspaceView> {
  const query = new URLSearchParams({
    include_history: "true",
    include_children: "true",
    include_stocks: "true",
    include_leaders: "false",
    stock_mapping_scope: "pool",
    history_limit: "8",
    children_limit: "8",
    stocks_limit: "10"
  });
  if (tradeDate) query.set("trade_date", tradeDate);
  const response = await fetch(`/api/theme-workspace/${subjectKey}?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`theme workspace request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchStockWorkspace(stockId: string): Promise<StockWorkspaceView> {
  const query = new URLSearchParams({
    include_themes: "true",
    include_leaders: "false",
    mapping_scope: "pool",
    themes_limit: "10"
  });
  const response = await fetch(`/api/stock-workspace/${stockId}?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`stock workspace request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchRecap(params: {
  date: string;
  reportType?: "pre_market" | "post_market";
}): Promise<MarketReportView> {
  const query = new URLSearchParams({
    date: params.date,
    report_type: params.reportType ?? "post_market",
  });
  const response = await fetch(`/api/recap?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`recap request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchRecapDefaults(): Promise<RecapDefaultsView> {
  const response = await fetch("/api/recap/defaults");
  if (!response.ok) {
    throw new Error(`recap defaults request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchCollectionAvailability(tradeDate?: string): Promise<CollectionAvailability> {
  const query = new URLSearchParams();
  if (tradeDate) query.set("trade_date", tradeDate);
  const response = await fetch(`/api/collection/availability?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`collection availability request failed: ${response.status}`);
  }
  return response.json();
}

export async function startCollection(payload: unknown): Promise<CollectionJobStatus> {
  const response = await fetch("/api/collection/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `collection start request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchCollectionStatus(jobId: string): Promise<CollectionJobStatus> {
  const response = await fetch(`/api/collection/status?job_id=${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    throw new Error(`collection status request failed: ${response.status}`);
  }
  return response.json();
}

export async function cancelCollection(jobId: string): Promise<CollectionJobStatus> {
  const response = await fetch("/api/collection/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId }),
  });
  if (!response.ok) {
    throw new Error(`collection cancel request failed: ${response.status}`);
  }
  return response.json();
}

export async function continueCollection(jobId: string): Promise<CollectionJobStatus> {
  const response = await fetch("/api/collection/continue", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job_id: jobId }),
  });
  if (!response.ok) {
    throw new Error(`collection continue request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchRealtimeCollectorStatus(): Promise<RealtimeCollectorCommandResult> {
  try {
    return await fetchJsonWithTimeout<RealtimeCollectorCommandResult>(
      "/api/realtime/collector/status",
      undefined,
      15000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "状态检查");
  }
}

export async function startRealtimeCollector(
  payload: RealtimeCollectorActionPayload = {},
): Promise<RealtimeCollectorCommandResult> {
  try {
    return await fetchJsonWithTimeout<RealtimeCollectorCommandResult>(
      "/api/realtime/collector/start",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      45000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "启动");
  }
}

export async function stopRealtimeCollector(
  payload: RealtimeCollectorActionPayload = {},
): Promise<RealtimeCollectorCommandResult> {
  try {
    return await fetchJsonWithTimeout<RealtimeCollectorCommandResult>(
      "/api/realtime/collector/stop",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
      30000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "停止");
  }
}

export async function fetchRealtimeCollectorLogs(lines = 200): Promise<RealtimeCollectorLogs> {
  try {
    return await fetchJsonWithTimeout<RealtimeCollectorLogs>(
      `/api/realtime/collector/logs?lines=${encodeURIComponent(String(lines))}`,
      {
        cache: "no-store",
      },
      15000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "日志拉取");
  }
}
