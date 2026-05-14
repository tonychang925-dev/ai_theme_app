import type { ThemeWorkspaceView } from '../../lib/api';

interface OverviewCardProps {
  themeName: string;
  payload: ThemeWorkspaceView;
  effectiveTradeDate: string;
  diagnostics?: ThemeWorkspaceView['diagnostics'];
  summary?: string;
  detailHtml?: string;
  reasonShort?: string;
  nodeLevel?: string;
  parentSubjectKey?: string;
  historyCount?: number;
  childrenCount?: number;
  stockCount?: number;
  bindingStatus?: string;
}

export function OverviewCard({
  themeName,
  payload,
  effectiveTradeDate,
  diagnostics,
  summary,
  detailHtml,
  reasonShort,
  nodeLevel,
  parentSubjectKey,
  historyCount,
  childrenCount,
  stockCount,
  bindingStatus,
}: OverviewCardProps) {
  return (
    <div className="workspace-card">
      <span className="metric-label">题材概览</span>
      <strong>{themeName}</strong>

      {/* 核心标识行 */}
      <p className="workspace-note">
        subject_key: {payload.subject_key}
        {nodeLevel ? <span className="workspace-badge">L{nodeLevel}</span> : null}
      </p>

      {/* 状态 + 交易日 */}
      <p className="workspace-note">
        状态: {String(bindingStatus ?? '--')}
        <span style={{ marginLeft: 12 }}>交易日: {effectiveTradeDate || '--'}</span>
      </p>

      {/* 上级题材 */}
      {parentSubjectKey && (
        <p className="workspace-note">上级题材: {parentSubjectKey}</p>
      )}

      {/* 数据统计 */}
      {((historyCount ?? 0) > 0 || (childrenCount ?? 0) > 0 || (stockCount ?? 0) > 0) && (
        <p className="workspace-note">
          历史记录: {historyCount ?? 0}
          <span style={{ marginLeft: 8 }}>子题材: {childrenCount ?? 0}</span>
          <span style={{ marginLeft: 8 }}>关联股票: {stockCount ?? 0}</span>
        </p>
      )}

      {/* 摘要 */}
      {summary && (
        <div className="workspace-summary-block">
          <span className="metric-label">题材摘要</span>
          <p className="workspace-note">{summary}</p>
        </div>
      )}

      {/* 入选理由 */}
      {reasonShort && (
        <div className="workspace-summary-block">
          <span className="metric-label">入选理由</span>
          <p className="workspace-note">{reasonShort}</p>
        </div>
      )}

      {/* 详细HTML内容 */}
      {detailHtml && (
        <div className="workspace-summary-block">
          <span className="metric-label">详细内容</span>
          <div
            className="workspace-detail-html"
            dangerouslySetInnerHTML={{ __html: detailHtml }}
          />
        </div>
      )}

      {diagnostics?.partial && (
        <p className="workspace-note">
          增强数据加载不完整：
          {Array.isArray(diagnostics.missing_sections)
            ? diagnostics.missing_sections.join(' | ')
            : '--'}
        </p>
      )}
    </div>
  );
}
