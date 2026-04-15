import React from 'react';

interface ResultItem {
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
    amount?: number;
  };
  llm_review?: {
    decision: string;
    confidence?: number;
    reasoning?: string;
  };
}

interface ResultsFormViewProps {
  results: ResultItem[];
  isLoading: boolean;
  onRowClick: (resultId: string) => void;
  onAddFavorite: (resultId: string) => void;
  onNavigateToStock?: (stockId: string) => void;
  onNavigateToTheme?: (subjectKey: string) => void;
}

export function ResultsFormView(props: ResultsFormViewProps) {
  const { results, isLoading, onRowClick, onAddFavorite, onNavigateToStock, onNavigateToTheme } = props;

  const llmBadgeClass = (decision?: string): string => {
    if (decision === 'pass') return 'is-pass';
    if (decision === 'watch') return 'is-watch';
    if (decision === 'reject') return 'is-reject';
    return 'is-pending';
  };

  const llmLabel = (decision?: string): string => {
    if (decision === 'pass') return '通过';
    if (decision === 'watch') return '观察';
    if (decision === 'reject') return '拒绝';
    return '未复核';
  };

  if (isLoading) {
    return (
      <div className="workspace-card">
        <div className="empty-state">规则选股执行中，正在加载结果...</div>
      </div>
    );
  }

  if (results.length === 0) {
    return (
      <div className="workspace-card">
        <div className="empty-state">暂无选股结果，请先执行规则选股。</div>
      </div>
    );
  }

  return (
    <div className="recap-table-wrap">
      <table className="recap-table screener-results-table">
        <thead>
          <tr>
            <th>排名</th>
            <th>股票</th>
            <th>题材</th>
            <th>综合分</th>
            <th>维度评分</th>
            <th>LLM复核</th>
            <th>筛选理由</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          {results.map((item) => (
            <tr key={item.result_id}>
              <td>{item.rank_position}</td>
              <td>
                <button
                  type="button"
                  className="recap-theme-link recap-stock-highlight"
                  onClick={() => onNavigateToStock?.(item.stock_id)}
                >
                  {item.stock_name || item.stock_id}
                </button>
                <div className="workspace-note">{item.stock_id}</div>
              </td>
              <td>
                {item.theme_info?.subject_key ? (
                  <button
                    type="button"
                    className="recap-theme-link"
                    onClick={() => onNavigateToTheme?.(item.theme_info!.subject_key)}
                  >
                    {item.theme_info.theme_name || item.theme_info.subject_key}
                  </button>
                ) : (
                  '--'
                )}
              </td>
              <td>
                <div className="recap-score-cell">
                  <strong>{item.composite_score.toFixed(2)}</strong>
                </div>
              </td>
              <td>
                <div className="recap-tag-stack">
                  <span className="recap-chip is-status">{`主线 ${item.dimension_scores.mainline.toFixed(1)}`}</span>
                  <span className="recap-chip is-status">{`周期 ${item.dimension_scores.cycle.toFixed(1)}`}</span>
                  <span className="recap-chip is-status">{`龙头 ${item.dimension_scores.leader.toFixed(1)}`}</span>
                  <span className="recap-chip is-status">{`技术 ${item.dimension_scores.technical.toFixed(1)}`}</span>
                </div>
              </td>
              <td>
                <div className="recap-score-cell">
                  <span className={`recap-chip ${llmBadgeClass(item.llm_review?.decision)}`}>
                    {llmLabel(item.llm_review?.decision)}
                  </span>
                  {item.llm_review?.confidence !== undefined && (
                    <span className="workspace-note">{`置信度 ${(item.llm_review.confidence * 100).toFixed(0)}%`}</span>
                  )}
                </div>
              </td>
              <td className="recap-cell-wrap">{item.screening_reason || '--'}</td>
              <td>
                <div className="recap-tag-stack">
                  <button type="button" className="recap-theme-link" onClick={() => onRowClick(item.result_id)}>
                    详情
                  </button>
                  <button type="button" className="recap-theme-link" onClick={() => onAddFavorite(item.result_id)}>
                    收藏
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
