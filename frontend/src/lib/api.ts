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
  theme_validation?: {
    theme_name?: string;
    cycle_stage?: string;
    mainline_strength?: number;
    fade_risk?: number;
    mainline_alive?: boolean;
    leader_stocks?: Array<{ name?: string; score?: number; pct_chg?: number }>;
    source?: string;
  } | null;
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

// ── DailyReview 结构化接口（P3） ──

export interface ThemeReview {
  subject_key: string;
  theme_name: string;
  theme_stage: string;
  theme_strength?: string;
  mainline_strength_score: number;
  fade_risk_score: number;
  final_cycle_state: string;
  final_mainline_alive: boolean;
  capital_validation?: string;
  total_inflow?: number;
  leader_inflow?: number;
  theme_kline?: string;
  leader_stocks: LeaderStockBrief[];
  event_chain: ThemeEventItem[];
  action_advice: string;
  conclusion: string;
  diagnostics?: {
    cycle_joined: boolean;
    capital_joined: boolean;
    leader_count: number;
  };
}

export interface LeaderStockBrief {
  stock_id?: string;
  stock_name?: string;
  leader_composite_score?: number;
  leader_capital_score?: number;
  pct_chg?: number;
}

export interface ThemeEventItem {
  event_id?: string;
  event_date?: string;
  title?: string;
  description?: string;
  event_level?: string;
  credibility?: string;
}

export interface CapitalReview {
  stock_code?: string;
  stock_name?: string;
  net_buy_amount?: number;
  seat_type?: string;
  related_theme?: string;
  ai_comment?: string;
}

export interface StrongStockReview {
  stock_code: string;
  stock_name: string;
  subject_key: string;
  theme_name: string;
  role: string;
  watch_status: string;
  strong_grade?: string;
  watch_score: number;
  support_type: string;
  support_score: number;
  money_flow_tier?: string;
  role_enhanced?: string;
  main_net_inflow?: number;
  pct_chg?: number;
  turnover_rate?: number;
  volume_ratio?: number;
  position_label?: string;
  pattern_labels?: string[];
  rationale?: string;
}

export interface DailyReviewView {
  trade_date: string;
  market_summary: Record<string, unknown>;
  theme_reviews: ThemeReview[];
  capital_reviews: CapitalReview[];
  strong_stock_reviews?: StrongStockReview[];
  trading_principle: Record<string, unknown>;
  diagnostics?: Record<string, unknown>;
}

export interface ModuleCoverage {
  status: "ready" | "empty" | "partial" | "failed";
  row_count: number;
  required: boolean;
  source: "structured" | "legacy_sections" | "none";
  missing_fields: string[];
  column_missing_fields?: string[];
  upstream_tables: Record<string, number>;
  message?: string;
  legacy_row_count?: number;
}

export interface DailyReviewV2Diagnostics {
  module_coverage: {
    market_summary: ModuleCoverage;
    theme_reviews: ModuleCoverage;
    theme_capital_reviews: ModuleCoverage;
    strong_stock_reviews: ModuleCoverage;
    watchlist_reviews: ModuleCoverage;
    stock_capital_reviews: ModuleCoverage;
    abnormal_reviews: ModuleCoverage;
    money_flow_reviews: ModuleCoverage;
    dragon_tiger_reviews: ModuleCoverage;
  };
  source_tables: Record<string, number>;
  column_missing_fields?: Record<string, string[]>;
  warnings: string[];
  errors: string[];
  legacy_sections_available: boolean;
  legacy_section_counts: Record<string, number>;
}

export interface MarketSummaryReview {
  market_bias: string;
  action_bias: string;
  market_health_score?: number | null;
  breadth_status?: string | null;
  short_term_sentiment_status?: string | null;
  relay_sentiment_status?: string | null;
  intraday_fade_status?: string | null;
  conclusion: string;
  highlights: string[];
  risk_flags: string[];
  diagnostics?: Record<string, unknown>;
}

