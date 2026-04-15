interface ResultDetail {
  result_id: string;
  stock_id: string;
  stock_name: string;
  composite_score: number;
  screening_reason: string;
  theme_info?: {
    subject_key?: string;
    theme_name?: string;
    mainline_strength?: number;
    cycle_stage?: string;
  };
  dimension_scores?: {
    mainline: number;
    cycle: number;
    leader: number;
    technical: number;
  };
  dimension_details?: {
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
  llm_review?: {
    decision: 'pass' | 'watch' | 'reject' | 'failed';
    llm_score?: number;
    confidence?: number;
    reasoning: string;
    key_points: string[];
    risks: string[];
  };
  created_at?: string;
}

interface ResultDetailModalProps {
  result: ResultDetail;
  isOpen: boolean;
  onClose: () => void;
  onAddFavorite: (resultId: string) => void;
  onNavigateToStock: (stockId: string) => void;
  onNavigateToTheme: (subjectKey: string) => void;
}

export function ResultDetailModal(props: ResultDetailModalProps) {
  const { result, isOpen, onClose, onAddFavorite, onNavigateToStock, onNavigateToTheme } = props;
  if (!isOpen) return null;
  const llmReview = result.llm_review;
  const llmRisks = Array.isArray(llmReview?.risks) ? llmReview!.risks : [];
  const llmReasoning = typeof llmReview?.reasoning === 'string' ? llmReview.reasoning : '暂无复核理由';
  const scoreEntries = Object.entries(result.dimension_scores || {});

  return (
    <div className="collection-modal-backdrop">
      <div className="screener-detail-modal">
        <div className="screener-detail-head">
          <div>
            <h3>选股结果详情</h3>
            <p className="workspace-note">字段化展示评分、理由与复核结论</p>
          </div>
          <button type="button" onClick={onClose} className="tag tag-button">
            关闭
          </button>
        </div>

        <div className="screener-detail-body">
          <section className="collection-section">
            <strong>基本信息</strong>
            <div className="screener-detail-grid">
              <label className="collection-field">
                <span>股票</span>
                <button type="button" className="recap-theme-link recap-stock-highlight" onClick={() => onNavigateToStock(result.stock_id)}>
                  {result.stock_name || result.stock_id}
                </button>
                <div className="workspace-note">{result.stock_id}</div>
              </label>
              <label className="collection-field">
                <span>综合分</span>
                <strong className="screener-detail-value">{result.composite_score?.toFixed?.(2) ?? '-'}</strong>
              </label>
              <label className="collection-field screener-detail-span-2">
                <span>题材</span>
                {result.theme_info?.subject_key ? (
                  <button type="button" className="recap-theme-link" onClick={() => onNavigateToTheme(result.theme_info!.subject_key!)}>
                    {result.theme_info?.theme_name || result.theme_info?.subject_key}
                  </button>
                ) : (
                  <div className="workspace-note">--</div>
                )}
              </label>
              <label className="collection-field screener-detail-span-2">
                <span>筛选理由</span>
                <div className="screener-detail-text">{result.screening_reason || '--'}</div>
              </label>
            </div>
          </section>

          {scoreEntries.length > 0 && (
            <section className="collection-section">
              <strong>维度评分</strong>
              <div className="screener-detail-score-grid">
                {scoreEntries.map(([dim, score]) => (
                  <div key={dim} className="screener-detail-score-card">
                    <div className="metric-label">{dim}</div>
                    <div className="screener-kpi-value">{Number(score || 0).toFixed(1)}</div>
                    <div className="workspace-note">
                      {result.dimension_details?.[dim as keyof typeof result.dimension_details]?.reasoning || '无'}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {llmReview && (
            <section className="collection-section">
              <strong>LLM复核</strong>
              <div className="screener-detail-grid">
                <label className="collection-field">
                  <span>决策</span>
                  <span className="recap-chip is-status">{llmReview.decision?.toUpperCase?.() || '--'}</span>
                </label>
                {llmReview.llm_score !== undefined && (
                  <label className="collection-field">
                    <span>LLM评分</span>
                    <strong className="screener-detail-value">{llmReview.llm_score.toFixed(2)}</strong>
                  </label>
                )}
                {llmReview.confidence !== undefined && (
                  <label className="collection-field">
                    <span>置信度</span>
                    <strong className="screener-detail-value">{(llmReview.confidence * 100).toFixed(0)}%</strong>
                  </label>
                )}
                <label className="collection-field screener-detail-span-2">
                  <span>复核理由</span>
                  <div className="screener-detail-text">{llmReasoning}</div>
                </label>
                {llmRisks.length > 0 && (
                  <label className="collection-field screener-detail-span-2">
                    <span>风险标记</span>
                    <div className="screener-risk-tags">
                      {llmRisks.map((flag, index) => (
                        <span key={index} className="recap-chip is-risk">
                          {flag}
                        </span>
                      ))}
                    </div>
                  </label>
                )}
              </div>
            </section>
          )}

          {result.created_at && (
            <section className="collection-section">
              <strong>时间信息</strong>
              <div className="workspace-note">{new Date(result.created_at).toLocaleString()}</div>
            </section>
          )}
        </div>

        <div className="screener-detail-actions">
          <button
            type="button"
            onClick={onClose}
            className="tag tag-button"
          >
            关闭
          </button>
          <button
            type="button"
            onClick={() => onAddFavorite(result.result_id)}
            className="tag tag-button tag-active"
          >
            加入收藏
          </button>
        </div>
      </div>
    </div>
  );
}
