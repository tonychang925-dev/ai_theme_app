import type { ThemeChild } from '../../lib/api';
import { navigateTo } from '../../lib/navigation';

interface ChildThemesCardProps {
  childItems: ThemeChild[];
}

export function ChildThemesCard({ childItems }: ChildThemesCardProps) {
  if (childItems.length === 0) {
    return (
      <div className="workspace-card">
        <span className="metric-label">子题材</span>
        <p className="workspace-note">暂无子题材</p>
      </div>
    );
  }

  return (
    <div className="workspace-card">
      <span className="metric-label">子题材</span>
      <div className="tag-row">
        {childItems.map((item, idx) => (
          <button
            type="button"
            className="tag tag-button"
            key={`${item.child_subject_key ?? idx}`}
            onClick={() => navigateTo(`/themes/${String(item.child_subject_key ?? '')}`)}
          >
            {String(item.child_name ?? item.child_subject_key ?? '--')}
          </button>
        ))}
      </div>
    </div>
  );
}