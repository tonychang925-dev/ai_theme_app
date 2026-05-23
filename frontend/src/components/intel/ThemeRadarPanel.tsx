import { navigateTo } from "../../lib/navigation";
import type { ThemeRadarItem } from "../../lib/api";

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    start: "启动",
    fermentation: "发酵",
    divergence: "分歧",
    rebound: "弱转强",
    climax: "高潮",
    fade: "退潮",
    fade_watch: "退潮观察",
    fade_confirmed: "退潮确认",
    repair: "修复",
  };
  return map[stage] ?? stage;
}

function stageClass(stage: string): string {
  const map: Record<string, string> = {
    start: "is-theme-start",
    fermentation: "is-theme-fermentation",
    divergence: "is-theme-divergence",
    rebound: "is-theme-rebound",
    climax: "is-theme-climax",
    fade: "is-theme-fade",
  };
  return map[stage] ?? "";
}

interface Props {
  themes: ThemeRadarItem[];
  loading?: boolean;
  error?: string | null;
  selectedTheme?: string | null;
  onThemeClick?: (themeId: string) => void;
  themeFilterEnabled?: boolean;
  onToggleFilter?: (enabled: boolean) => void;
}

export function ThemeRadarPanel({
  themes,
  loading,
  error,
  selectedTheme,
  onThemeClick,
  themeFilterEnabled,
  onToggleFilter,
}: Props) {
  const maxHeat = Math.max(1, ...themes.map((t) => t.heat));

  return (
    <aside className="theme-radar-panel">
      <div className="theme-radar-head">
        <span className="metric-label section-title">主题雷达</span>
        <span className="recap-chip is-status">{themes.length} 个</span>
      </div>

      {onToggleFilter && (
        <label className="workspace-note" style={{ display: "block", padding: "0 14px 8px" }}>
          <input type="checkbox" checked={!!themeFilterEnabled}
            onChange={(e) => onToggleFilter(e.target.checked)}
            style={{ marginRight: 6 }} />
          按左栏主题过滤中栏
        </label>
      )}

      {loading && <div className="empty-state compact">加载中...</div>}
      {error && <div className="empty-state compact error">{error}</div>}

      {!loading && !error && (
        <div className="theme-radar-list">
          {themes.map((item) => (
            <button
              key={item.theme_id}
              type="button"
              className={`theme-radar-item ${selectedTheme === item.theme_id ? "active" : ""}`}
              onClick={() => {
                if (onThemeClick) onThemeClick(item.theme_id);
                else navigateTo(`/themes/${encodeURIComponent(item.theme_id)}`);
              }}
            >
              <div className="theme-radar-item-head">
                <strong>{item.theme_name}</strong>
                <span className="recap-chip is-status">{item.heat}</span>
              </div>
              <div className="theme-radar-heat-track">
                <div
                  className="theme-radar-heat-fill"
                  style={{ width: `${Math.round((item.heat / maxHeat) * 100)}%` }}
                />
              </div>
              <div className="theme-radar-item-meta">
                {item.stage && item.stage !== "UNKNOWN" && stageLabel(item.stage) && (
                  <span className={`recap-chip ${stageClass(item.stage)}`}>
                    {stageLabel(item.stage)}
                  </span>
                )}
                {item.stock_count > 0 && (
                  <span className="recap-chip">{item.stock_count} 股</span>
                )}
              </div>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}
