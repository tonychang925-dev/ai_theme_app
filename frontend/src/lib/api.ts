export type IntelItemType = "all" | "event" | "event_review" | "theme_move" | "new_theme" | "stock_move" | "recap" | "weak_to_strong" | "theme_cycle" | "theme_identity" | "stock_signal" | "theme_history";
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
  };
}

export interface IntelFeedEvent {
  event_id: string;
  occurred_at: string;
  event_type: "event" | "event_review" | "theme_move" | "new_theme" | "stock_move";
  item: IntelFeedItem;
  cursor?: string;
}

export interface ThemeRadarItem {
  theme_id: string;
  theme_name: string;
  heat: number;
  stage: string;
  stock_count: number;
}

export interface ThemeRadarView {
  date?: string;
  themes: ThemeRadarItem[];
  source?: string;
}

export interface IntelContextView {
  date?: string;
  subject_key?: string | null;
  stock_id?: string | null;
  items: IntelFeedItem[];
  count: number;
  diagnostics?: Record<string, unknown>;
  source?: string;
}

export interface MarketValidationView {
  trade_date: string;
  subject_key?: string | null;
  stock_id?: string | null;
  candidate_level: string;
  support_type: string;
  support_score: number | null;
  reject_reasons: string[];
  strong_watch_count: number;
  w2s_candidate_count: number;
  stock_validation?: Record<string, unknown> | null;
  source?: string;
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
  stock_info?: Record<string, unknown> | null;
  profile_ext?: Record<string, unknown> | null;
  lightspots?: Record<string, unknown>[] | null;
  daily_snapshots?: Record<string, unknown>[] | null;
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

export interface RecapViewModelV2 extends MarketReportView {
  source: "recap_v2_snapshot" | "recap_v2_report";
  diagnostics?: {
    snapshot_version?: string;
  };
}

interface PostMarketSnapshotView {
  trade_date: string;
  snapshot_version: string;
  payload: Record<string, unknown>;
}

export interface RecapDefaultsView {
  latest_post_market_date?: string | null;
  latest_pre_market_date?: string | null;
}

export interface PreMarketBriefEvent {
  event_id?: string | number | null;
  item_id?: string;
  occurred_at?: string;
  title?: string;
  summary?: string;
  subject_key?: string;
  theme_name?: string;
  confidence?: number | null;
  impact_score?: number | null;
  source_type?: string;
  source_channel?: string;
  reason?: string;
}

export interface PreMarketBriefTheme {
  subject_key?: string;
  theme_name?: string;
  event_count?: number;
  latest_event_title?: string;
  confidence?: number | null;
  impact_score?: number | null;
  event_ids?: Array<string | number | null>;
}

export interface PreMarketOpportunityStock {
  stock_id?: string;
  stock_name?: string;
  level?: "A" | "B" | "C" | string;
  score?: number | null;
  reason?: string;
  risk?: string;
  evidence?: Record<string, unknown>;
}

export interface PreMarketOpportunity {
  subject_key?: string;
  theme_name?: string;
  event_count?: number;
  latest_event_title?: string;
  theme_confidence?: number | null;
  tiers?: Record<string, PreMarketOpportunityStock[]>;
  stocks?: PreMarketOpportunityStock[];
}

export interface PreMarketAlert {
  alert_type?: string;          // "risk" | "opportunity"
  alert_level?: string;        // "critical" | "important" | "normal"
  alert_score?: number;        // 0-100
  reason_code?: string;        // R01_DELISTING, O01_CONTRACT, etc.
  reason?: string;
  title?: string;
  summary?: string;
  message?: string;            // 汇总类告警的描述
  count?: number;              // 关联事件数量
  stock_code?: string;
  stock_name?: string;
  publish_time?: string;
  dedupe_key?: string;
  amount?: string;
  impact_score?: number;
  source_event_id?: number;
  risk_type?: string;          // human_review_pending | unknown_event_watch
  events?: Array<{             // 关联的子事件
    event_id?: number;
    title?: string;
    summary?: string;
    theme_name?: string;
    reason?: string;
  }>;
}

export interface PreMarketBriefSections {
  market_overview?: unknown[];
  overnight_global?: unknown[];
  major_events?: PreMarketBriefEvent[];
  matched_themes?: PreMarketBriefTheme[];
  event_driven_opportunities?: PreMarketOpportunity[];
  weak_to_strong_watch?: unknown[];
  review_events?: PreMarketBriefEvent[];
  unknown_watch?: PreMarketBriefEvent[];
  risk_alerts?: PreMarketAlert[];
  opportunity_alerts?: PreMarketAlert[];
  company_announcements_raw?: unknown[];
  company_announcements_matched?: unknown[];
}

export interface PreMarketBriefPayload {
  version?: string;
  trade_date?: string;
  status?: "draft" | "final" | "stale" | "partial" | string;
  sections?: PreMarketBriefSections;
  diagnostics?: Record<string, unknown>;
}

export interface PreMarketBriefView {
  ok?: boolean;
  trade_date: string;
  snapshot_version?: string;
  status?: string;
  payload: PreMarketBriefPayload;
  diagnostics?: Record<string, unknown>;
  generated_at?: string | null;
  finalized_at?: string | null;
  updated_at?: string | null;
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

// ── Phase 5: New-chain realtime stack status ──

export interface NewChainRealtimeStatus {
  running: boolean;
  run_id: string;
  started_at: string | null;
  akshare_pid?: number | null;
  raw_news_pid: number | null;
  decision_pid: number | null;
  rebuild_pid?: number | null;
  log_dir: string;
  last_error: string;
  profile_version: string;
  profile_status: string;
  profile_fallback: string;
  llm_judge_mode: string;
  structured_concurrency: number;
  pending_count: number;
  dead_letter_count: number;
  decision_stream_count?: number;
  review_queue_count?: number;
  akshare_collector?: Record<string, unknown>;
  brief_rebuild?: Record<string, unknown>;
  redis_streams?: Record<string, { length: number; groups: number }>;
  redis_error?: string;
}

export interface NewChainRealtimeResult {
  ok: boolean;
  status: string;
  error?: string;
  detail?: NewChainRealtimeStatus;
}

export interface RealtimeCollectorCommandResult {
  ok: boolean;
  return_code: number;
  stdout: string;
  stderr: string;
  command: string[];
}

export interface RealtimeCollectorActionPayload {
  with_frontend?: boolean;
  restart?: boolean;
  force?: boolean;
}

export interface RealtimeCollectorLogs {
  log_dir: string;
  lines: number;
  files: Record<string, string[]>;
}

export interface JyhfCdpCommandResult {
  ok: boolean;
  message: string;
  service_owner: string;
  collector_running: boolean;
  service_running: boolean;
  // Full status fields returned by _status_result (get_status() merge)
  service_pid?: number | null;
  service_port?: number;
  app_running?: boolean;
  cdp_connected?: boolean;
  cdp_port?: number;
  current_route?: string | null;
  current_tab?: string | null;
  last_capture_at?: string | null;
  last_event_at?: string | null;
  capture_count_total?: number;
  new_event_count_total?: number;
  duplicate_count_total?: number;
  parse_error_count_total?: number;
  pushed_to_stream_count_total?: number;
  pushed_to_intel_count_total?: number;
  review_queue_count_total?: number;
  last_error?: string | null;
  collector_status?: Record<string, unknown> | null;
  collector_state?: string;
}

export interface JyhfCdpCollectorStatus {
  service?: string;
  service_running?: boolean;
  service_owner?: string;
  service_pid?: number | null;
  service_port?: number;
  running: boolean;
  collector_running?: boolean;
  pid?: number | null;
  app_running: boolean;
  cdp_connected: boolean;
  cdp_port: number;
  current_route?: string | null;
  current_tab?: string | null;
  last_capture_at?: string | null;
  last_event_at?: string | null;
  capture_count_total: number;
  new_event_count_total: number;
  duplicate_count_total: number;
  parse_error_count_total: number;
  pushed_to_stream_count_total: number;
  pushed_to_intel_count_total?: number;
  review_queue_count_total: number;
  last_error?: string | null;
}

export interface JyhfCdpCollectorLogs {
  log_file: string;
  lines: string[];
}

function normalizeRealtimeCollectorError(err: unknown, action: string): Error {
  if (err instanceof Error) {
    const lower = err.message.toLowerCase();
    if (lower.includes("request failed: 502") || lower.includes("request failed: 503")) {
      if (action.includes("JYHF-CDP")) {
        return new Error(
          `${action}失败: JYHF CDP 服务(8095)未运行，web_app 无法连接上游。请点击"启动 JYHF DOM 采集"按钮自动拉起服务。`,
        );
      }
      return new Error(
        `${action}失败: 上游服务不可达 (502/503)，请确认依赖服务已启动`,
      );
    }
    if (
      lower.includes("failed to fetch") ||
      lower.includes("networkerror") ||
      lower.includes("network error") ||
      lower.includes("request failed: 500") ||
      lower.includes("econnrefused")
    ) {
      return new Error(
        `${action}失败: 无法连接 web_app_service(127.0.0.1:8000)，请先启动新链前端栈（./scripts/start_new_chain_stack.sh --restart --with-frontend）`,
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
    return await fetchJsonWithTimeout<IntelFeedView>(`/api/v2/intel/feed?${query.toString()}`, undefined, 10000);
  } catch (error) {
    const message = error instanceof Error ? error.message : "unknown error";
    throw new Error(`intel feed request failed: ${message}`);
  }
}

export async function fetchWorkspaceThemeRadar(params: {
  date?: string;
  session?: IntelSession;
  limit?: number;
}): Promise<ThemeRadarView> {
  const query = new URLSearchParams();
  if (params.date) query.set("date", params.date);
  if (params.session) query.set("session", params.session);
  if (params.limit) query.set("limit", String(params.limit));
  return fetchJsonWithTimeout<ThemeRadarView>(`/api/v2/workspace/theme-radar?${query.toString()}`, undefined, 10000);
}

export async function fetchWorkspaceIntelContext(params: {
  date?: string;
  session?: IntelSession;
  subjectKey?: string;
  stockId?: string;
  limit?: number;
}): Promise<IntelContextView> {
  const query = new URLSearchParams();
  if (params.date) query.set("date", params.date);
  if (params.session) query.set("session", params.session);
  if (params.subjectKey) query.set("subject_key", params.subjectKey);
  if (params.stockId) query.set("stock_id", params.stockId);
  if (params.limit) query.set("limit", String(params.limit));
  return fetchJsonWithTimeout<IntelContextView>(`/api/v2/workspace/intel-context?${query.toString()}`, undefined, 20000);
}

export async function fetchWorkspaceMarketValidation(params: {
  tradeDate: string;
  subjectKey?: string;
  stockId?: string;
}): Promise<MarketValidationView> {
  const query = new URLSearchParams();
  query.set("trade_date", params.tradeDate);
  if (params.subjectKey) query.set("subject_key", params.subjectKey);
  if (params.stockId) query.set("stock_id", params.stockId);
  return fetchJsonWithTimeout<MarketValidationView>(`/api/v2/workspace/market-validation?${query.toString()}`, undefined, 10000);
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

  // 强势股页面统一走 v2 口径，避免旧路由字段漂移。

  try {
    const url = `/api/v2/strong_watch/watch?${query.toString()}`;
    const getResp = await fetch(url, { method: "GET" });
    if (!getResp.ok) throw new Error(`request failed: ${getResp.status}`);
    return (await getResp.json()) as StrongStockWatchView;
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
  return new EventSource(`/api/v2/intel/stream?${query.toString()}`);
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
    stock_mapping_scope: "all",
    history_limit: "8",
    children_limit: "8",
    stocks_limit: "10"
  });
  if (tradeDate) query.set("trade_date", tradeDate);
  const response = await fetch(`/api/v1/theme/workspace/${subjectKey}?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`theme workspace request failed: ${response.status}`);
  }
  return response.json();
}

export async function fetchStockWorkspace(stockId: string): Promise<StockWorkspaceView> {
  const query = new URLSearchParams({
    include_themes: "true",
    include_leaders: "false",
    mapping_scope: "all",
    themes_limit: "10"
  });
  const response = await fetch(`/api/v1/stock/workspace/${stockId}`);
  if (!response.ok) {
    throw new Error(`stock workspace request failed: ${response.status}`);
  }
  return response.json();
}

function asMarketReportViewFromSnapshot(
  snapshot: PostMarketSnapshotView,
  reportType: "pre_market" | "post_market",
): RecapViewModelV2 | null {
  const payload = snapshot.payload || {};
  const maybe = payload["report"] || payload["recap"] || payload["market_report"];
  if (maybe && typeof maybe === "object") {
    const obj = maybe as Record<string, unknown>;
    const sections = Array.isArray(obj.sections) ? obj.sections : [];
    return {
      report_type: reportType,
      trade_date: String(obj.trade_date || snapshot.trade_date),
      title: String(obj.title || "盘后复盘"),
      summary: String(obj.summary || ""),
      highlights: Array.isArray(obj.highlights) ? obj.highlights.map((x) => String(x)) : [],
      sections: sections.map((s) => {
        const row = s as Record<string, unknown>;
        return {
          heading: String(row.heading || "--"),
          items: Array.isArray(row.items) ? row.items.map((x) => String(x)) : [],
        };
      }),
      source: "recap_v2_report",
      diagnostics: { snapshot_version: snapshot.snapshot_version },
    };
  }

  let recapDocRaw: Record<string, unknown> | null = null;
  if (payload["recap_doc"] && typeof payload["recap_doc"] === "object") {
    recapDocRaw = payload["recap_doc"] as Record<string, unknown>;
  } else if (typeof payload["candidate_count"] === "number") {
    // 新链格式：recap_doc 内容直接作为 payload 存储（无嵌套 recap_doc key）
    recapDocRaw = payload as Record<string, unknown>;
  }
  if (!recapDocRaw) return null;

  const candidateCount = Number(recapDocRaw["candidate_count"] || 0);
  const strongWatchInputCount = Number(recapDocRaw["strong_watch_input_count"] || recapDocRaw["strong_watch_input_7d_count"] || 0);
  const strongWatchPromotedCount = Number(recapDocRaw["strong_watch_promoted_count"] || 0);
  const strongWatchHistoryCount = Number(recapDocRaw["strong_watch_history_count"] || 0);
  const topCandidates = Array.isArray(recapDocRaw["top_candidates"]) ? (recapDocRaw["top_candidates"] as Array<Record<string, unknown>>) : [];

  const candidateItems = topCandidates.slice(0, 20).map((item, idx) => {
    const stockName = String(item["stock_name"] || item["stock_id"] || `候选${idx + 1}`);
    const score = item["score"] ?? item["composite_score"] ?? "--";
    const level = item["candidate_level"] ?? item["transition_type"] ?? "--";
    return `${idx + 1}. ${stockName}｜评分 ${score}｜级别 ${level}`;
  });

  return {
    report_type: reportType,
    trade_date: snapshot.trade_date,
    title: "盘后复盘（快照映射）",
    summary: `候选 ${candidateCount} | 强势池输入 ${strongWatchInputCount} | 晋级 ${strongWatchPromotedCount}`,
    highlights: [
      `snapshot_version: ${snapshot.snapshot_version}`,
      `strong_watch_history_count: ${strongWatchHistoryCount}`,
    ],
    sections: [
      {
        heading: "强势池与候选概览",
        items: [
          `candidate_count: ${candidateCount}`,
          `strong_watch_input_count: ${strongWatchInputCount}`,
          `strong_watch_promoted_count: ${strongWatchPromotedCount}`,
          `strong_watch_history_count: ${strongWatchHistoryCount}`,
        ],
      },
      {
        heading: "弱转强候选明细（Top）",
        items: candidateItems.length ? candidateItems : ["暂无候选"],
      },
    ],
    source: "recap_v2_snapshot",
    diagnostics: { snapshot_version: snapshot.snapshot_version },
  };
}

export async function fetchRecapSnapshot(params: {
  date: string;
  reportType?: "pre_market" | "post_market";
}): Promise<RecapViewModelV2> {
  const reportType = params.reportType ?? "post_market";
  const query = new URLSearchParams({ trade_date: params.date });
  const snapshot = await fetchJsonWithTimeout<PostMarketSnapshotView>(
    `/api/v2/post_market_snapshot?${query.toString()}`,
    undefined,
    10000,
  );
  const mapped = asMarketReportViewFromSnapshot(snapshot, reportType);
  if (!mapped) {
    throw new Error(`post-market snapshot is unavailable or unmappable for ${params.date}`);
  }
  return mapped;
}

export async function fetchRecapDefaults(): Promise<RecapDefaultsView> {
  const response = await fetch("/api/v2/recap/defaults");
  if (!response.ok) {
    throw new Error(`recap defaults request failed: ${response.status}`);
  }
  return response.json();
}

export interface NotionPublishResult {
  ok?: boolean;
  page_id?: string;
  page_url?: string;
  action?: string;
  report_id?: string;
  report_type?: string;
  trade_date?: string;
}

export async function publishRecapToNotion(tradeDate: string): Promise<NotionPublishResult> {
  return fetchJsonWithTimeout<NotionPublishResult>(
    "/api/v2/recap/publish-notion",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trade_date: tradeDate }),
    },
    45000,
  );
}

export async function publishPreMarketBriefToNotion(tradeDate: string): Promise<NotionPublishResult> {
  return fetchJsonWithTimeout<NotionPublishResult>(
    "/api/v1/pre_market_brief/publish-notion",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trade_date: tradeDate }),
    },
    45000,
  );
}

export async function fetchPreMarketBrief(tradeDate: string): Promise<PreMarketBriefView> {
  const query = new URLSearchParams({ trade_date: tradeDate });
  return fetchJsonWithTimeout<PreMarketBriefView>(
    `/api/v1/pre_market_brief?${query.toString()}`,
    undefined,
    15000,
  );
}

export async function fetchCollectionAvailability(tradeDate?: string): Promise<CollectionAvailability> {
  const query = new URLSearchParams();
  if (tradeDate) query.set("trade_date", tradeDate);
  const response = await fetch(`/api/v2/collection/availability?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`collection availability request failed: ${response.status}`);
  }
  return response.json();
}

export async function startCollection(payload: unknown): Promise<CollectionJobStatus> {
  const response = await fetch("/api/v2/collection/start", {
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
  const response = await fetch(`/api/v2/collection/status?job_id=${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    throw new Error(`collection status request failed: ${response.status}`);
  }
  return response.json();
}

export async function cancelCollection(jobId: string): Promise<CollectionJobStatus> {
  const response = await fetch("/api/v2/collection/cancel", {
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
  const response = await fetch("/api/v2/collection/continue", {
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
      "/api/v2/realtime/collector/status",
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
      "/api/v2/realtime/collector/start",
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
      "/api/v2/realtime/collector/stop",
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
      `/api/v2/realtime/collector/logs?lines=${encodeURIComponent(String(lines))}`,
      {
        cache: "no-store",
      },
      15000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "日志拉取");
  }
}

// ── Phase 5: New-chain realtime stack APIs (→ SPS:8090) ──

export async function fetchNewChainRealtimeStatus(): Promise<NewChainRealtimeStatus> {
  return fetchJsonWithTimeout<NewChainRealtimeStatus>(
    "/api/v1/realtime/status",
    { cache: "no-store" },
    10000,
  );
}

export async function startNewChainRealtime(): Promise<NewChainRealtimeResult> {
  return fetchJsonWithTimeout<NewChainRealtimeResult>(
    "/api/v1/realtime/start",
    { method: "POST", headers: { "Content-Type": "application/json" } },
    30000,
  );
}

export async function stopNewChainRealtime(): Promise<NewChainRealtimeResult> {
  return fetchJsonWithTimeout<NewChainRealtimeResult>(
    "/api/v1/realtime/stop",
    { method: "POST", headers: { "Content-Type": "application/json" } },
    30000,
  );
}

export async function fetchJyhfCdpCollectorStatus(): Promise<JyhfCdpCollectorStatus> {
  try {
    return await fetchJsonWithTimeout<JyhfCdpCollectorStatus>(
      "/api/v2/realtime/jyhf-cdp/status?_t=" + Date.now(),
      { cache: "no-store" },
      10000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-CDP 状态检查");
  }
}

export async function startJyhfCdpCollector(): Promise<JyhfCdpCommandResult> {
  try {
    return await fetchJsonWithTimeout<JyhfCdpCommandResult>(
      "/api/v2/realtime/jyhf-cdp/start",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
      45000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-CDP 启动");
  }
}

export async function stopJyhfCdpCollector(): Promise<JyhfCdpCommandResult> {
  try {
    return await fetchJsonWithTimeout<JyhfCdpCommandResult>(
      "/api/v2/realtime/jyhf-cdp/stop",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      },
      10000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-CDP 停止");
  }
}

export async function fetchJyhfCdpCollectorLogs(lines = 300): Promise<JyhfCdpCollectorLogs> {
  try {
    return await fetchJsonWithTimeout<JyhfCdpCollectorLogs>(
      `/api/v2/realtime/jyhf-cdp/logs?lines=${encodeURIComponent(String(lines))}`,
      { cache: "no-store" },
      10000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-CDP 日志拉取");
  }
}
