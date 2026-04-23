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
  weak_to_strong?: {
    detail_view?: 'candidate' | 'confirm';
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
  weak_to_strong_replay?: {
    candidate_evidence?: {
      scores?: {
        breakdown?: {
          support_breakdown?: Record<string, unknown>;
          support_refs?: Array<Record<string, unknown>>;
          entry_components?: Record<string, unknown>;
          weekly_gate?: Record<string, unknown>;
        };
      };
      rules?: {
        hard_rule_results?: Array<{ rule?: string; passed?: boolean; reason?: string }>;
      };
      cycle_diagnostics?: {
        values?: Record<string, unknown>;
      };
    };
    signal_evidence?: {
      scores?: Record<string, unknown>;
      inputs?: Record<string, unknown>;
      decision?: Record<string, unknown>;
    };
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
  const dimNameMap: Record<string, string> = {
    mainline: '主线强度',
    cycle: '周期位置',
    leader: '龙头地位',
    technical: '技术形态',
  };
  const businessSummary = [
    `综合评分 ${Number(result.composite_score || 0).toFixed(2)} 分，用于衡量当前交易日的入选优先级。`,
    result.theme_info?.theme_name
      ? `该股票归属题材为“${result.theme_info.theme_name}”，可结合题材主线强弱判断持续性。`
      : '当前结果未返回明确题材归属，建议结合盘面补充确认题材线索。',
    result.screening_reason
      ? `系统入选理由：${result.screening_reason}`
      : '当前结果未返回明确的入选理由。',
  ];
  const candidateEvidence = result.weak_to_strong_replay?.candidate_evidence || {};
  const signalEvidence = result.weak_to_strong_replay?.signal_evidence || {};
  const evidenceBreakdown = candidateEvidence.scores?.breakdown || {};
  const hardRules = Array.isArray(candidateEvidence.rules?.hard_rule_results) ? candidateEvidence.rules?.hard_rule_results || [] : [];
  const cycleValues = candidateEvidence.cycle_diagnostics?.values || {};
  const supportBreakdown = evidenceBreakdown.support_breakdown || {};
  const supportRefs = Array.isArray(evidenceBreakdown.support_refs) ? evidenceBreakdown.support_refs || [] : [];
  const entryComponents = evidenceBreakdown.entry_components || {};
  const weeklyGate = evidenceBreakdown.weekly_gate || {};
  const signalScores = signalEvidence.scores || {};
  const signalInputs = signalEvidence.inputs || {};
  const signalDecision = signalEvidence.decision || {};
  const formatEvidenceValue = (value: unknown): string => {
    if (typeof value === 'number') return value.toFixed(2);
    if (typeof value === 'boolean') return value ? '是' : '否';
    if (value === null || value === undefined || value === '') return '--';
    return String(value);
  };
  const toneStyle = (tone: 'good' | 'bad' | 'neutral'): React.CSSProperties => {
    if (tone === 'good') return { color: '#15803d', fontWeight: 600 };
    if (tone === 'bad') return { color: '#b91c1c', fontWeight: 600 };
    return {};
  };
  const evidenceTone = (key: string, raw: unknown): 'good' | 'bad' | 'neutral' => {
    const n = Number(raw);
    if (!Number.isFinite(n)) return 'neutral';
    if (key === 'support_strength') return n >= 60 ? 'good' : n < 45 ? 'bad' : 'neutral';
    if (key === 'auction_open_pct') return n >= 1 ? 'good' : n < 0 ? 'bad' : 'neutral';
    if (key === 'last_minute_grab') return n >= 60 ? 'good' : n < 40 ? 'bad' : 'neutral';
    if (key === 'plate_follow') return n >= 60 ? 'good' : n < 40 ? 'bad' : 'neutral';
    if (key === 'risk_penalty') return n <= 10 ? 'good' : n > 25 ? 'bad' : 'neutral';
    if (key === 'confirmation_score') return n >= 65 ? 'good' : n < 52 ? 'bad' : 'neutral';
    if (key === 'mainline_strength_score') return n >= 60 ? 'good' : n < 40 ? 'bad' : 'neutral';
    if (key === 'leader_alive_score') return n >= 60 ? 'good' : n < 40 ? 'bad' : 'neutral';
    return 'neutral';
  };
  const renderEvidenceRows = (
    data: Record<string, unknown>,
    labelMap: Record<string, string>,
    orderedKeys?: string[],
  ) => {
    const keys = orderedKeys && orderedKeys.length > 0
      ? orderedKeys.filter((k) => k in data)
      : Object.keys(data);
    if (keys.length === 0) return <div className="workspace-note">--</div>;
    return (
      <>
        {keys.map((k) => (
          <div key={k} className="workspace-note" style={toneStyle(evidenceTone(k, data[k]))}>
            {labelMap[k] || k}：{formatEvidenceValue(data[k])}
          </div>
        ))}
      </>
    );
  };

  const dimensionBreakdown: Array<{ key: string; label: string; value: number; reasoning: string; detailItems: string[] }> = [
    {
      key: 'mainline',
      label: '主线强度',
      value: Number(result.dimension_scores?.mainline || 0),
      reasoning: result.dimension_details?.mainline?.reasoning || '暂无主线解释',
      detailItems: [
        `题材强度分：${Number(result.dimension_details?.mainline?.strength_score || 0).toFixed(1)}`,
        `热度排名分：${Number(result.dimension_details?.mainline?.heat_rank || 0).toFixed(1)}`,
        `资金关注分：${Number(result.dimension_details?.mainline?.capital_attention || 0).toFixed(1)}`,
      ],
    },
    {
      key: 'cycle',
      label: '周期位置',
      value: Number(result.dimension_scores?.cycle || 0),
      reasoning: result.dimension_details?.cycle?.reasoning || '暂无周期解释',
      detailItems: [
        `阶段分：${Number(result.dimension_details?.cycle?.stage_score || 0).toFixed(1)}`,
        `持续性分：${Number(result.dimension_details?.cycle?.duration_score || 0).toFixed(1)}`,
        `稳定性分：${Number(result.dimension_details?.cycle?.stability_score || 0).toFixed(1)}`,
      ],
    },
    {
      key: 'leader',
      label: '龙头地位',
      value: Number(result.dimension_scores?.leader || 0),
      reasoning: result.dimension_details?.leader?.reasoning || '暂无龙头解释',
      detailItems: [
        `位置分：${Number(result.dimension_details?.leader?.position_score || 0).toFixed(1)}`,
        `带动效应分：${Number(result.dimension_details?.leader?.leading_effect || 0).toFixed(1)}`,
        `资金认可分：${Number(result.dimension_details?.leader?.capital_recognition || 0).toFixed(1)}`,
      ],
    },
    {
      key: 'technical',
      label: '技术形态',
      value: Number(result.dimension_scores?.technical || 0),
      reasoning: result.dimension_details?.technical?.reasoning || '暂无技术解释',
      detailItems: [
        `异动分：${Number(result.dimension_details?.technical?.abnormal_score || 0).toFixed(1)}`,
        `形态分：${Number(result.dimension_details?.technical?.pattern_score || 0).toFixed(1)}`,
        `量价分：${Number(result.dimension_details?.technical?.volume_price_score || 0).toFixed(1)}`,
      ],
    },
  ];

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
              {result.weak_to_strong && (
                <label className="collection-field screener-detail-span-2">
                  <span>两阶段确认</span>
                  <div className="screener-detail-text">
                    入池依据：{result.weak_to_strong.candidate_type_label || result.weak_to_strong.candidate_type || '--'}；
                    视角：{result.weak_to_strong.detail_view === 'confirm' ? '盘前确认（含增量）' : '盘后候选（基础）'}；
                    候选日：{result.weak_to_strong.candidate_trade_date || '--'}；
                    确认日：{result.weak_to_strong.confirm_trade_date || '--'}；
                    确认等级：{result.weak_to_strong.signal_level || '--'}；
                    结论：{result.weak_to_strong.decision_label || result.weak_to_strong.decision || '--'}；
                    支撑类型：{result.weak_to_strong.support_type || '--'}；
                    支撑强度：{Number(result.weak_to_strong.support_strength || 0).toFixed(2)}；
                    候选分：{Number(result.weak_to_strong.candidate_score || 0).toFixed(2)}；
                    确认分：{Number(result.weak_to_strong.confirmation_score || 0).toFixed(2)}
                  </div>
                </label>
              )}
            </div>
          </section>

          <section className="collection-section">
            <strong>业务解读</strong>
            <div className="screener-detail-grid">
              <label className="collection-field screener-detail-span-2">
                <span>结论说明</span>
                <div className="screener-detail-text">
                  {businessSummary.map((line, idx) => (
                    <div key={idx}>{line}</div>
                  ))}
                </div>
              </label>
            </div>
          </section>

          {scoreEntries.length > 0 && (
            <section className="collection-section">
              <strong>维度评分与拆解</strong>
              <div className="screener-detail-score-grid">
                {scoreEntries.map(([dim, score]) => (
                  <div key={dim} className="screener-detail-score-card">
                    <div className="metric-label">{dimNameMap[dim] || dim}</div>
                    <div className="screener-kpi-value">{Number(score || 0).toFixed(1)}</div>
                    <div className="workspace-note">
                      {result.dimension_details?.[dim as keyof typeof result.dimension_details]?.reasoning || '无'}
                    </div>
                  </div>
                ))}
              </div>
              <div className="screener-detail-grid" style={{ marginTop: 12 }}>
                {dimensionBreakdown.map((item) => (
                  <label key={item.key} className="collection-field screener-detail-span-2">
                    <span>{item.label}（{item.value.toFixed(1)}）</span>
                    <div className="screener-detail-text">{item.reasoning}</div>
                    <div className="workspace-note">{item.detailItems.join('；')}</div>
                  </label>
                ))}
              </div>
            </section>
          )}

          {result.weak_to_strong && (
            <section className="collection-section">
              <strong>硬证据明细</strong>
              <div className="screener-detail-grid">
                <label className="collection-field screener-detail-span-2">
                  <span>候选入池硬规则</span>
                  <div className="screener-detail-text">
                    {hardRules.length === 0 ? '--' : hardRules.map((r, i) => (
                      <div key={i}>{r.rule || '--'}：{r.passed ? '通过' : '未通过'}{r.reason ? `（${r.reason}）` : ''}</div>
                    ))}
                  </div>
                </label>
                <label className="collection-field screener-detail-span-2">
                  <span>支撑结构证据</span>
                  <div className="screener-detail-text">
                    支撑强度：{Number(result.weak_to_strong.support_strength || 0).toFixed(2)}；支撑类型：{result.weak_to_strong.support_type || '--'}
                  </div>
                  {renderEvidenceRows(
                    weeklyGate as Record<string, unknown>,
                    {
                      passed: '周线门控是否通过',
                      reason: '门控原因',
                      weekly_position: '周线位置',
                      pullback_ratio: '回撤比例',
                    },
                    ['passed', 'reason', 'weekly_position', 'pullback_ratio'],
                  )}
                  {renderEvidenceRows(
                    supportBreakdown as Record<string, unknown>,
                    {
                      gap_support: '缺口支撑',
                      previous_low: '前低支撑',
                      previous_close: '昨收支撑',
                      pivot_support: '枢轴支撑',
                      fibonacci_support: '斐波支撑',
                      combined_strength: '综合支撑强度',
                    },
                  )}
                  {supportRefs.length > 0 && (
                    <div className="workspace-note">
                      支撑位样本：
                      {supportRefs.slice(0, 3).map((x, idx) => {
                        const item = x as Record<string, unknown>;
                        return ` #${idx + 1} ${formatEvidenceValue(item.type)}@${formatEvidenceValue(item.level)}(强度${formatEvidenceValue(item.strength)})`;
                      }).join('；')}
                    </div>
                  )}
                </label>
                <label className="collection-field screener-detail-span-2">
                  <span>主线与龙头证据</span>
                  <div className="workspace-note">主线强度：{Number(cycleValues.mainline_strength_score || 0).toFixed(2)}</div>
                  <div className="workspace-note">龙头存活分：{Number(cycleValues.leader_alive_score || 0).toFixed(2)}</div>
                  <div className="workspace-note">事件连续性：{Number(cycleValues.event_continuity_score || 0).toFixed(2)}</div>
                  {renderEvidenceRows(
                    entryComponents as Record<string, unknown>,
                    {
                      score_mainline_alive: '主线存活得分',
                      score_repair_window: '修复窗口得分',
                      score_support_quality: '支撑质量得分',
                      score_strong_background: '强势背景得分',
                      score_day_weak: '当日转弱得分',
                      score_prev_day_weak: '前日转弱得分',
                      penalty_fade_confirmed: '退潮扣分',
                    },
                  )}
                </label>
                {result.weak_to_strong.detail_view === 'confirm' && (
                  <label className="collection-field screener-detail-span-2">
                    <span>盘前确认增量证据</span>
                    {renderEvidenceRows(
                      signalInputs as Record<string, unknown>,
                      {
                        auction_open_pct: '开盘强度(%)',
                        auction_close_pct: '竞价收敛(%)',
                        auction_high_pct: '竞价高点(%)',
                        auction_low_pct: '竞价低点(%)',
                        support_strength: '支撑强度',
                        plate_red_ratio: '板块红盘比例',
                        plate_leader_strength: '板块龙头强度',
                      },
                      [
                        'auction_open_pct',
                        'auction_close_pct',
                        'auction_high_pct',
                        'auction_low_pct',
                        'support_strength',
                        'plate_red_ratio',
                        'plate_leader_strength',
                      ],
                    )}
                    {renderEvidenceRows(
                      signalScores as Record<string, unknown>,
                      {
                        price_strength: '开盘强度分',
                        pattern_stability: '形态稳定分',
                        last_minute_grab: '尾盘抢筹分',
                        plate_follow: '板块跟随分',
                        risk_penalty: '风险扣分',
                        confirmation_score: '确认总分',
                      },
                      ['price_strength', 'pattern_stability', 'last_minute_grab', 'plate_follow', 'risk_penalty', 'confirmation_score'],
                    )}
                    {renderEvidenceRows(
                      signalDecision as Record<string, unknown>,
                      {
                        signal_level: '信号等级',
                        decision: '决策',
                        data_status: '数据状态',
                        data_latency_ms: '数据延迟(ms)',
                      },
                      ['signal_level', 'decision', 'data_status', 'data_latency_ms'],
                    )}
                    <div className="workspace-note" style={{ marginTop: 8 }}>
                      阈值参考：确认总分 ≥65 偏强；52-64 观察；&lt;52 偏弱。支撑强度 ≥60 偏强；&lt;45 偏弱。
                    </div>
                  </label>
                )}
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