export interface ThemeReviewV2 {
  subject_key: string;
  theme_name: string;
  tier: "mainline" | "strong_branch" | "watch" | "fading" | "unknown";
  decision?: string | null;
  decision_score?: number | null;
  capital_validation?: "positive" | "neutral" | "divergent" | "negative" | "unknown" | string | null;
  position_suggestion?: number | null;
  next_day_watch_points?: string[];
  invalidation_conditions?: string[];
  total_inflow: number | null;
  leader_inflow: number | null;
  theme_kline: string | null;
  event_score: number | null;
  market_score: number | null;
  mainline_strength_score: number | null;
  fade_risk_score: number | null;
  cycle_stage: string;
  final_cycle_state: string;
  final_mainline_alive: boolean;
  action_advice: string;
  conclusion: string;
  leader_stocks?: PostMarketDailyReviewV2ModuleRow[];
  event_chain?: PostMarketDailyReviewV2ModuleRow[];
  diagnostics?: Record<string, unknown>;
}

export interface ThemeCapitalReview {
  subject_key: string;
  theme_name: string;
  tier: "mainline" | "strong_branch" | "watch" | "unknown";
  total_inflow: number;
  top3_inflow: number | null;
  leader_inflow: number | null;
  inflow_stock_count: number | null;
  theme_kline: string | null;
  cycle_stage: string | null;
  action: string | null;
  rank_order: number;
  diagnostics?: Record<string, unknown>;
}

export interface StrongStockReviewV2 {
  stock_id: string;
  stock_code: string;
  stock_name: string;
  subject_key: string;
  theme_name: string;
  role: "leader" | "sub_leader" | "trend" | "watch" | "observe_only" | "reject" | "unknown";
  role_label: string;
  candidate_level: "formal" | "observe_only" | "reject" | "unknown";
  candidate_source: string;
  composite_score: number | null;
  purity_score: number | null;
  leading_score: number | null;
  capital_score: number | null;
  structure_score: number | null;
  resilience_score: number | null;
  money_flow: {
    main_net_inflow: number | null;
    money_flow_tier: string | null;
    role_enhanced: string | null;
  };
  kline: {
    position_label: string | null;
    pattern_labels: string[];
    pattern_summary: string | null;
  };
  support: {
    support_type: string | null;
    support_score: number | null;
    support_reason: string | null;
  };
  llm: {
    judgement: string | null;
    reason: string | null;
    confirmation_basis: string | null;
  };
  rationale: string;
  rejection_reason?: string | null;
  diagnostics: Record<string, unknown>;
}

export interface WatchlistReviewV2 {
  stock_id: string;
  stock_code: string;
  stock_name: string;
  subject_key: string;
  theme_name: string;
  category: "重点观察" | "弱转强观察" | "风险观察" | "其他" | string;
  role_label: string;
  stage: string | null;
  action: string | null;
  buy_condition?: string[];
  invalid_condition?: string[];
  risk_level?: string | null;
  suggested_position?: number | null;
  volume_ratio: number | null;
  pattern: string | null;
  flags: string[];
  dragon_tiger_days: number | null;
  catalyst: string | null;
  abnormal_labels: string[];
  priority: number;
  reason: string;
  diagnostics?: Record<string, unknown>;
}

export interface StockCapitalReviewV2 {
  stock_id: string;
  stock_code: string;
  stock_name: string;
  subject_key: string;
  theme_name: string;
  main_net_inflow: number;
  rank_in_theme: number | null;
  rank_overall: number | null;
  pct_chg: number | null;
  turnover_rate: number | null;
  volume_ratio: number | null;
  is_leader: boolean;
  flags: string[];
  diagnostics?: Record<string, unknown>;
}

export interface AbnormalStockReviewV2 {
  stock_id: string;
  stock_code: string;
  stock_name: string;
  subject_key: string | null;
  theme_name: string | null;
  abnormal_score: number;
  turnover_rate: number | null;
  volume_ratio: number | null;
  volume_vs_ma50: number | null;
  capital: {
    main_net_inflow: number | null;
    inflow_rank: number | null;
    money_flow_tier: string | null;
  };
  labels: string[];
  conclusion: string;
  diagnostics: Record<string, unknown>;
}

