import type { ThemeWorkspaceView } from '../../lib/api';

interface OverviewCardProps {
  themeName: string;
  payload: ThemeWorkspaceView;
  effectiveTradeDate: string;
  diagnostics?: ThemeWorkspaceView['diagnostics'];
}

export function OverviewCard({
  themeName,
  payload,
  effectiveTradeDate,
  diagnostics,
}: OverviewCardProps) {
  return (
    <div className="workspace-card">
      <span className="metric-label">题材概览</span>
      <strong>{themeName}</strong>
      <p className="workspace-note">subject_key: {payload.subject_key}</p>
      <p className="workspace-note">交易日: {effectiveTradeDate || '--'}</p>
      <p className="workspace-note">状态: {String(payload.detail.binding_status ?? '--')}</p>
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