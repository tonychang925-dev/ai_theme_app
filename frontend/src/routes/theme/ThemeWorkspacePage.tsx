import { useState } from 'react';
import { useThemeWorkspace } from '../../hooks/useThemeWorkspace';
import { WorkspaceHeader } from '../../components/theme/WorkspaceHeader';
import { OverviewCard } from '../../components/theme/OverviewCard';
import { PrimaryCycleCard } from '../../components/theme/PrimaryCycleCard';
import { TrendCard } from '../../components/theme/TrendCard';
import { LeaderInflowCard } from '../../components/theme/LeaderInflowCard';
import { LeaderTechCard } from '../../components/theme/LeaderTechCard';
import { HistoryCard } from '../../components/theme/HistoryCard';
import { ChildThemesCard } from '../../components/theme/ChildThemesCard';
import { StockPoolCard } from '../../components/theme/StockPoolCard';
import { SubjectGraphCard } from '../../components/theme/SubjectGraphCard';

interface Props {
  subjectKey: string;
}

function q(name: string) {
  return new URLSearchParams(window.location.search).get(name) ?? '';
}

export function ThemeWorkspacePage({ subjectKey }: Props) {
  const tradeDate = q("date");
  const [activeTab, setActiveTab] = useState<"dynamics" | "detail" | "graph">("dynamics");
  const {
    payload, loading, error,
    historyItems, childItems, stockItems,
    graph,
    analytics, summaryRow, recentRankRows,
    leaderStocks, rankedLeaderStocks, diagnostics,
    themeName, summary, detailHtml, reasonShort,
    nodeLevel, parentSubjectKey, historyCount,
    childrenCount, stockCount, bindingStatus,
    effectiveTradeDate, trendStats,
  } = useThemeWorkspace(subjectKey, { tradeDate: tradeDate || undefined });

  return (
    <div className="workspace-page">
      <WorkspaceHeader tradeDate={tradeDate} themeName={themeName} summary={summary} />

      {loading && <div className="empty-state">正在加载题材工作台...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <main className="workspace-layout single">
          {/* Tab bar */}
          <nav className="theme-tab-bar">
            <button
              className={`theme-tab ${activeTab === "dynamics" ? "active" : ""}`}
              onClick={() => setActiveTab("dynamics")}
            >
              题材动态
            </button>
            <button
              className={`theme-tab ${activeTab === "detail" ? "active" : ""}`}
              onClick={() => setActiveTab("detail")}
            >
              题材详情
            </button>
            <button
              className={`theme-tab ${activeTab === "graph" ? "active" : ""}`}
              onClick={() => setActiveTab("graph")}
            >
              题材图谱
            </button>
          </nav>

          {/* Tab: 题材动态 */}
          <section className="workspace-column" style={{ display: activeTab === "dynamics" ? "block" : "none" }}>
            <PrimaryCycleCard summaryRow={summaryRow} />
            <TrendCard recentRankRows={recentRankRows} trendStats={trendStats} />
            <LeaderInflowCard rankedLeaderStocks={rankedLeaderStocks} />
            <LeaderTechCard leaderStocks={leaderStocks} />
            <HistoryCard historyItems={historyItems} />
            <ChildThemesCard childItems={childItems} />
            <StockPoolCard stockItems={stockItems} limit={12} />
          </section>

          {/* Tab: 题材详情 */}
          <section className="workspace-column" style={{ display: activeTab === "detail" ? "block" : "none" }}>
            <OverviewCard
              themeName={themeName}
              payload={payload}
              effectiveTradeDate={effectiveTradeDate}
              diagnostics={diagnostics}
              summary={summary}
              detailHtml={detailHtml}
              reasonShort={reasonShort}
              nodeLevel={nodeLevel}
              parentSubjectKey={parentSubjectKey}
              historyCount={historyCount}
              childrenCount={childrenCount}
              stockCount={stockCount}
              bindingStatus={bindingStatus}
            />
          </section>

          {/* Tab: 题材图谱 */}
          <section className="workspace-column" style={{ display: activeTab === "graph" ? "block" : "none" }}>
            <SubjectGraphCard graph={graph} />
          </section>
        </main>
      )}
    </div>
  );
}
