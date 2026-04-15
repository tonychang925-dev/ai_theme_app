import type { ThemeHistory } from '../../lib/api';

interface HistoryCardProps {
  historyItems: ThemeHistory[];
}

export function HistoryCard({ historyItems }: HistoryCardProps) {
  if (historyItems.length === 0) {
    return (
      <div className="workspace-card">
        <span className="metric-label">历史驱动</span>
        <p className="workspace-note">暂无历史驱动</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">历史驱动</span>
      <ul className="workspace-list">
        {historyItems.slice(0, 10).map((item, idx) => (
          <li key={`${item.source_ref ?? idx}`}>
            <strong>{String(item.rank_date ?? '--')}</strong>
            <span>{String(item.description ?? item.theme_name ?? '--')}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}