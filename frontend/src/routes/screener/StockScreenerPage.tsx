import React, { useEffect, useState } from 'react';
import { useStockScreenerStore } from './store/stockScreenerStore';
import { ScreeningControlPanel } from './components/ScreeningControlPanel';
import { ResultsFormView } from './components/ResultsFormView';
import { ResultsChart } from './components/ResultsChart';
import { FavoritePanel } from './components/FavoritePanel';
import { ResultDetailModal } from './components/ResultDetailModal';
import { ExportPanel } from './components/ExportPanel';
import { WeakToStrongTwoStageView } from './components/WeakToStrongTwoStageView';
import { NetworkStatusAlert } from '../../components/common/NetworkStatusAlert';
import { navigateTo } from '../../lib/navigation';
import screenerIcon from '../../assets/intel-icons/AI选股.png';

function getShanghaiNowParts(): { date: string; hour: number; minute: number } {
  const formatter = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  const parts = formatter.formatToParts(new Date());
  const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return {
    date: `${lookup.year}-${lookup.month}-${lookup.day}`,
    hour: Number(lookup.hour || 0),
    minute: Number(lookup.minute || 0),
  };
}

function isBeforePreMarketConfirmWindow(tradeDate: string): boolean {
  const now = getShanghaiNowParts();
  if (tradeDate !== now.date) {
    return false;
  }
  return now.hour < 9 || (now.hour === 9 && now.minute < 25);
}

// 类型定义
interface ScreeningResultItem {
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
  llm_review?: {
    decision?: string;
    confidence?: number;
    reasoning?: string;
  };
}

