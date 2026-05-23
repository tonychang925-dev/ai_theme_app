import {
  translateStage,
  formatBillion,
  formatNumber,
} from '../../lib/utils/format';
import type { ThemeAnalyticsSummary } from '../../lib/api';

interface PrimaryCycleCardProps {
  summaryRow: ThemeAnalyticsSummary | null;
}

export function PrimaryCycleCard({ summaryRow }: PrimaryCycleCardProps) {
  if (!summaryRow) {
    return (
      <div className="workspace-card">
        <span className="metric-label">主线与周期</span>
        <p className="workspace-note">暂无复盘增强数据</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">主线与周期</span>
      <div className="market-summary-grid">
        <div className="workspace-card">
          <span className="metric-label">阶段</span>
          <strong>{translateStage(String(summaryRow.primary_cycle_stage ?? '--'))}</strong>
          <p className="workspace-note">动作: {String(summaryRow.action_bias ?? summaryRow.theme_action_bias ?? '--')}</p>
          <p className="workspace-note">{String(summaryRow.conclusion ?? '--')}</p>
        </div>
        <div className="workspace-card">
          <span className="metric-label">资金流入</span>
          <strong>总净流入 {formatBillion(summaryRow.main_net_inflow_sum)}</strong>
          <p className="workspace-note">前3净流入 {formatBillion(summaryRow.top3_main_net_inflow_sum)}</p>
          <p className="workspace-note">龙头净流入 {formatBillion(summaryRow.leader_main_net_inflow)}</p>
        </div>
        <div className="workspace-card">
          <span className="metric-label">识别分</span>
          <strong>事件 {formatNumber(summaryRow.event_chain_score)}</strong>
          <p className="workspace-note">市场 {formatNumber(summaryRow.market_recognition_score)}</p>
          <p className="workspace-note">稳定性 {formatNumber(summaryRow.mainline_stability_score)}</p>
        </div>
        <div className="workspace-card">
          <span className="metric-label">板块状态</span>
          <strong>{String(summaryRow.board_health_status ?? '--')}</strong>
          <p className="workspace-note">{String(summaryRow.board_effect_status ?? '--')}</p>
          <p className="workspace-note">
            {String(summaryRow.leader_support_status ?? '--')} /{' '}
            {String(summaryRow.follow_strength_status ?? '--')}
          </p>
        </div>
      </div>
    </div>
  );
}