export interface MoneyFlowReviewV2 {
  stock_id: string;
  stock_code: string;
  stock_name: string;
  subject_key: string;
  theme_name: string;
  main_net_inflow: number | null;
  money_flow_tier: string | null;
  role_enhanced: string | null;
  institution_signal: string | null;
  hot_money_signal: string | null;
  dragon_tiger_signal: string | null;
  conclusion: string;
  kline?: {
    position_label: string | null;
    pattern_labels: string[];
    pattern_summary: string | null;
  };
  diagnostics?: Record<string, unknown>;
}

export interface DragonTigerReviewV2 {
  stock_id: string;
  stock_code: string;
  stock_name: string;
  subject_key: string | null;
  theme_name: string | null;
  net_buy: number | null;
  buy_amount: number | null;
  sell_amount: number | null;
  seat_type: "INSTITUTION" | "HOT_MONEY" | "MIXED" | "UNKNOWN";
  hot_money_name: string | null;
  institution_seat_count: number | null;
  reason: string | null;
  continuous_days: number | null;
  side_summary: string;
  seat_summary: string[];
  diagnostics: Record<string, unknown>;
}

export type PostMarketDailyReviewV2ModuleRow = Record<string, unknown>;

export interface PostMarketDailyReviewV2 {
  schema_version: "daily_review_v2";
  trade_date: string;
  report_type: "post_market";
  snapshot_version: string;
  generated_at: string;
  data_mode: "daily_review_v2_first";
  source: {
    snapshot_id?: string | null;
    recap_snapshot_version?: string | null;
    derived_data_status: "ready" | "failed_precondition" | "partial";
    recap_generate_status: "success" | "skipped_idempotent" | "failed";
  };
  market_environment_review?: Record<string, unknown>;
  market_summary: MarketSummaryReview;
  theme_reviews: ThemeReviewV2[];
  theme_capital_reviews: ThemeCapitalReview[];
  strong_stock_reviews: StrongStockReviewV2[];
  watchlist_reviews: WatchlistReviewV2[];
  stock_capital_reviews: StockCapitalReviewV2[];
  abnormal_reviews: AbnormalStockReviewV2[];
  money_flow_reviews: MoneyFlowReviewV2[];
  dragon_tiger_reviews: DragonTigerReviewV2[];
  trading_principle: Record<string, unknown>;
  diagnostics: DailyReviewV2Diagnostics;
}

// ── P1-6: PostMarket readiness / jobs status ──

export interface PostMarketReadinessView {
  trade_date: string;
  status: "ready" | "failed_precondition" | string;
  error_code?: string;
  missing_tables?: string[];
  skipped_tables?: Array<{ table: string; reason?: string }>;
  base_tables?: Record<string, number>;
  derived_tables?: Record<string, number>;
  diagnostics?: Record<string, unknown>;
}

export interface PostMarketJobStatusItem {
  job_key: string;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  diagnostics?: Record<string, unknown>;
}

export interface PostMarketJobsStatusView {
  trade_date: string;
  items: PostMarketJobStatusItem[];
  summary?: {
    has_running?: boolean;
    has_failed?: boolean;
    all_success?: boolean;
    latest_status?: string;
  };
}

export async function fetchPostMarketReadiness(date: string): Promise<PostMarketReadinessView> {
  return fetchJsonWithTimeout<PostMarketReadinessView>(
    `/api/v2/post-market/derived-data/readiness?date=${encodeURIComponent(date)}`,
    undefined,
    15000,
  );
}

export async function fetchPostMarketJobsStatus(date: string): Promise<PostMarketJobsStatusView> {
  return fetchJsonWithTimeout<PostMarketJobsStatusView>(
    `/api/v2/post-market/jobs/status?date=${encodeURIComponent(date)}`,
    undefined,
    15000,
  );
}

const POST_MARKET_DERIVED_DATA_GENERATE_TIMEOUT_MS = 600000;
const POST_MARKET_RECAP_GENERATE_TIMEOUT_MS = 300000;
const POST_MARKET_DAILY_REVIEW_V2_GENERATE_TIMEOUT_MS = 180000;

