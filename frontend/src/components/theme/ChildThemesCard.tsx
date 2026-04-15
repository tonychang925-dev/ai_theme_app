import type { ThemeChild } from '../../lib/api';

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
          <span className="tag" key={`${item.child_subject_key ?? idx}`}>
            {String(item.child_name ?? item.child_subject_key ?? '--')}
          </span>
        ))}
      </div>
    </div>
  );
}