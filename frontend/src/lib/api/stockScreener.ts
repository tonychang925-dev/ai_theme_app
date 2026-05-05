export interface ScreeningStrategy {
  strategy_id: string;
  strategy_name: string;
  strategy_type: "mainline" | "cycle" | "leader" | "technical" | "composite" | "weak_to_strong";
  description: string;
  weight_config: {
    mainline: number;
    cycle: number;
    leader: number;
    technical: number;
  };
  filter_config: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface CreateStrategyRequest {
  strategy_name: string;
  strategy_type: string;
  description?: string;
  weight_config: {
    mainline: number;
    cycle: number;
    leader: number;
    technical: number;
  };
  filter_config: Record<string, unknown>;
}

export interface ExecuteScreeningRequest {
  strategy_id: string;
  trade_date?: string;
  candidate_trade_date?: string;
  confirm_trade_date?: string;
  limit?: number;
  min_score?: number;
  auto_tune_min_score?: boolean;
  target_min_count?: number;
  target_max_count?: number;
  enable_llm_review?: boolean;
  llm_top_k?: number;
  run_stage1?: boolean;
  run_stage2?: boolean;
}

export interface ScreeningResultItem {
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
  dimension_scores: {
    mainline: number;
    cycle: number;
    leader: number;
    technical: number;
  };
  rank_position: number;
  screening_reason: string;
  theme_info?: {
    subject_key: string;
    theme_name: string;
    mainline_strength: number;
    cycle_stage: string;
  };
}

export interface ExecuteScreeningResponse {
  job_id: string;
  status: "pending" | "running" | "completed" | "failed";
  results?: ScreeningResultItem[];
  total_count: number;
  execution_time_ms: number;
  llm_review_status?: string;
  llm_summary?: { pass: number; watch: number; reject: number; failed: number };
  diagnostics?: {
    requested_trade_date?: string;
    resolved_trade_date?: string;
    candidate_trade_date?: string;
    confirm_trade_date?: string;
    snapshot_trade_date?: string;
    snapshot_channel?: string;
    cache_writes?: number;
    persisted_count?: number;
    signal_count?: number;
    snapshot_hit_count?: number;
    confirm_input_candidate_count?: number;
    confirm_filtered_out_count?: number;
    stage2?: {
      level_count?: { A?: number; B?: number; C?: number; X?: number };
    };
    requested_snapshot_stock_count?: number;
    resolved_snapshot_stock_count?: number;
    no_data_reason?: string | null;
    score_tuning?: {
      requested_min_score: number;
      tuned_min_score: number;
      auto_tune_applied: boolean;
      total_scored: number;
      pre_filter_count: number;
      final_count: number;
      target_min_count: number;
      target_max_count: number;
    };
    coverage_ratio: { theme: number; mainline: number; cycle: number; leader: number; technical: number };
    zero_score_count: number;
    missing_dimension_count: { mainline: number; cycle: number; leader: number; technical: number };
  };
}

export interface ScreeningResultDetail extends ScreeningResultItem {
  dimension_details: {
    mainline: {
      strength_score: number;
      heat_rank: number;
      capital_attention: number;
      reasoning: string;
    };
    cycle: {
      stage_score: number;
      duration_score: number;
      stability_score: number;
      reasoning: string;
    };
    leader: {
      position_score: number;
      leading_effect: number;
      capital_recognition: number;
      reasoning: string;
    };
    technical: {
      abnormal_score: number;
      pattern_score: number;
      volume_price_score: number;
      reasoning: string;
    };
  };
  created_at: string;
  weak_to_strong?: {
    detail_view?: "candidate" | "confirm";
    candidate_type?: string;
    candidate_type_label?: string;
    signal_level?: string;
    decision?: string;
    decision_label?: string;
    candidate_score?: number;
    confirmation_score?: number;
    support_type?: string;
    support_strength?: number;
    candidate_trade_date?: string;
    confirm_trade_date?: string;
  };
}

export interface HistoryQueryParams {
  strategy_id?: string;
  trade_date_from?: string;
  trade_date_to?: string;
  stock_id?: string;
  min_score?: number;
  limit?: number;
  offset?: number;
}

export interface HistoryResponse {
  results: ScreeningResultItem[];
  total_count: number;
  has_more: boolean;
}

export interface AddFavoriteRequest {
  result_id: string;
  notes?: string;
  tags?: string[];
}

export interface FavoriteItem {
  favorite_id: string;
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
  notes?: string;
  tags?: string[];
  created_at: string;
}

type ApiResult<T> = { data: T };

interface RequestOptions {
  timeoutMs?: number;
}

async function request<T>(url: string, init?: RequestInit, options?: RequestOptions): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeoutMs = Math.max(1000, options?.timeoutMs ?? 30000);
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers || {}),
      },
      signal: controller.signal,
      credentials: 'include', // 包含cookies
    });

    clearTimeout(timeoutId);

    if (!response.ok) {
      // 尝试获取更详细的错误信息
      let errorDetail = `HTTP ${response.status}`;
      try {
        const errorData = await response.json();
        if (errorData && errorData.detail) {
          errorDetail = `${errorDetail}: ${errorData.detail}`;
        }
      } catch {
        // 忽略JSON解析错误
      }
      throw new Error(`API请求失败: ${errorDetail}`);
    }

    const data = await response.json();
    return { data: data as T };
  } catch (error) {
    clearTimeout(timeoutId);
    if (error instanceof Error) {
      if (error.name === 'AbortError') {
        throw new Error(`请求超时（${Math.round(timeoutMs / 1000)}秒），后端处理时间过长，请稍后重试`);
      } else if (error.message.includes('Failed to fetch')) {
        throw new Error('无法连接到服务器，请检查网络连接或服务器状态');
      }
    }
    throw error;
  }
}