export async function generatePostMarketDerivedData(date: string, force = false): Promise<Record<string, unknown>> {
  return fetchJsonWithTimeout<Record<string, unknown>>(
    `/api/v2/post-market/derived-data/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trade_date: date, force }),
    },
    POST_MARKET_DERIVED_DATA_GENERATE_TIMEOUT_MS,
  );
}

export async function generatePostMarketRecap(date: string, force = false): Promise<Record<string, unknown>> {
  return fetchJsonWithTimeout<Record<string, unknown>>(
    `/api/v2/post-market/recap/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trade_date: date, force }),
    },
    POST_MARKET_RECAP_GENERATE_TIMEOUT_MS,
  );
}

// ── DailyReview ──

export async function fetchDailyReview(date: string): Promise<DailyReviewView> {
  return fetchJsonWithTimeout<DailyReviewView>(
    `/api/v2/daily-review?date=${encodeURIComponent(date)}`,
    undefined,
    30000,
  );
}

export async function fetchDailyReviewV2(date: string): Promise<PostMarketDailyReviewV2> {
  return fetchJsonWithTimeout<PostMarketDailyReviewV2>(
    `/api/v2/daily-review-v2?date=${encodeURIComponent(date)}`,
    undefined,
    30000,
  );
}

export interface IndexCollectResult {
  success: boolean;
  trade_date: string;
  collected_count: number;
  technical_count: number;
  total_count: number;
  missing_indices: string[];
  source: string;
}

export async function collectIndexKline(payload: { trade_date?: string; force?: boolean }): Promise<IndexCollectResult> {
  return fetchJsonWithTimeout<IndexCollectResult>(
    `/api/v2/index-kline/collect`,
    { method: "POST", body: JSON.stringify(payload || {}), headers: { "Content-Type": "application/json" } },
    120000,
  );
}

export async function fetchIndexKlineStatus(tradeDate: string): Promise<IndexCollectResult> {
  return fetchJsonWithTimeout<IndexCollectResult>(
    `/api/v2/index-kline/status?trade_date=${encodeURIComponent(tradeDate)}`,
    {}, 5000,
  );
}

