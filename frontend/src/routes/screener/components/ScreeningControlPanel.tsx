interface Strategy {
  strategy_id: string;
  strategy_name: string;
  strategy_type: string;
  description: string;
}

interface ScreeningControlPanelProps {
  strategies: Array<{ strategy_id: string; strategy_name: string; description?: string }>;
  selectedStrategyId: string | null;
  onStrategySelect: (strategyId: string) => void;
  selectedStrategy: Strategy | null;
  tradeDate: string;
  enableLlmReview: boolean;
  autoTuneMinScore: boolean;
  targetMinCount: number;
  targetMaxCount: number;
  onTradeDateChange: (date: string) => void;
  onEnableLlmReviewChange: (enable: boolean) => void;
  onAutoTuneMinScoreChange: (enable: boolean) => void;
  onTargetMinCountChange: (value: number) => void;
  onTargetMaxCountChange: (value: number) => void;
  onExecute: () => void;
  onExecuteStage2Only?: () => void;
  isExecuting: boolean;
  isTwoStageStrategy?: boolean;
  executionLabel?: string;
  runMode?: 'post' | 'pre';
}

export function ScreeningControlPanel(props: ScreeningControlPanelProps) {
  const {
    selectedStrategy,
    strategies,
    selectedStrategyId,
    onStrategySelect,
    tradeDate,
    enableLlmReview,
    autoTuneMinScore,
    targetMinCount,
    targetMaxCount,
    onTradeDateChange,
    onEnableLlmReviewChange,
    onAutoTuneMinScoreChange,
    onTargetMinCountChange,
    onTargetMaxCountChange,
    onExecute,
    onExecuteStage2Only,
    isExecuting,
    isTwoStageStrategy,
    executionLabel,
    runMode,
  } = props;

  const postRunning = isTwoStageStrategy ? (isExecuting && runMode === 'post') : isExecuting;
  const preRunning = Boolean(isTwoStageStrategy && isExecuting && runMode === 'pre');

  return (
    <div className="screener-form-stack">
      <div className="collection-section screener-step-card">
        <div className="screener-step-head">
          <span className="screener-step-index">1</span>
          <strong>选择交易日</strong>
        </div>
        <input type="date" value={tradeDate} onChange={(e) => onTradeDateChange(e.target.value)} className="screener-input" />
        <p className="workspace-note">选择要分析的交易日，系统将使用该日期的数据进行规则选股。</p>
      </div>

      <div className="collection-section screener-step-card">
        <div className="screener-step-head">
          <span className="screener-step-index">2</span>
          <strong>选择策略</strong>
        </div>
        <select value={selectedStrategyId ?? ''} onChange={(e) => onStrategySelect(e.target.value)} className="screener-input">
          <option value="" disabled>
            请选择选股策略
          </option>
          {strategies.map((s) => (
            <option key={s.strategy_id} value={s.strategy_id}>
              {/weak_to_strong/i.test(s.strategy_id) || /弱转强/.test(s.strategy_name)
                ? `${s.strategy_name}（两阶段）`
                : s.strategy_name}
            </option>
          ))}
        </select>
        <p className="workspace-note">{selectedStrategy?.description || '策略决定了选股评分权重和筛选逻辑。'}</p>
      </div>

      <div className="collection-section screener-step-card">
        <div className="screener-step-head">
          <span className="screener-step-index">3</span>
          <strong>LLM二次复核</strong>
        </div>
        <div className="screener-toggle-row">
          <p className="workspace-note">启用后将对规则结果 Top 20 做 AI 复核。</p>
          <button
            type="button"
            className={`screener-toggle ${enableLlmReview ? 'is-on' : ''}`}
            onClick={() => onEnableLlmReviewChange(!enableLlmReview)}
            aria-pressed={enableLlmReview}
          >
            <span />
          </button>
        </div>
      </div>

      <div className="collection-section screener-step-card">
        <div className="screener-step-head">
          <span className="screener-step-index">4</span>
          <strong>结果数量目标</strong>
        </div>
        <div className="screener-toggle-row">
          <p className="workspace-note">自动调分会根据得分分布微调阈值，使结果靠近目标区间。</p>
          <button
            type="button"
            className={`screener-toggle ${autoTuneMinScore ? 'is-on' : ''}`}
            onClick={() => onAutoTuneMinScoreChange(!autoTuneMinScore)}
            aria-pressed={autoTuneMinScore}
          >
            <span />
          </button>
        </div>
        <div className="collection-parameter-grid">
          <label className="collection-field">
            <span>目标最少数量</span>
            <input
              type="number"
              min={1}
              value={targetMinCount}
              onChange={(e) => onTargetMinCountChange(Number(e.target.value || 1))}
              className="screener-input"
            />
          </label>
          <label className="collection-field">
            <span>目标最多数量</span>
            <input
              type="number"
              min={1}
              value={targetMaxCount}
              onChange={(e) => onTargetMaxCountChange(Number(e.target.value || 1))}
              className="screener-input"
            />
          </label>
        </div>
      </div>

      <div className="collection-section screener-step-card">
        <div className="screener-step-head">
          <span className="screener-step-index">5</span>
          <strong>{isTwoStageStrategy ? '执行策略' : '执行选股'}</strong>
        </div>
        <button type="button" disabled={!selectedStrategy || isExecuting} onClick={onExecute} className="screener-run-button">
          {postRunning ? (
            <span className="screener-run-inline">
              <span className="screener-spinner" />
              {executionLabel || '执行中...'}
            </span>
          ) : (
            (isTwoStageStrategy ? '盘后选股' : '执行选股')
          )}
        </button>
        {isTwoStageStrategy && (
          <button
            type="button"
            disabled={!selectedStrategy || isExecuting}
            onClick={onExecuteStage2Only}
            className="screener-run-button"
            style={{ marginTop: 8 }}
          >
            {preRunning ? (
              <span className="screener-run-inline">
                <span className="screener-spinner" />
                盘前确认执行中...
              </span>
            ) : (
              '盘前确认'
            )}
          </button>
        )}
        <p className="workspace-note">
          {!selectedStrategy
            ? '请先选择策略。'
            : isTwoStageStrategy
              ? `“盘后选股”仅生成候选池；“盘前确认”仅对候选池做9:25后竞价确认（${tradeDate}）。`
              : `将使用“${selectedStrategy.strategy_name}”分析 ${tradeDate} 的数据。`}
        </p>
      </div>
    </div>
  );
}
