import React, { useMemo, useState } from 'react';

interface ResultItem {
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
  screening_reason: string;
  rank_position: number;
  theme_info?: {
    subject_key: string;
    theme_name: string;
  };
  weak_to_strong?: {
    candidate_score?: number;
    signal_level?: string;
    decision?: string;
    decision_label?: string;
    confirmation_score?: number;
  };
}

interface WeakToStrongTwoStageViewProps {
  tradeDate: string;
  confirmTradeDate?: string;
  signalCount?: number;
  snapshotHitCount?: number;
  confirmInputCandidateCount?: number;
  confirmFilteredOutCount?: number;
  xLevelCount?: number;
  isExecuting: boolean;
  runMode: 'post' | 'pre';
  candidateCount: number;
  results: ResultItem[];
  onRowClick: (resultId: string, view?: 'candidate' | 'confirm') => void;
  onAddFavorite: (resultId: string) => void;
  onNavigateToStock?: (stockId: string) => void;
  onNavigateToTheme?: (subjectKey: string) => void;
}

type TwoStageTab = 'confirm' | 'candidate' | 'merged';

function deriveSignalLevel(score: number): 'A' | 'B' | 'C' {
  if (score >= 65) return 'A';
  if (score >= 52) return 'B';
  return 'C';
}

function deriveDecision(score: number): 'confirmed' | 'watch' | 'reject' {
  const level = deriveSignalLevel(score);
  if (level === 'A') return 'confirmed';
  if (level === 'B') return 'watch';
  return 'reject';
}

function toDecisionLabel(decision?: string): string {
  const code = String(decision || '').toLowerCase();
  if (code === 'confirmed') return '通过';
  if (code === 'watch') return '观察';
  if (code === 'reject') return '不通过';
  if (code === 'no_decision') return '待判定';
  return decision || '--';
}