export async function generateDailyReviewV2(date: string, force = false): Promise<Record<string, unknown>> {
  return fetchJsonWithTimeout<Record<string, unknown>>(
    `/api/v2/post-market/daily-review-v2/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ trade_date: date, force }),
    },
    POST_MARKET_DAILY_REVIEW_V2_GENERATE_TIMEOUT_MS,
  );
}

// ──

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
  jyhf_reason?: string;
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
  running_verified?: boolean;
  status_source?: string;
  run_id: string;
  started_at: string | null;
  akshare_pid?: number | null;
  raw_news_pid: number | null;
  decision_pid: number | null;
  rebuild_pid?: number | null;
  db_collector_pid?: number | null;
  db_collector_enabled?: boolean;
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
  qwen_dedup_ready?: boolean;
  qwen_dedup_calls?: number;
  semantic_dedup_count?: number;
  prefilter_skipped?: number;
  news_dedup_skipped?: number;
  news_published_total?: number;
  hard_protect_count?: number;
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
  run_id?: string | null;
  lines: number;
  max_age_minutes?: number;
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
  return fetchJsonWithTimeout<ThemeRadarView>(`/api/v2/workspace/theme-radar?${query.toString()}`, undefined, 20000);
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
  const response = await fetch(`/api/v2/theme_workspace/${encodeURIComponent(subjectKey)}?${query.toString()}`);
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
  const response = await fetch(`/api/v2/stock_workspace/${encodeURIComponent(stockId)}?${query.toString()}`);
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
    60000,
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
    `/api/v2/pre_market_brief?${query.toString()}`,
    undefined,
    15000,
  );
}

// ── Phase 6A: Review Queue ──

export interface ReviewQueueItem {
  id: number;
  event_id: number;
  review_status: string;
  proposed_theme_name: string | null;
  proposed_theme_confidence: number | null;
  reason: string | null;
  source_channel: string;
  created_at: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  event_title: string | null;
  event_summary: string | null;
  event_type: string | null;
  raw_title: string | null;
  raw_content?: string | null;
  event_source?: string | null;
  raw_source_channel?: string | null;
  publish_date?: string | null;
  publish_time?: string | null;
}

export interface ReviewQueueListResponse {
  items: ReviewQueueItem[];
  total: number;
  page: number;
  page_size: number;
}

export async function fetchReviewQueue(params: {
  page?: number;
  page_size?: number;
  status?: string;
  source?: string;
} = {}): Promise<ReviewQueueListResponse> {
  const query = new URLSearchParams();
  if (params.page) query.set("page", String(params.page));
  if (params.page_size) query.set("page_size", String(params.page_size));
  if (params.status) query.set("status", params.status);
  if (params.source) query.set("source", params.source);
  return fetchJsonWithTimeout<ReviewQueueListResponse>(
    `/api/v2/review-queue/events?${query.toString()}`,
    { cache: "no-store" },
    10000,
  );
}

export async function fetchReviewQueueDetail(id: number): Promise<ReviewQueueItem> {
  return fetchJsonWithTimeout<ReviewQueueItem>(
    `/api/v2/review-queue/events/${id}`,
    { cache: "no-store" },
    10000,
  );
}

export async function confirmReviewEvent(id: number, reviewedBy?: string, reviewNote?: string): Promise<{ ok: boolean }> {
  return fetchJsonWithTimeout<{ ok: boolean }>(
    `/api/v2/review-queue/events/${id}/confirm`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reviewed_by: reviewedBy || "", review_note: reviewNote || "" }),
    },
    10000,
  );
}

export async function deleteReviewEvent(id: number): Promise<{ ok: boolean }> {
  return fetchJsonWithTimeout<{ ok: boolean }>(
    `/api/v2/review-queue/events/${id}`,
    { method: "DELETE" },
    10000,
  );
}

export async function batchDeleteReviewEvents(ids: number[]): Promise<{ ok: boolean; deleted_count: number }> {
  return fetchJsonWithTimeout<{ ok: boolean; deleted_count: number }>(
    `/api/v2/review-queue/events/batch-delete`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    },
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

export async function fetchRealtimeCollectorLogs(
  lines = 200,
  maxAgeMinutes = 180,
): Promise<RealtimeCollectorLogs> {
  try {
    return await fetchJsonWithTimeout<RealtimeCollectorLogs>(
      `/api/v2/realtime/collector/logs?lines=${encodeURIComponent(String(lines))}&max_age_minutes=${encodeURIComponent(String(maxAgeMinutes))}`,
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
    "/api/v2/realtime/new-chain/status",
    { cache: "no-store" },
    10000,
  );
}

// ── P0-C2: 统一状态聚合接口 ──

export interface StatusBundle {
  new_chain: Record<string, unknown>;
  jyhf_cdp: Record<string, unknown>;
  jyhf_auction: Record<string, unknown>;
  timestamp: string;
}

export async function fetchStatusBundle(): Promise<StatusBundle> {
  return fetchJsonWithTimeout<StatusBundle>(
    "/api/v2/realtime/status-bundle?_t=" + Date.now(),
    { cache: "no-store" },
    10000,
  );
}

export async function startNewChainRealtime(): Promise<NewChainRealtimeResult> {
  return fetchJsonWithTimeout<NewChainRealtimeResult>(
    "/api/v2/realtime/new-chain/start",
    { method: "POST", headers: { "Content-Type": "application/json" } },
    30000,
  );
}

export async function stopNewChainRealtime(): Promise<NewChainRealtimeResult> {
  return fetchJsonWithTimeout<NewChainRealtimeResult>(
    "/api/v2/realtime/new-chain/stop",
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
      120000,
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

// ── P2-B-4: JYHF 竞价采集 ──

export interface JyhfAuctionStatus {
  running: boolean;
  state: string;         // idle | waiting_auction | collecting | finished | error | stopped
  started_at: string | null;
  trade_date: string | null;
  candidate_date: string | null;
  rounds: number;
  points: number;
  pid: number | null;
  last_error: string | null;
}

export async function fetchJyhfAuctionStatus(): Promise<JyhfAuctionStatus> {
  try {
    return await fetchJsonWithTimeout<JyhfAuctionStatus>(
      "/api/v2/realtime/jyhf-auction/status?_t=" + Date.now(),
      { cache: "no-store" },
      10000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-竞价 状态检查");
  }
}

export async function startJyhfAuctionCollector(
  tradeDate: string,
  candidateDate: string,
): Promise<JyhfAuctionStatus> {
  try {
    return await fetchJsonWithTimeout<JyhfAuctionStatus>(
      "/api/v2/realtime/jyhf-auction/start",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trade_date: tradeDate, candidate_date: candidateDate }),
      },
      15000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-竞价 启动");
  }
}

export async function stopJyhfAuctionCollector(): Promise<JyhfAuctionStatus> {
  try {
    return await fetchJsonWithTimeout<JyhfAuctionStatus>(
      "/api/v2/realtime/jyhf-auction/stop",
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({}) },
      10000,
    );
  } catch (err) {
    throw normalizeRealtimeCollectorError(err, "JYHF-竞价 停止");
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

// ── P1-H: K线支撑告警 SSE ──

export interface KlineAlertEvent {
  stock_id: string;
  stock_name: string;
  support_type: string;
  support_level: string;
  support_strength: string;
  support_level_age_days: string;
  current: string;
  distance_pct: string;
  alert_type: string;
  severity: string;
  previous_state: string;
  confirm_count: string;
  confidence: string;
  quote_ts: string;
  generated_at: string;
  pct_chg: string;
}

// ── P1-I-1b: W2S 竞价弱转强告警 SSE ──

export interface W2SAlertEvent {
  trade_date: string;
  candidate_trade_date: string;
  candidate_id: string;
  stock_id: string;
  stock_name: string;
  theme_name: string;
  candidate_type: string;
  weak_type: string;
  confirm_level: string;
  confirm_score: string;
  auction_open_pct: string;
  carry_ratio: string;
  last_minute_ratio: string;
  price_path_stability_score: string;
  shape_features: string;
  evidence_rules: string;
  reject_reason_code: string;
  data_status: string;
  source: string;
  severity: string;
  generated_at: string;
  // 统一告警 (phase=auction/intraday)
  phase?: string;
  unified_level?: string;
  intraday_level?: string;
  intraday_score?: number;
  d2_level?: string;
  d2_score?: number;
  capital_flow?: string;
  current?: number;
  vwap?: number;
  above_vwap_ratio?: number;
  relative_strength?: number;
}

// P0-D: SSE 前端直连 SPS:8090，去掉 BFF 代理一跳
const SPS_BASE = import.meta.env.VITE_SPS_BASE_URL || "http://127.0.0.1:8090";

export function openW2SAlertsStream(
  onAlert: (alert: W2SAlertEvent) => void,
  onError?: (err: Error) => void,
): EventSource {
  const es = new EventSource(`${SPS_BASE}/api/v1/w2s-alerts/stream`);
  es.addEventListener("w2s_alert", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data) as W2SAlertEvent;
      onAlert(data);
    } catch { /* skip malformed */ }
  });
  es.addEventListener("error", () => {
    if (es.readyState === EventSource.CLOSED && onError) {
      onError(new Error("W2S alerts SSE disconnected"));
    }
  });
  return es;
}

export function openKlineAlertsStream(
  onAlert: (alert: KlineAlertEvent) => void,
  onError?: (err: Error) => void,
): EventSource {
  const es = new EventSource(`${SPS_BASE}/api/v1/kline-alerts/stream`);
  es.addEventListener("kline_alert", (e: MessageEvent) => {
    try {
      const data = JSON.parse(e.data) as KlineAlertEvent;
      onAlert(data);
    } catch {
      // skip malformed
    }
  });
  es.addEventListener("error", () => {
    if (es.readyState === EventSource.CLOSED && onError) {
      onError(new Error("Kline alerts SSE disconnected"));
    }
  });
  return es;
}

// ── P4-2A: Realtime Business Orchestrator ──

export interface OrchestratorServiceState {
  name: string;
  enabled: boolean;
  desired_state: string;    // disabled | wanted | not_in_window | observe
  observed_state: string;   // unknown | ready | running | stopped | blocked | degraded | failed
  owner: string;
  dependencies: string[];
  blockers: string[];
  evidence: Record<string, unknown>;
  last_action: string | null;
  last_error: string | null;
  next_retry_at: string | null;
}

export interface RedisStreamHealth {
  exists?: boolean;
  length?: number | null;
  memory_bytes?: number | null;
  state?: string;
  last_id?: string | null;
  last_event_at?: string | null;
  blockers?: string[];
}

export interface ConsumerGroupEntry {
  name: string;
  consumers: number;
  pending: number;
  lag: number;
  last_delivered_id: string;
  delivery_lag_s?: number | null;
  consumers_detail?: ConsumerDetail[];
}

export interface ConsumerDetail {
  name: string;
  idle_ms: number;
  pending: number;
}

export interface ConsumerGroupSummary {
  stream: string;
  group: string;
  consumers: number;
  pending: number;
  lag: number;
  delivery_lag_s?: number | null;
}

export interface DlqGrowthEntry {
  trend: "growing" | "stable" | "shrinking" | "unknown";
  delta: number;
  delta_pct: number;
  prev_length: number;
  since_s: number;
}

export interface RedisRuntimeHealth {
  ok?: boolean;
  state?: string;
  redis_state?: string;
  stream_state?: string;
  dead_letter_state?: string;
  latency_ms?: number | null;
  redis_url_masked?: string;
  checked_at?: string;
  blockers?: string[];
  server?: Record<string, unknown>;
  streams?: Record<string, RedisStreamHealth>;
  consumer_groups?: Record<string, ConsumerGroupEntry[]>;
  consumer_groups_summary?: ConsumerGroupSummary[];
  dead_letter_growth?: Record<string, DlqGrowthEntry>;
  sse_clients?: Record<string, number>;
}

export interface DbTableHealth {
  exists?: boolean;
  estimated_rows?: number | null;
  latest_at?: string | null;
  age_sec?: number | null;
  state?: string;
  blockers?: string[];
}

export interface DbWaitingSample {
  pid?: number;
  user?: string;
  app?: string;
  state?: string;
  wait_type?: string;
  wait_event?: string;
  query_age?: string | null;
  query?: string;
}

export interface DatabaseRuntimeHealth {
  ok?: boolean;
  state?: string;
  db_state?: string;
  pool_state?: string;
  schema_state?: string;
  freshness_state?: string;
  lock_state?: string;
  latency_ms?: number | null;
  write_db?: string;
  read_db?: string;
  same_db?: boolean;
  blockers?: string[];
  server?: Record<string, unknown>;
  tables?: Record<string, DbTableHealth>;
  waiting_samples?: DbWaitingSample[];
}

export interface OrchestratorStatus {
  enabled: boolean;
  actions_enabled: boolean;
  dry_run: boolean;
  dry_run_forced: boolean;
  dry_run_forced_reason: string;
  now_override: string | null;
  trade_date: string;
  phase: string;
  phase_label: string;
  now_cn: string;
  tick_seq: number;
  is_trade_day: boolean;
  services: Record<string, OrchestratorServiceState>;
  planned_actions: Array<{ service: string; action: string; reason: string; owner: string }>;
  executed_actions: Array<Record<string, unknown>>;
  global_blockers: string[];
  runtime_dependencies?: Record<string, unknown>;
  tick_duration_ms: number;
}

export async function fetchOrchestratorStatus(nowOverride?: string): Promise<OrchestratorStatus> {
  const params = nowOverride ? `?now=${encodeURIComponent(nowOverride)}` : "";
  return fetchJsonWithTimeout<OrchestratorStatus>(
    `/api/v2/realtime/orchestrator/status${params}`,
    { cache: "no-store" },
    3000,  // 短超时：非关键诊断，不要阻塞
  );
}

export async function triggerOrchestratorTick(
  dryRun: boolean = true,
  nowOverride?: string,
): Promise<OrchestratorStatus> {
  return fetchJsonWithTimeout<OrchestratorStatus>(
    "/api/v2/realtime/orchestrator/tick",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dry_run: dryRun,
        ...(nowOverride ? { now_override: nowOverride } : {}),
      }),
    },
    5000,
  );
}

export async function enableOrchestrator(actionsEnabled: boolean = false): Promise<{ ok: boolean; enabled: boolean; actions_enabled: boolean }> {
  return fetchJsonWithTimeout(
    "/api/v2/realtime/orchestrator/enable",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ actions_enabled: actionsEnabled }),
    },
    5000,
  );
}

export async function disableOrchestrator(): Promise<{ ok: boolean; enabled: boolean; actions_enabled: boolean }> {
  return fetchJsonWithTimeout(
    "/api/v2/realtime/orchestrator/disable",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    5000,
  );
}

export async function resetOrchestratorActions(): Promise<{ ok: boolean }> {
  return fetchJsonWithTimeout(
    "/api/v2/realtime/orchestrator/reset-action-history",
    { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
    5000,
  );
}

// ── PR-12.5: Mainline Confirmation API ──

export interface MainlineReviewItem {
  review_id: string;
  trade_date: string;
  subject_key: string;
  theme_name?: string | null;
  mainline_id?: string | null;
  mainline_name?: string | null;
  machine_state: string;
  final_mainline_state?: string | null;
  mainline_type?: string | null;
  confirmation_path?: string | null;
  trigger_mode?: string | null;
  review_reason?: string | null;
  review_priority?: number | null;
  review_status: string;
  suggested_human_decision?: string | null;
  scores_json?: Record<string, unknown>;
  evidence_json?: Record<string, unknown>;
  risk_flags_json?: Record<string, unknown>;
  diagnostics_json?: Record<string, unknown>;
  human_decision?: string | null;
  human_reviewer?: string | null;
  human_notes?: string | null;
  reviewed_at?: string | null;
  created_at?: string | null;
}

export interface ConfirmedMainlineItem {
  mainline_id: string;
  mainline_name: string;
  canonical_subject_key: string;
  identity_status: string;
  valid_from: string;
  valid_to?: string | null;
  mainline_type?: string | null;
  confirmation_path?: string | null;
  related_subject_keys_json?: string[];
  core_subject_keys_json?: string[];
  branch_subject_keys_json?: string[];
  source_review_id?: string | null;
  human_reviewer?: string | null;
  human_notes?: string | null;
  created_at?: string | null;
}

export interface MainlineReviewQueueResponse {
  items: MainlineReviewItem[];
  total?: number;
  pending_count?: number;
  reviewed_count?: number;
}

export interface MainlineRegistryResponse {
  items: ConfirmedMainlineItem[];
  total?: number;
}

export interface MainlineDecisionPayload {
  human_decision: string;
  canonical_subject_key?: string | null;
  mainline_name?: string | null;
  mainline_type?: string | null;
  related_subject_keys?: string[] | null;
  merge_target_mainline_id?: string | null;
  human_reviewer?: string | null;
  human_notes?: string | null;
}

export async function fetchMainlineReviewQueue(params: {
  trade_date?: string; status?: string; limit?: number;
} = {}): Promise<MainlineReviewQueueResponse> {
  const q = new URLSearchParams();
  if (params.trade_date) q.set("trade_date", params.trade_date);
  if (params.status) q.set("status", params.status);
  if (params.limit) q.set("limit", String(params.limit));
  return fetchJsonWithTimeout<MainlineReviewQueueResponse>(
    `/api/v2/mainline-review/queue?${q.toString()}`,
    { cache: "no-store" }, 10000,
  );
}

export async function fetchConfirmedMainlines(params: {
  trade_date?: string; limit?: number;
} = {}): Promise<MainlineRegistryResponse> {
  const q = new URLSearchParams();
  if (params.trade_date) q.set("trade_date", params.trade_date);
  if (params.limit) q.set("limit", String(params.limit));
  return fetchJsonWithTimeout<MainlineRegistryResponse>(
    `/api/v2/mainline-review/registry?${q.toString()}`,
    { cache: "no-store" }, 10000,
  );
}

export async function submitMainlineReviewDecision(
  reviewId: string, payload: MainlineDecisionPayload,
): Promise<{ ok: boolean; action?: string; mainline_id?: string; error?: string }> {
  return fetchJsonWithTimeout(
    `/api/v2/mainline-review/${reviewId}/decision`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) },
    15000,
  );
}

export async function importMainlineReviewCandidates(tradeDate: string): Promise<{ ok: boolean; count?: number; error?: string }> {
  return fetchJsonWithTimeout(
    `/api/v2/mainline-review/import-candidates`,
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ trade_date: tradeDate }) },
    30000,
  );
}
