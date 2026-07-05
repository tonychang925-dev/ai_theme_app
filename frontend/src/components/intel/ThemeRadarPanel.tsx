import { useState } from 'react';
import { navigateTo } from "../../lib/navigation";
import type { ThemeRadarItem } from "../../lib/api";
import { ThemeSearchTab } from "./ThemeSearchTab";

function stageLabel(stage: string): string {
  const map: Record<string, string> = {
    start: "\u542f\u52a8",
    fermentation: "\u53d1\u919b",
    divergence: "\u5206\u6b67",
    rebound: "\u5f31\u8f6c\u5f3a",
    climax: "\u9ad8\u6f6e",
    fade: "\u9000\u6f6e",
    fade_watch: "\u9000\u6f6e\u89c2\u5bdf",
    fade_confirmed: "\u9000\u6f6e\u786e\u8ba4",
    repair: "\u4fee\u590d",
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

type PanelTab = "radar" | "search";

export function ThemeRadarPanel({
  themes,
  loading,
  error,
  selectedTheme,
  onThemeClick,
  themeFilterEnabled,
  onToggleFilter,
}: Props) {
  const [activeTab, setActiveTab] = useState<PanelTab>("radar");
  const maxHeat = Math.max(1, ...themes.map((t) => t.heat));

  return (
    <aside className="theme-radar-panel">
      <div className="theme-search-tab-bar">
        <button
          className={`theme-search-tab ${activeTab === "radar" ? "active" : ""}`}
          onClick={() => setActiveTab("radar")}
        >
          {"\u4e3b\u9898\u96f7\u8fbe"}
        </button>
        <button
          className={`theme-search-tab ${activeTab === "search" ? "active" : ""}`}
          onClick={() => setActiveTab("search")}
        >
          {"\u9898\u6750\u641c\u7d22"}
        </button>
      </div>

      {activeTab === "search" && (
        <ThemeSearchTab onThemeClick={onThemeClick} />
      )}

      {activeTab === "radar" && (
        <>
          <div className="theme-radar-head">
            <span className="metric-label section-title">{"\u4e3b\u9898\u96f7\u8fbe"}</span>
            <span className="recap-chip is-status">{themes.length} {"\u4e2a"}</span>
          </div>

          {onToggleFilter && (
            <label className="workspace-note" style={{ display: "block", padding: "0 14px 8px" }}>
              <input type="checkbox" checked={!!themeFilterEnabled}
                onChange={(e) => onToggleFilter(e.target.checked)}
                style={{ marginRight: 6 }} />
              {"\u6309\u5de6\u680f\u4e3b\u9898\u8fc7\u6ee4\u4e2d\u680f"}
            </label>
          )}

          {loading && <div className="empty-state compact">{"\u52a0\u8f7d\u4e2d..."}</div>}
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
                      <span className="recap-chip">{item.stock_count} {"\u80a1"}</span>
                    )}
                  </div>
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </aside>
  );
}