function withQuery(path: string, params?: Record<string, unknown>): string {
  if (!params) return path;
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    q.set(k, String(v));
  });
  return q.toString() ? `${path}?${q.toString()}` : path;
}

export const stockScreenerApi = {
  getStrategies: () => request<ScreeningStrategy[]>("/api/v2/stock-screener/strategies"),

  createStrategy: (data: CreateStrategyRequest) =>
    request<ScreeningStrategy>("/api/v2/stock-screener/strategies", { method: "POST", body: JSON.stringify(data) }),

  updateStrategy: (strategyId: string, data: Partial<CreateStrategyRequest>) =>
    request<ScreeningStrategy>(`/api/v2/stock-screener/strategies/${strategyId}`, { method: "PUT", body: JSON.stringify(data) }),

  deleteStrategy: (strategyId: string) =>
    request<{ ok: boolean }>(`/api/v2/stock-screener/strategies/${strategyId}`, { method: "DELETE" }),

  executeScreening: (data: ExecuteScreeningRequest) =>
    request<ExecuteScreeningResponse>("/api/v2/stock-screener/execute", { method: "POST", body: JSON.stringify(data) }, { timeoutMs: 120000 }),

  getExecutionStatus: (jobId: string) =>
    request<ExecuteScreeningResponse>(`/api/v2/stock-screener/executions/${jobId}`),

  getResultDetail: (resultId: string, params?: { view?: "candidate" | "confirm" }) =>
    request<ScreeningResultDetail>(withQuery(`/api/v2/stock-screener/results/${resultId}`, params as Record<string, unknown>)),

  getHistory: (params: HistoryQueryParams) =>
    request<HistoryResponse>(withQuery("/api/v2/stock-screener/history", params as Record<string, unknown>)),

  getFavorites: () => request<FavoriteItem[]>("/api/v2/stock-screener/favorites"),

  addFavorite: (data: AddFavoriteRequest) =>
    request<FavoriteItem>("/api/v2/stock-screener/favorites", {
      method: "POST",
      body: JSON.stringify(data),
    }),

  updateFavorite: (favoriteId: string, data: { notes?: string; tags?: string[] }) =>
    request<FavoriteItem>(`/api/v2/stock-screener/favorites/${favoriteId}`, { method: "PUT", body: JSON.stringify(data) }),

  removeFavorite: (favoriteId: string) =>
    request<{ ok: boolean }>(`/api/v2/stock-screener/favorites/${favoriteId}`, { method: "DELETE" }),

  exportResults: (resultIds: string[], format: "csv" | "excel" | "json") =>
    request<{ download_url: string }>("/api/v2/stock-screener/export", {
      method: "POST",
      body: JSON.stringify({ result_ids: resultIds, format }),
    }),

  getStatistics: (strategyId?: string, dateRange?: { from: string; to: string }) =>
    request<{
      total_executions: number;
      avg_composite_score: number;
      top_themes: Array<{ subject_key: string; theme_name: string; count: number }>;
      score_distribution: Array<{ score_range: string; count: number }>;
    }>(withQuery("/api/v2/stock-screener/statistics", { strategy_id: strategyId, ...(dateRange || {}) })),
};
