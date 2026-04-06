export type IntelItemType = "all" | "event" | "theme_move" | "new_theme" | "stock_move";
export type IntelSession = "all" | "pre" | "intra" | "post";

export interface IntelFeedItem {
  item_id: string;
  item_type: "event" | "theme_move" | "new_theme" | "stock_move";
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
    fallback_from?: string | null;
  };
}

export interface IntelFeedEvent {
  event_id: string;
  occurred_at: string;
  event_type: "event" | "theme_move" | "new_theme" | "stock_move";
  item: IntelFeedItem;
  cursor?: string;
}

export interface ThemeWorkspaceView {
  subject_key: string;
  detail: Record<string, unknown>;
  history?: Record<string, unknown>[] | null;
  children?: Record<string, unknown>[] | null;
  stocks?: Record<string, unknown>[] | null;
  diagnostics?: {
    partial: boolean;
    missing_sections: string[];
  };
}

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

  const response = await fetch(`/api/intel/feed?${query.toString()}`);
  if (!response.ok) {
    throw new Error(`intel feed request failed: ${response.status}`);
  }
  return response.json();
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

export async function fetchThemeWorkspace(subjectKey: string): Promise<ThemeWorkspaceView> {
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
