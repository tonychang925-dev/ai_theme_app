import { create } from 'zustand';
import { stockScreenerApi } from '../../../lib/api/stockScreener';

// 类型定义
export interface ScreeningStrategy {
  strategy_id: string;
  strategy_name: string;
  strategy_type: 'mainline' | 'cycle' | 'leader' | 'technical' | 'composite' | 'weak_to_strong';
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
    mainline_strength?: number;
    cycle_stage?: string;
    amount?: number; // API返回的字段
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
  llm_review?: {
    decision: 'pass' | 'watch' | 'reject' | 'failed';
    confidence: number;
    reasoning: string;
    key_points: string[];
    risks: string[];
  };
}

export interface FavoriteItem {
  favorite_id: string;
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
  notes?: string;
  tags?: string[];
}

// Store 类型定义
export interface StockScreenerStoreType {
  // 状态
  strategies: ScreeningStrategy[];
  selectedStrategyId: string | null;
  tradeDate: string;
  enableLlmReview: boolean; // 新增：是否启用LLM复核
  autoTuneMinScore: boolean;
  targetMinCount: number;
  targetMaxCount: number;
  isExecuting: boolean;
  executionJobId: string | null;
  executionStatus: {
    llmReviewStatus?: string;
    llmSummary?: { pass: number; watch: number; reject: number; failed: number };
    totalCount?: number;
    inconsistencyWarning?: string;
    diagnostics?: {
      requested_trade_date?: string;
      resolved_trade_date?: string;
      fallback_applied?: boolean;
      fallback_reason?: string | null;
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
  };
  currentResults: ScreeningResultItem[];
  selectedResultId: string | null;
  resultDetail: ScreeningResultDetail | null;
  favorites: FavoriteItem[];

  // Actions
  loadStrategies: () => Promise<void>;
  selectStrategy: (strategyId: string) => void;
  setTradeDate: (tradeDate: string) => void;
  setEnableLlmReview: (enable: boolean) => void; // 新增：设置LLM复核启用状态
  setAutoTuneMinScore: (enable: boolean) => void;
  setTargetMinCount: (value: number) => void;
  setTargetMaxCount: (value: number) => void;
  executeScreening: (opts?: { runStage1?: boolean; runStage2?: boolean }) => Promise<void>;
  loadResultDetail: (resultId: string) => Promise<void>;
  toggleFavorite: (stockId: string, stockName: string) => Promise<void>;
  loadFavorites: () => Promise<void>;
}

export const useStockScreenerStore = create<StockScreenerStoreType>()((set, get) => ({
  // 初始状态
  strategies: [],
  selectedStrategyId: null,
  tradeDate: '2026-04-09',
  enableLlmReview: true, // 默认启用LLM复核
  autoTuneMinScore: true,
  targetMinCount: 30,
  targetMaxCount: 120,
  isExecuting: false,
  executionJobId: null,
  executionStatus: {},
  currentResults: [],
  selectedResultId: null,
  resultDetail: null,
  favorites: [],

  // 加载策略列表（带重试机制）
  loadStrategies: async () => {
    const maxRetries = 3;
    let lastError: Error | null = null;

    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const response = await stockScreenerApi.getStrategies();
        const strategies = response.data;
        set({ strategies });

        // 如果没有选中策略，选择第一个活跃策略
        if (!get().selectedStrategyId && strategies.length > 0) {
          const activeStrategy = strategies.find(s => s.is_active);
          if (activeStrategy) {
            set({ selectedStrategyId: activeStrategy.strategy_id });
          }
        }
        return; // 成功则返回
      } catch (error) {
        lastError = error as Error;
        console.error(`加载策略失败 (尝试 ${attempt}/${maxRetries}):`, error);

        if (attempt < maxRetries) {
          // 指数退避重试
          await new Promise(resolve => setTimeout(resolve, 1000 * attempt));
          continue;
        }
      }
    }

    // 所有重试都失败
    throw lastError || new Error('加载策略失败，请检查网络连接');
  },

  // 选择策略
  selectStrategy: (strategyId: string) => {
    set({ selectedStrategyId: strategyId });
  },

  // 设置交易日
  setTradeDate: (tradeDate: string) => {
    set({ tradeDate });
  },

  // 设置LLM复核启用状态
  setEnableLlmReview: (enable: boolean) => {
    set({ enableLlmReview: enable });
  },

  setAutoTuneMinScore: (enable: boolean) => {
    set({ autoTuneMinScore: enable });
  },

  setTargetMinCount: (value: number) => {
    const safeValue = Number.isFinite(value) ? Math.max(1, Math.floor(value)) : 30;
    set({ targetMinCount: safeValue });
  },

  setTargetMaxCount: (value: number) => {
    const safeValue = Number.isFinite(value) ? Math.max(1, Math.floor(value)) : 120;
    set({ targetMaxCount: safeValue });
  },

  // 执行选股
  executeScreening: async (opts) => {
    const state = get();
    if (!state.selectedStrategyId) {
      throw new Error('请先选择策略');
    }

    console.log('🔍 executeScreening开始: selectedStrategyId=', state.selectedStrategyId);
    set({ isExecuting: true, executionJobId: null });

    try {
      const selected = state.strategies.find(s => s.strategy_id === state.selectedStrategyId);
      const isWeakToStrong = Boolean(
        selected && (/weak_to_strong/i.test(selected.strategy_id) || /弱转强/.test(selected.strategy_name)),
      );
      const response = await stockScreenerApi.executeScreening({
        strategy_id: state.selectedStrategyId,
        trade_date: state.tradeDate,
        limit: isWeakToStrong ? 20 : 50,
        auto_tune_min_score: state.autoTuneMinScore,
        target_min_count: state.targetMinCount,
        target_max_count: state.targetMaxCount,
        enable_llm_review: state.enableLlmReview, // 使用用户选择的LLM复核设置
        llm_top_k: 20, // 默认TopK为20
        run_stage1: opts?.runStage1,
        run_stage2: opts?.runStage2,
      });

      const result = response.data;
      console.log('🔍 API响应 (时间戳:', new Date().toLocaleTimeString(), '):');
      console.log('  status:', result.status);
      console.log('  job_id:', result.job_id);
      console.log('  results长度:', result.results ? result.results.length : 0);
      console.log('  完整响应:', JSON.stringify(result, null, 2).substring(0, 1000) + '...');

      // execute 接口已完成时，直接以本次响应为准。
      // 轮询接口只返回执行状态，不携带结果明细；completed 后继续轮询会导致结果丢失。
      if (result.status === 'completed') {
        console.log('🔍 API已完成，直接更新store状态');
        if (result.results && result.results.length > 0) {
          console.log('  第一条结果结构:', JSON.stringify(result.results[0], null, 2));
        }
        set({
          isExecuting: false,
          executionJobId: result.job_id,
          currentResults: result.results || [],
          executionStatus: {
            llmReviewStatus: result.llm_review_status,
            llmSummary: result.llm_summary,
            totalCount: result.total_count,
            inconsistencyWarning:
              ((result.total_count || 0) > 0 && (!result.results || result.results.length === 0))
                ? `接口返回 total_count=${result.total_count} 但 results 为空，可能是前端缓存或网络中间层问题，请刷新页面后重试。`
                : undefined,
            diagnostics: result.diagnostics
          }
        });
        console.log('🔍 store状态已更新: currentResults.length=', (result.results || []).length);
      } else {
        // 需要轮询获取结果
        const jobId = result.job_id;
        set({ executionJobId: jobId });

        // 轮询获取结果（带超时保护）
        const maxPollingTime = 300000; // 5分钟最大轮询时间
        const pollingStartTime = Date.now();
        let pollingTimeoutId: NodeJS.Timeout | null = null;

        const pollResult = async () => {
          try {
            // 检查是否超过最大轮询时间
            if (Date.now() - pollingStartTime > maxPollingTime) {
              set({ isExecuting: false });
              throw new Error('选股执行超时，请稍后重试');
            }

            const resultResponse = await stockScreenerApi.getExecutionStatus(jobId);
            const polledResult = resultResponse.data;

            if (polledResult.status === 'completed') {
              set({
                isExecuting: false,
                currentResults: polledResult.results || [],
                executionStatus: {
                  llmReviewStatus: polledResult.llm_review_status,
                  llmSummary: polledResult.llm_summary,
                  totalCount: polledResult.total_count,
                  inconsistencyWarning:
                    ((polledResult.total_count || 0) > 0 && (!polledResult.results || polledResult.results.length === 0))
                      ? `轮询返回 total_count=${polledResult.total_count} 但 results 为空；该接口默认不返回明细，请重新执行筛选。`
                      : undefined,
                  diagnostics: polledResult.diagnostics
                }
              });
              if (pollingTimeoutId) clearTimeout(pollingTimeoutId);
            } else if (polledResult.status === 'failed') {
              set({ isExecuting: false });
              if (pollingTimeoutId) clearTimeout(pollingTimeoutId);
              throw new Error('选股执行失败');
            } else {
              // 继续轮询，使用指数退避策略
              const elapsedTime = Date.now() - pollingStartTime;
              const delay = elapsedTime < 30000 ? 1000 : // 前30秒每秒轮询
                           elapsedTime < 120000 ? 2000 : // 30-120秒每2秒轮询
                           5000; // 超过2分钟每5秒轮询

              pollingTimeoutId = setTimeout(pollResult, delay);
            }
          } catch (error) {
            set({ isExecuting: false });
            if (pollingTimeoutId) clearTimeout(pollingTimeoutId);
            throw error;
          }
        };

        // 开始轮询
        pollingTimeoutId = setTimeout(pollResult, 1000);
      }
    } catch (error) {
      set({ isExecuting: false });
      throw error;
    }
  },

  // 加载结果详情
  loadResultDetail: async (resultId: string) => {
    try {
      const response = await stockScreenerApi.getResultDetail(resultId);
      set({ resultDetail: response.data, selectedResultId: resultId });
    } catch (error) {
      console.error('加载结果详情失败:', error);
      throw error;
    }
  },

  // 切换收藏
  toggleFavorite: async (stockId: string, stockName: string) => {
    try {
      const currentFavorites = get().favorites;
      const isFavorite = currentFavorites.some(f => f.stock_id === stockId);

      if (isFavorite) {
        await stockScreenerApi.removeFavorite(stockId);
        set({
          favorites: currentFavorites.filter(f => f.stock_id !== stockId)
        });
      } else {
        await stockScreenerApi.addFavorite({ result_id: 'temp', notes: `收藏股票: ${stockName}` });
        set({
          favorites: [...currentFavorites, {
            favorite_id: `temp_${Date.now()}`,
            result_id: 'temp',
            stock_id: stockId,
            stock_name: stockName,
            composite_score: 0
          }]
        });
      }
    } catch (error) {
      console.error('切换收藏失败:', error);
      throw error;
    }
  },

  // 加载收藏列表
  loadFavorites: async () => {
    try {
      const response = await stockScreenerApi.getFavorites();
      set({ favorites: response.data });
    } catch (error) {
      console.error('加载收藏列表失败:', error);
      throw error;
    }
  },
}));