export function WeakToStrongTwoStageView(props: WeakToStrongTwoStageViewProps) {
  const {
    tradeDate,
    confirmTradeDate,
    signalCount,
    snapshotHitCount,
    confirmInputCandidateCount,
    confirmFilteredOutCount,
    xLevelCount,
    isExecuting,
    runMode,
    candidateCount,
    results,
    onRowClick,
    onAddFavorite,
    onNavigateToStock,
    onNavigateToTheme,
  } = props;
  const [tab, setTab] = useState<TwoStageTab>('confirm');
  const confirmResults = useMemo(
    () => results.filter((item) => Boolean(item.weak_to_strong?.signal_level)),
    [results],
  );
  const candidateResults = useMemo(
    () =>
      results
        .filter((item) => Boolean(item.weak_to_strong))
        .sort((a, b) => {
          const aScore = Number(a.weak_to_strong?.candidate_score ?? a.composite_score ?? 0);
          const bScore = Number(b.weak_to_strong?.candidate_score ?? b.composite_score ?? 0);
          return bScore - aScore;
        }),
    [results],
  );

  const levelCount = useMemo(() => {
    return confirmResults.reduce(
      (acc, item) => {
        const lvl = String(item.weak_to_strong?.signal_level || '');
        if (lvl === 'A' || lvl === 'B' || lvl === 'C' || lvl === 'X') {
          acc[lvl] += 1;
        }
        return acc;
      },
      { A: 0, B: 0, C: 0, X: 0 },
    );
  }, [confirmResults]);

  const stage1Status = isExecuting && runMode === 'post' ? 'running' : candidateCount > 0 ? 'success' : 'idle';
  const stage2Status = isExecuting && runMode === 'pre' ? 'running' : confirmResults.length > 0 ? 'success' : candidateCount > 0 ? 'partial' : 'idle';
  const stage2Text =
    stage2Status === 'running'
      ? '确认执行中...'
      : stage2Status === 'success'
        ? '已完成确认'
        : stage2Status === 'partial'
          ? '确认未产出信号（可能超时或数据缺失）'
          : '未执行确认';

  return (
    <div className="screener-two-stage-wrap">
      <div className="screener-two-stage-grid">
        <div className={`workspace-card screener-two-stage-card is-${stage1Status}`}>
          <div className="screener-step-head">
            <span className="screener-step-index">1</span>
            <strong>盘后候选池生成</strong>
          </div>
          <div className="screener-kpi-value">{candidateCount}</div>
          <div className="metric-label">候选池数量</div>
          <div className="workspace-note">候选日：{tradeDate}</div>
        </div>
        <div className={`workspace-card screener-two-stage-card is-${stage2Status}`}>
          <div className="screener-step-head">
            <span className="screener-step-index">2</span>
            <strong>盘前竞价确认</strong>
          </div>
          <div className="screener-kpi-value">{confirmResults.length}</div>
          <div className="metric-label">确认结果数</div>
          <div className="workspace-note">{stage2Text}</div>
          <div className="workspace-note">确认日：{confirmTradeDate || '--'}</div>
          <div className="workspace-note">signal_count：{signalCount ?? confirmResults.length}</div>
          <div className="workspace-note">snapshot_hit_count：{snapshotHitCount ?? '--'}</div>
          <div className="workspace-note">阶段2输入候选数：{confirmInputCandidateCount ?? '--'}</div>
          <div className="workspace-note">阶段2过滤数：{confirmFilteredOutCount ?? '--'}</div>
          <div className="workspace-note">X级数量：{xLevelCount ?? levelCount.X}</div>
        </div>
      </div>

      <div className="workspace-card screener-summary-card" style={{ marginTop: 12 }}>
        <div className="screener-kpi-grid">
          <div className="screener-kpi-card">
            <div className="screener-kpi-value">{levelCount.A}</div>
            <div className="metric-label">A级</div>
          </div>
          <div className="screener-kpi-card">
            <div className="screener-kpi-value">{levelCount.B}</div>
            <div className="metric-label">B级</div>
          </div>
          <div className="screener-kpi-card">
            <div className="screener-kpi-value">{levelCount.C}</div>
            <div className="metric-label">C级</div>
          </div>
          <div className="screener-kpi-card">
            <div className="screener-kpi-value">{levelCount.X}</div>
            <div className="metric-label">X级</div>
          </div>
        </div>
      </div>

      <div className="screener-tab-row" style={{ marginTop: 12 }}>
        <button type="button" className={`tag tag-button ${tab === 'confirm' ? 'tag-active' : ''}`} onClick={() => setTab('confirm')}>
          盘前确认结果
        </button>
        <button type="button" className={`tag tag-button ${tab === 'candidate' ? 'tag-active' : ''}`} onClick={() => setTab('candidate')}>
          盘后候选池
        </button>
        <button type="button" className={`tag tag-button ${tab === 'merged' ? 'tag-active' : ''}`} onClick={() => setTab('merged')}>
          综合视图
        </button>
      </div>

      <div className="recap-table-wrap" style={{ marginTop: 10 }}>
        <table className="recap-table screener-results-table">
          <thead>
            {tab === 'confirm' && (
              <tr>
                <th>股票</th>
                <th>题材名</th>
                <th>信号等级</th>
                <th>确认分</th>
                <th>决策</th>
                <th>说明</th>
                <th>操作</th>
              </tr>
            )}
            {tab === 'candidate' && (
              <tr>
                <th>排名</th>
                <th>股票</th>
                <th>题材名</th>
                <th>候选分</th>
                <th>入池理由</th>
                <th>操作</th>
              </tr>
            )}
            {tab === 'merged' && (
              <tr>
                <th>股票</th>
                <th>题材名</th>
                <th>候选分</th>
                <th>确认等级</th>
                <th>决策</th>
                <th>操作</th>
              </tr>
            )}
          </thead>
          <tbody>
            {((tab === 'confirm' && confirmResults.length === 0) || (tab !== 'confirm' && candidateResults.length === 0)) && (
              <tr>
                <td colSpan={7}>
                  <div className="empty-state">
                    {isExecuting
                      ? '两阶段执行中，正在加载结果...'
                      : tab === 'confirm'
                        ? '暂无盘前确认结果，请先点击“盘前确认”。'
                        : '暂无盘后候选池结果，请先点击“盘后选股”。'}
                  </div>
                </td>
              </tr>
            )}
            {(tab === 'confirm' ? confirmResults : candidateResults).map((item, idx) => {
              const candidateScore = Number(item.weak_to_strong?.candidate_score ?? item.composite_score ?? 0);
              const confirmScore = Number(item.weak_to_strong?.confirmation_score ?? item.composite_score ?? 0);
              const level = (item.weak_to_strong?.signal_level as 'A' | 'B' | 'C') || deriveSignalLevel(confirmScore);
              const decision = item.weak_to_strong?.decision || deriveDecision(confirmScore);
              const decisionLabel = item.weak_to_strong?.decision_label || toDecisionLabel(decision);
              return (
                <tr key={item.result_id}>
                  {tab === 'confirm' && (
                    <>
                      <td>
                        <button type="button" className="recap-theme-link recap-stock-highlight" onClick={() => onNavigateToStock?.(item.stock_id)}>
                          {item.stock_name || item.stock_id}
                        </button>
                        <div className="workspace-note">{item.stock_id}</div>
                      </td>
                      <td>
                        {item.theme_info?.subject_key ? (
                          <button type="button" className="recap-theme-link" onClick={() => onNavigateToTheme?.(item.theme_info!.subject_key)}>
                            {item.theme_info.theme_name || item.theme_info.subject_key}
                          </button>
                        ) : '--'}
                      </td>
                      <td><span className="recap-chip is-status">{level}</span></td>
                      <td><strong>{confirmScore.toFixed(2)}</strong></td>
                      <td>{decisionLabel}</td>
                      <td className="recap-cell-wrap">{item.screening_reason || '--'}</td>
                      <td>
                        <div className="recap-tag-stack">
                          <button type="button" className="recap-theme-link" onClick={() => onRowClick(item.result_id, 'confirm')}>详情</button>
                          <button type="button" className="recap-theme-link" onClick={() => onAddFavorite(item.result_id)}>收藏</button>
                        </div>
                      </td>
                    </>
                  )}
                  {tab === 'candidate' && (
                    <>
                      <td>{idx + 1}</td>
                      <td>
                        <button type="button" className="recap-theme-link recap-stock-highlight" onClick={() => onNavigateToStock?.(item.stock_id)}>
                          {item.stock_name || item.stock_id}
                        </button>
                        <div className="workspace-note">{item.stock_id}</div>
                      </td>
                      <td>{item.theme_info?.theme_name || item.theme_info?.subject_key || '--'}</td>
                      <td><strong>{candidateScore.toFixed(2)}</strong></td>
                      <td className="recap-cell-wrap">{item.screening_reason || '--'}</td>
                      <td>
                        <button type="button" className="recap-theme-link" onClick={() => onRowClick(item.result_id, 'candidate')}>详情</button>
                      </td>
                    </>
                  )}
                  {tab === 'merged' && (
                    <>
                      <td>
                        <button type="button" className="recap-theme-link recap-stock-highlight" onClick={() => onNavigateToStock?.(item.stock_id)}>
                          {item.stock_name || item.stock_id}
                        </button>
                        <div className="workspace-note">{item.stock_id}</div>
                      </td>
                      <td>{item.theme_info?.theme_name || item.theme_info?.subject_key || '--'}</td>
                      <td><strong>{candidateScore.toFixed(2)}</strong></td>
                      <td><span className="recap-chip is-status">{level}</span></td>
                      <td>{decisionLabel}</td>
                      <td>
                        <button type="button" className="recap-theme-link" onClick={() => onRowClick(item.result_id, item.weak_to_strong?.signal_level ? 'confirm' : 'candidate')}>详情</button>
                      </td>
                    </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