interface ScreeningStrategy {
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

export function StockScreenerPage() {
  const store = useStockScreenerStore();
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showExportPanel, setShowExportPanel] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llmDecisionFilter, setLlmDecisionFilter] = useState<'all' | 'pass' | 'watch' | 'reject' | 'unreviewed'>('all');
  const [runMode, setRunMode] = useState<'post' | 'pre'>('post');

  const selectedStrategy = store.strategies.find((s: ScreeningStrategy) => s.strategy_id === store.selectedStrategyId) || null;
  const isWeakToStrongTwoStage = Boolean(
    selectedStrategy && (
      selectedStrategy.strategy_type === 'weak_to_strong' ||
      /weak_to_strong/i.test(selectedStrategy.strategy_id) ||
      /弱转强/.test(selectedStrategy.strategy_name)
    ),
  );

  const filteredResults = store.currentResults.filter((item: ScreeningResultItem) => {
    const decision = item.llm_review?.decision;
    if (llmDecisionFilter === 'all') return true;
    if (llmDecisionFilter === 'unreviewed') return !decision;
    return decision === llmDecisionFilter;
  });

  const executionStageLabel = isWeakToStrongTwoStage
    ? (runMode === 'pre'
      ? '阶段2：正在采集竞价快照并确认信号...'
      : '阶段1：正在生成盘后候选池...')
    : '正在执行选股分析...';
  const twoStageCandidateCount = isWeakToStrongTwoStage
    ? Number(
      (store.executionStatus.diagnostics as any)?.candidate_pool_count ??
      (store.executionStatus.diagnostics as any)?.display_result_count ??
      (store.executionStatus.diagnostics as any)?.stage1?.candidate_count ??
      0
    )
    : 0;
  const confirmTradeDate =
    String(
      (store.executionStatus.diagnostics as any)?.confirm_trade_date ||
      ''
    ).trim() || undefined;
  const snapshotChannel =
    String(
      (store.executionStatus.diagnostics as any)?.snapshot_channel ||
      ''
    ).trim() || undefined;
  const stage2CacheWrites = Number((store.executionStatus.diagnostics as any)?.cache_writes ?? 0);
  const stage2PersistedCount = Number((store.executionStatus.diagnostics as any)?.persisted_count ?? 0);
  const stage2SignalCount = Number((store.executionStatus.diagnostics as any)?.signal_count ?? store.currentResults.length ?? 0);
  const stage2SnapshotHitCount = Number((store.executionStatus.diagnostics as any)?.snapshot_hit_count ?? 0);
  const stage2InputCandidateCount = Number((store.executionStatus.diagnostics as any)?.confirm_input_candidate_count ?? 0);
  const stage2FilteredOutCount = Number((store.executionStatus.diagnostics as any)?.confirm_filtered_out_count ?? 0);
  const stage2XCount = Number((store.executionStatus.diagnostics as any)?.stage2?.level_count?.X ?? 0);
  // 调试：强制显示候选池数量
  console.log('🔍 候选池数量调试:', {
    twoStageCandidateCount,
    diagnostics: store.executionStatus.diagnostics,
    candidate_pool_count: (store.executionStatus.diagnostics as any)?.candidate_pool_count,
    display_result_count: (store.executionStatus.diagnostics as any)?.display_result_count,
    stage1_candidate_count: (store.executionStatus.diagnostics as any)?.stage1?.candidate_count,
    storeCurrentResultsLength: store.currentResults.length
  });

  // 调试日志
  console.log('🔍 调试twoStageCandidateCount:', {
    isWeakToStrongTwoStage,
    twoStageCandidateCount,
    executionStatus: store.executionStatus,
    diagnostics: store.executionStatus.diagnostics,
    candidate_pool_count: (store.executionStatus.diagnostics as any)?.candidate_pool_count,
    stage1_candidate_count: (store.executionStatus.diagnostics as any)?.stage1?.candidate_count,
  });

  // 调试：监听store状态变化
  useEffect(() => {
    console.log('🔍 StockScreenerPage - store状态变化 (时间戳:', new Date().toLocaleTimeString(), '):');
    console.log('  isExecuting:', store.isExecuting);
    console.log('  currentResults长度:', store.currentResults.length);
    console.log('  executionJobId:', store.executionJobId);
    console.log('  store对象:', store);
    if (store.currentResults.length > 0) {
      console.log('  第一条结果:', store.currentResults[0]);
    } else {
      console.log('  ⚠️ currentResults为空数组');
    }
  }, [store.isExecuting, store.currentResults, store.executionJobId]);

  // 处理页面可见性变化 - 简化版本
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible' && store.strategies.length === 0) {
        // 页面重新可见时，如果还没有数据，尝试重新加载
        store.loadStrategies().catch(err => {
          console.warn('重新加载策略失败:', err);
        });
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [store]);

  // 初始化加载 - 简化版本，依赖NetworkStatusAlert处理网络错误
  useEffect(() => {
    let mounted = true;

    const initialize = async () => {
      try {
        // 添加短暂延迟，避免页面加载时立即请求
        await new Promise(resolve => setTimeout(resolve, 1000));

        if (!mounted) return;

        await store.loadStrategies();
        await store.loadFavorites();
      } catch (err) {
        // 只记录错误，不显示给用户，因为NetworkStatusAlert会处理网络错误
        console.warn('选股器初始化失败:', err);
      }
    };

    initialize();

    return () => {
      mounted = false;
    };
  }, [store]);

  // 执行选股
  const handleExecuteScreening = async () => {
    try {
      setRunMode('post');
      await store.executeScreening({ runStage1: true, runStage2: false });
    } catch (err) {
      // 显示执行错误，但不处理网络错误（由NetworkStatusAlert处理）
      const errorMessage = err instanceof Error ? err.message : '选股执行失败';
      const isTimeout = errorMessage.includes('请求超时');
      if (isTimeout || (!errorMessage.includes('网络连接') && !errorMessage.includes('无法连接到服务器'))) {
        setError(errorMessage);
      }
    }
  };

  const handleExecuteStage2Only = async () => {
    try {
      if (isBeforePreMarketConfirmWindow(store.tradeDate)) {
        setError('9:25分之后才能进行盘前确认！');
        return;
      }
      setRunMode('pre');
      await store.executeScreening({ runStage1: false, runStage2: true });
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '竞价确认执行失败';
      const isTimeout = errorMessage.includes('请求超时');
      if (isTimeout || (!errorMessage.includes('网络连接') && !errorMessage.includes('无法连接到服务器'))) {
        setError(errorMessage);
      }
    }
  };

  // 查看结果详情
  const handleViewDetail = async (resultId: string, view?: 'candidate' | 'confirm') => {
    try {
      await store.loadResultDetail(resultId, view);
      setShowDetailModal(true);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '加载详情失败';
      if (!errorMessage.includes('网络连接') && !errorMessage.includes('无法连接到服务器')) {
        setError(errorMessage);
      }
    }
  };

  // 添加到收藏
  const handleAddFavorite = async (resultId: string) => {
    try {
      const result = store.currentResults.find(r => r.result_id === resultId);
      if (result) {
        await store.toggleFavorite(result.stock_id, result.stock_name);
      }
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : '收藏失败';
      if (!errorMessage.includes('网络连接') && !errorMessage.includes('无法连接到服务器')) {
        setError(errorMessage);
      }
    }
  };

  // 导出结果
  const handleExportResults = () => {
    setShowExportPanel(true);
  };

  // 跳转到股票详情页
  const handleNavigateToStock = (stockId: string) => {
    window.location.href = `/stocks/${stockId}`;
  };

  // 跳转到题材详情页
  const handleNavigateToTheme = (subjectKey: string) => {
    window.location.href = `/themes/${subjectKey}`;
  };

  // 处理重试连接 - 简化版本，现在由NetworkStatusAlert处理
  const handleRetryConnection = async () => {
    try {
      await store.loadStrategies();
      await store.loadFavorites();
    } catch (err) {
      // 网络错误由NetworkStatusAlert处理
      console.warn('重试连接失败:', err);
    }
  };

  // 只显示非网络相关的错误
  const showError = error && !error.includes('网络连接') && !error.includes('无法连接到服务器');

  if (showError) {
    return (
      <div className="workspace-page">
        <div className="collection-modal-backdrop">
          <div className="collection-modal">
            <span className="metric-label section-title">操作错误</span>
            <h3>选股器操作失败</h3>
            <p>{error}</p>
            <div className="collection-action-row">
              <button type="button" className="tag tag-button tag-active" onClick={() => setError(null)}>
                关闭
              </button>
              <button type="button" className="tag tag-button" onClick={() => navigateTo('/')}>
                返回首页
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace-page">
      {/* 网络状态提示 */}
      <NetworkStatusAlert onRetry={handleRetryConnection} suppress={store.isExecuting} />

      <section className="strong-watch-toolbar">
        <img src={screenerIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">AI选股</h1>
        <div className="collection-action-row" style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
          <button className="tag tag-button" type="button" onClick={handleExportResults} style={{ fontSize: 16, padding: "8px 16px" }}>
            导出结果
          </button>
          <button className="tag tag-button" type="button" onClick={() => {/* 打开策略编辑器 */}} style={{ fontSize: 16, padding: "8px 16px" }}>
            新建策略
          </button>
        </div>
        <button className="back-button" type="button" onClick={() => navigateTo('/')}>
          返回
        </button>
      </section>

      <main className="collection-grid">
        <section className="workspace-card collection-config-card">
          <span className="metric-label section-title">选股配置</span>

          <div className="collection-section">
            <strong>选股流程</strong>
            <p className="workspace-note">按照以下步骤执行选股：</p>
            <ScreeningControlPanel
              strategies={store.strategies}
              selectedStrategyId={store.selectedStrategyId}
              onStrategySelect={store.selectStrategy}
              selectedStrategy={selectedStrategy}
              tradeDate={store.tradeDate}
              enableLlmReview={store.enableLlmReview}
              autoTuneMinScore={store.autoTuneMinScore}
              targetMinCount={store.targetMinCount}
              targetMaxCount={store.targetMaxCount}
              onTradeDateChange={store.setTradeDate}
              onEnableLlmReviewChange={store.setEnableLlmReview}
              onAutoTuneMinScoreChange={store.setAutoTuneMinScore}
              onTargetMinCountChange={store.setTargetMinCount}
              onTargetMaxCountChange={store.setTargetMaxCount}
              onExecute={handleExecuteScreening}
              onExecuteStage2Only={handleExecuteStage2Only}
              isExecuting={store.isExecuting}
              isTwoStageStrategy={isWeakToStrongTwoStage}
              executionLabel={isWeakToStrongTwoStage ? (runMode === 'pre' ? '盘前确认执行中...' : '盘后选股执行中...') : '执行中...'}
              runMode={runMode}
            />
          </div>

          <div className="collection-section">
            <strong>我的收藏</strong>
            <FavoritePanel
              favorites={store.favorites}
              onRemoveFavorite={(favoriteId) => {
                const favorite = store.favorites.find(f => f.favorite_id === favoriteId);
                if (favorite) {
                  store.toggleFavorite(favorite.stock_id, favorite.stock_name);
                }
              }}
              onViewDetail={handleViewDetail}
              onNavigateToStock={handleNavigateToStock}
            />
          </div>
        </section>

        <section className="collection-main-column">
          {/* 执行状态指示器 */}
          {store.isExecuting && (
            <section className="workspace-card collection-summary-card">
              <span className="metric-label section-title">执行状态</span>
              <div className="collection-summary-grid">
                <article className="collection-metric-card">
                  <span>状态</span>
                  <strong className="screener-status-running">运行中</strong>
                </article>
                <article className="collection-metric-card">
                  <span>任务ID</span>
                  <strong>{store.executionJobId}</strong>
                </article>
              </div>
              <div className="collection-progress-panel">
                <div className="collection-progress-head">
                  <strong className="screener-run-inline">
                    <span className="screener-spinner" />
                    {executionStageLabel}
                  </strong>
                  <span>{isWeakToStrongTwoStage ? '请勿刷新页面，执行完成后将自动展示候选与确认结果' : '请稍候，系统正在计算多维评分'}</span>
                </div>
                <div className="collection-progress-bar is-indeterminate">
                  <span />
                </div>
                {isWeakToStrongTwoStage && (
                  <div className="screener-stage-hint">
                    {runMode === 'pre'
                      ? '当前为“仅更新竞价确认”：仅对前一日候选池做9:25后确认。'
                      : '当前为“盘后选股”：仅生成候选池，不做盘前确认。'}
                  </div>
                )}
              </div>
            </section>
          )}

          {/* LLM复核状态显示 */}
          {store.executionStatus.llmReviewStatus && (
            <section className="workspace-card">
              <span className="metric-label section-title">LLM复核状态</span>
              <div className="collection-summary-grid">
                <article className="collection-metric-card">
                  <span>状态</span>
                  <strong className="screener-status-chip">
                    {store.executionStatus.llmReviewStatus}
                  </strong>
                </article>
                {store.executionStatus.llmSummary && (
                  <>
                    <article className="collection-metric-card">
                      <span>通过</span>
                      <strong className="screener-count-pass">{store.executionStatus.llmSummary.pass}</strong>
                    </article>
                    <article className="collection-metric-card">
                      <span>观察</span>
                      <strong className="screener-count-watch">{store.executionStatus.llmSummary.watch}</strong>
                    </article>
                    <article className="collection-metric-card">
                      <span>拒绝</span>
                      <strong className="screener-count-reject">{store.executionStatus.llmSummary.reject}</strong>
                    </article>
                  </>
                )}
              </div>

              {store.executionStatus.llmReviewStatus === 'skipped_no_api_key' && (
                <div className="workspace-note screener-note-warn">
                  未配置DEEPSEEK_API_KEY，已跳过LLM复核
                </div>
              )}

              {store.executionStatus.llmReviewStatus === 'partial_failed' && (
                <div className="workspace-note screener-note-warn">
                  部分LLM复核失败，规则选股结果仍可用
                </div>
              )}
            </section>
          )}

          {store.executionStatus.inconsistencyWarning && (
            <section className="workspace-card">
              <span className="metric-label section-title">结果一致性告警</span>
              <div className="screener-alert-card">
                <div className="screener-alert-title">检测到结果异常</div>
                <div className="workspace-note">{store.executionStatus.inconsistencyWarning}</div>
              </div>
            </section>
          )}

            {/* 结果统计摘要 */}
            {!isWeakToStrongTwoStage && store.currentResults.length > 0 && (
              <div className="workspace-card screener-summary-card">
                <div className="screener-kpi-grid">
                  <div className="screener-kpi-card">
                    <div className="screener-kpi-value">{store.currentResults.length}</div>
                    <div className="metric-label">筛选结果</div>
                  </div>
                  <div className="screener-kpi-card">
                    <div className="screener-kpi-value">
                      {Math.max(...store.currentResults.map((r: ScreeningResultItem) => r.composite_score)).toFixed(2)}
                    </div>
                    <div className="metric-label">最高得分</div>
                  </div>
                  <div className="screener-kpi-card">
                    <div className="screener-kpi-value">
                      {(store.currentResults.reduce((sum: number, r: ScreeningResultItem) => sum + r.composite_score, 0) / store.currentResults.length).toFixed(2)}
                    </div>
                    <div className="metric-label">平均得分</div>
                  </div>
                  <div className="screener-kpi-card">
                    <div className="screener-kpi-value">
                      {new Set(store.currentResults.map((r: ScreeningResultItem) => r.theme_info?.subject_key)).size}
                    </div>
                    <div className="metric-label">涉及题材</div>
                  </div>
                </div>
              </div>
            )}

            {/* 图表展示 */}
            {!isWeakToStrongTwoStage && store.currentResults.length > 0 && (
              <div className="workspace-card screener-chart-card">
                <h2 className="screener-section-head">得分分布</h2>
                <div className="workspace-card">
                  <ResultsChart
                    results={filteredResults}
                    chartType="pie"
                    dimensions={['mainline', 'cycle', 'leader', 'technical']}
                    onDataPointClick={handleViewDetail}
                  />
                </div>
              </div>
            )}

            {/* 结果表格 / 两阶段视图 */}
            <div className="workspace-card screener-results-card">
              <div className="recap-table-head">
                <div className="screener-results-head">
                  <h2>{isWeakToStrongTwoStage ? '弱转强两阶段结果' : '选股结果'}</h2>
                  {!isWeakToStrongTwoStage && (
                    <div className="screener-results-tools">
                      <select
                        className="screener-input screener-inline-select"
                        value={llmDecisionFilter}
                        onChange={(e) => setLlmDecisionFilter(e.target.value as 'all' | 'pass' | 'watch' | 'reject' | 'unreviewed')}
                      >
                        <option value="all">全部</option>
                        <option value="pass">仅通过</option>
                        <option value="watch">仅观察</option>
                        <option value="reject">仅拒绝</option>
                        <option value="unreviewed">仅未复核</option>
                      </select>
                      <span className="recap-chip is-status">
                        {filteredResults.length} / {store.currentResults.length} 条记录
                      </span>
                    </div>
                  )}
                </div>
              </div>
              <div className="overflow-x-auto">
                {isWeakToStrongTwoStage ? (
                  <WeakToStrongTwoStageView
                    tradeDate={store.tradeDate}
                    confirmTradeDate={confirmTradeDate}
                    snapshotChannel={snapshotChannel}
                    cacheWrites={stage2CacheWrites}
                    persistedCount={stage2PersistedCount}
                    signalCount={stage2SignalCount}
                    snapshotHitCount={stage2SnapshotHitCount}
                    confirmInputCandidateCount={stage2InputCandidateCount}
                    confirmFilteredOutCount={stage2FilteredOutCount}
                    xLevelCount={stage2XCount}
                    isExecuting={store.isExecuting}
                    runMode={runMode}
                    candidateCount={twoStageCandidateCount}
                    results={store.currentResults}
                    onRowClick={handleViewDetail}
                    onAddFavorite={handleAddFavorite}
                    onNavigateToStock={handleNavigateToStock}
                    onNavigateToTheme={handleNavigateToTheme}
                  />
                ) : (
                  <ResultsFormView
                    results={filteredResults}
                    isLoading={store.isExecuting}
                    onRowClick={handleViewDetail}
                    onAddFavorite={handleAddFavorite}
                    onNavigateToStock={handleNavigateToStock}
                    onNavigateToTheme={handleNavigateToTheme}
                  />
                )}
              </div>
            </div>

            {/* 诊断信息显示（置于结果区最下方） */}
            {!isWeakToStrongTwoStage && store.executionStatus.diagnostics?.coverage_ratio && store.executionStatus.diagnostics?.missing_dimension_count && (
              <div className="workspace-card screener-diagnostics-card">
                <h3 className="screener-section-head">诊断信息</h3>

                <div className="screener-diagnostics-stack">
                  {store.executionStatus.diagnostics.score_tuning && (
                    <div className="screener-kpi-grid">
                      <div className="screener-kpi-card">
                        <div className="metric-label">请求阈值</div>
                        <div className="screener-kpi-value">
                          {store.executionStatus.diagnostics.score_tuning.requested_min_score.toFixed(2)}
                        </div>
                      </div>
                      <div className="screener-kpi-card">
                        <div className="metric-label">调后阈值</div>
                        <div className="screener-kpi-value">
                          {store.executionStatus.diagnostics.score_tuning.tuned_min_score.toFixed(2)}
                        </div>
                      </div>
                      <div className="screener-kpi-card">
                        <div className="metric-label">调分状态</div>
                        <div className="screener-kpi-value screener-kpi-text">
                          {store.executionStatus.diagnostics.score_tuning.auto_tune_applied ? '已触发' : '未触发'}
                        </div>
                      </div>
                      <div className="screener-kpi-card">
                        <div className="metric-label">预过滤数量</div>
                        <div className="screener-kpi-value">
                          {store.executionStatus.diagnostics.score_tuning.pre_filter_count}
                        </div>
                      </div>
                    </div>
                  )}

                  <div>
                    <div className="screener-row-head">
                      <span className="metric-label">数据覆盖率</span>
                      <span className="screener-kpi-value">{store.executionStatus.diagnostics ? (store.executionStatus.diagnostics.coverage_ratio.theme * 100).toFixed(1) : 0}%</span>
                    </div>
                    <div className="screener-coverage-grid">
                      {['theme', 'mainline', 'cycle', 'leader', 'technical'].map((dim) => (
                        <div key={dim} className="screener-coverage-cell">
                          <div className="metric-label">{dim}</div>
                          <div className="screener-kpi-value">
                            {store.executionStatus.diagnostics ? (store.executionStatus.diagnostics.coverage_ratio[dim as keyof typeof store.executionStatus.diagnostics.coverage_ratio] * 100).toFixed(0) : 0}%
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="screener-kpi-grid screener-kpi-grid-2">
                    <div className="screener-kpi-card">
                      <div className="metric-label">零分股票</div>
                      <div className="screener-kpi-value">{store.executionStatus.diagnostics?.zero_score_count || 0}</div>
                      <div className="workspace-note">综合得分为0的股票数量</div>
                    </div>

                    <div className="screener-kpi-card">
                      <div className="metric-label">缺失维度</div>
                      <div className="screener-missing-list">
                        {Object.entries(store.executionStatus.diagnostics.missing_dimension_count).filter(([_, count]) => count > 0).length > 0 ? (
                          Object.entries(store.executionStatus.diagnostics.missing_dimension_count)
                            .filter(([_, count]) => count > 0)
                            .map(([dim, count]) => (
                              <div key={dim} className="screener-missing-row">
                                <span className="capitalize">{dim}</span>
                                <strong>{count}</strong>
                              </div>
                            ))
                        ) : (
                          <span className="workspace-note">无缺失维度</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
        </section>
      </main>

      {/* 结果详情模态框 */}
      {showDetailModal && store.resultDetail && (
        <ResultDetailModal
          result={store.resultDetail}
          isOpen={showDetailModal}
          onClose={() => setShowDetailModal(false)}
          onAddFavorite={handleAddFavorite}
          onNavigateToStock={handleNavigateToStock}
          onNavigateToTheme={handleNavigateToTheme}
        />
      )}

      {/* 导出面板 */}
      {showExportPanel && (
        <ExportPanel
          results={store.currentResults}
          isOpen={showExportPanel}
          onClose={() => setShowExportPanel(false)}
        />
      )}
    </div>
  );
}
