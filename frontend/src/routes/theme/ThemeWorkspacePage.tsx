import { useEffect, useState } from 'react';
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
import { fetchDailyReviewV2 } from '../../lib/api';

interface Props {
  subjectKey: string;
}

function q(name: string) {
  return new URLSearchParams(window.location.search).get(name) ?? '';
}

/** 从名称提取日期：支持 "6月24日热门题材复盘" 格式 */
function deriveDateFromName(name: string): string {
  const m = name.match(/(\d{1,2})月(\d{1,2})日/);
  if (!m) return "";
  const now = new Date();
  const year = String(now.getFullYear());
  const mon = m[1].padStart(2, "0");
  const day = m[2].padStart(2, "0");
  return `${year}-${mon}-${day}`;
}

function needsMatrixFallback(subjectKey: string, graph: unknown): boolean {
  return !graph || (!(graph as any)?.children?.length && !(graph as any)?.uncategorized_stocks?.length);
}

export function ThemeWorkspacePage({ subjectKey }: Props) {
  const tradeDate = q("date");
  const [activeTab, setActiveTab] = useState<"dynamics" | "detail" | "graph">("dynamics");
  const [matrixData, setMatrixData] = useState<any>(null);
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

  // 推断显示日期：URL参数 > 数据 > 名称提取
  const inferredDate = deriveDateFromName(themeName) || "";
  const displayDate = tradeDate || effectiveTradeDate || inferredDate;

  // 当 graph 为空时，加载涨停矩阵
  useEffect(() => {
    const date = displayDate;
    if (!needsMatrixFallback(subjectKey, graph)) return;
    if (!date) return;
    let cancelled = false;
    (async () => {
      try {
        const v2 = await fetchDailyReviewV2(date);
        if (cancelled) return;
        const m = (v2 as any)?.limit_up_theme_matrix;
        if (m && m.columns?.length > 0) { setMatrixData(m); return; }
      } catch {}
      try {
        const ym = date.replace(/-/g, '');
        const resp = await fetch(`/jyhf_matrix_${ym}.json`);
        if (cancelled || !resp.ok) return;
        const json = await resp.json();
        if (json.columns?.length > 0) setMatrixData(json);
      } catch {}
    })();
    return () => { cancelled = true; };
  }, [subjectKey, graph, displayDate]);

  const showMatrixFallback = needsMatrixFallback(subjectKey, graph);

  return (
    <div className="workspace-page">
      <WorkspaceHeader tradeDate={tradeDate} themeName={themeName} summary={summary} />

      {loading && <div className="empty-state">正在加载题材工作台...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <main className="workspace-layout single">
          <nav className="theme-tab-bar">
            <button className={`theme-tab ${activeTab === "dynamics" ? "active" : ""}`}
              onClick={() => setActiveTab("dynamics")}>题材动态</button>
            <button className={`theme-tab ${activeTab === "detail" ? "active" : ""}`}
              onClick={() => setActiveTab("detail")}>题材详情</button>
            <button className={`theme-tab ${activeTab === "graph" ? "active" : ""}`}
              onClick={() => setActiveTab("graph")}>题材图谱</button>
          </nav>

          <section className="workspace-column" style={{ display: activeTab === "dynamics" ? "block" : "none" }}>
            <PrimaryCycleCard summaryRow={summaryRow} />
            <TrendCard recentRankRows={recentRankRows} trendStats={trendStats} />
            <LeaderInflowCard rankedLeaderStocks={rankedLeaderStocks} />
            <LeaderTechCard leaderStocks={leaderStocks} />
            <HistoryCard historyItems={historyItems} />
            <ChildThemesCard childItems={childItems} />
            <StockPoolCard stockItems={stockItems} limit={12} />
          </section>

          <section className="workspace-column" style={{ display: activeTab === "detail" ? "block" : "none" }}>
            <OverviewCard
              themeName={themeName} payload={payload} effectiveTradeDate={effectiveTradeDate}
              diagnostics={diagnostics} summary={summary} detailHtml={detailHtml}
              reasonShort={reasonShort} nodeLevel={nodeLevel} parentSubjectKey={parentSubjectKey}
              historyCount={historyCount} childrenCount={childrenCount}
              stockCount={stockCount} bindingStatus={bindingStatus}
            />
          </section>

          <section className="workspace-column" style={{ display: activeTab === "graph" ? "block" : "none" }}>
            <SubjectGraphCard
              graph={graph}
              tradeDate={displayDate}
              fallbackMatrix={showMatrixFallback ? matrixData : null}
            />
          </section>
        </main>
      )}
    </div>
  );
}
