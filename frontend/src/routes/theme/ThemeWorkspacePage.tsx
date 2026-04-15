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

interface Props {
  subjectKey: string;
}

function q(name: string) {
  return new URLSearchParams(window.location.search).get(name) ?? '';
}

export function ThemeWorkspacePage({ subjectKey }: Props) {
  const tradeDate = q("date");
  const {
    payload,
    loading,
    error,
    historyItems,
    childItems,
    stockItems,
    analytics,
    summaryRow,
    recentRankRows,
    leaderStocks,
    rankedLeaderStocks,
    diagnostics,
    themeName,
    summary,
    effectiveTradeDate,
    trendStats,
  } = useThemeWorkspace(subjectKey, { tradeDate: tradeDate || undefined });



  return (
    <div className="workspace-page">
      <WorkspaceHeader tradeDate={tradeDate} themeName={themeName} summary={summary} />

      {loading && <div className="empty-state">正在加载题材工作台...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <main className="workspace-layout single">
          <section className="workspace-column">
            <OverviewCard
              themeName={themeName}
              payload={payload}
              effectiveTradeDate={effectiveTradeDate}
              diagnostics={diagnostics}
            />

            <PrimaryCycleCard summaryRow={summaryRow} />

            <TrendCard recentRankRows={recentRankRows} trendStats={trendStats} />

            <LeaderInflowCard rankedLeaderStocks={rankedLeaderStocks} />

            <LeaderTechCard leaderStocks={leaderStocks} />

            <HistoryCard historyItems={historyItems} />

            <ChildThemesCard childItems={childItems} />

            <StockPoolCard stockItems={stockItems} limit={12} />
          </section>
        </main>
      )}
    </div>
  );
}
