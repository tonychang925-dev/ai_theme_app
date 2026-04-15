import { navigateTo } from '../../lib/navigation';

interface WorkspaceHeaderProps {
  tradeDate: string;
  themeName: string;
  summary: string;
}

export function WorkspaceHeader({ tradeDate, themeName, summary }: WorkspaceHeaderProps) {
  return (
    <header className="workspace-topbar">
      <button
        className="back-button"
        type="button"
        onClick={() =>
          navigateTo(
            tradeDate
              ? `/recap?date=${tradeDate}&report_type=post_market`
              : '/intel'
          )
        }
      >
        {tradeDate ? '返回复盘' : '返回情报台'}
      </button>
      <div>
        <p className="eyebrow">Theme Workspace</p>
        <h1>{themeName}</h1>
        <p className="subtle">{summary || '暂无题材摘要'}</p>
      </div>
    </header>
  );
}