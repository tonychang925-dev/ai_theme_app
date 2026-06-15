import { Alert } from "antd";
import { useMemo } from "react";
import { navigateTo } from "../../../lib/navigation";

type RowRecord = Record<string, any>;

interface Props {
  reportType: "pre_market" | "post_market";
  tradeDate?: string;
  onShowEngine?: () => void;
  highlights: string[];
  marketEnvironmentSection: string[];
  themeEnvironmentSection: string[];
  themeSection: string[];
  themeSummaryRows: RowRecord[];
  themeCapitalFlowRows: RowRecord[];
  strongStockSection: string[];
  strongStockGroups: Array<[string, RowRecord[]]>;
  watchlistSection: string[];
  watchlistRows: RowRecord[];
  stockCapitalFlowSection: string[];
  stockCapitalFlowRows: RowRecord[];
  moneySection: string[];
  moneyFlowRows: RowRecord[];
  abnormalSection: string[];
  abnormalNote: string;
  abnormalRows: RowRecord[];
  sortedAbnormalRows: RowRecord[];
  auctionSection: string[];
  auctionValidationSection: string[];
  auxSection: string[];
  dragonTigerNote: string;
  dragonTigerRows: Array<{ hotMoneyName: string; items: Array<{ theme: string; stockName: string; sideNet: string }> }>;
  themeKeyByTheme: Map<string, string>;
}

function zh(value: string) {
  const replacements: Array<[string, string]> = [
    ["risk_off", "避险防御"],
    ["risk_on", "进攻偏多"],
    ["neutral", "中性"],
    ["strong_branch", "强分支"],
    ["main", "主线"],
    ["HIGH", "高"],
    ["MEDIUM", "中"],
    ["LOW", "低"],
    ["start", "启动"],
    ["fermentation", "发酵"],
    ["divergence", "分歧"],
    ["rebound", "弱转强"],
    ["climax", "高潮"],
    ["fade", "退潮"],
  ];
  let text = String(value ?? "");
  for (const [from, to] of replacements) {
    text = text.split(from).join(to);
  }
  return text;
}

function splitThemeLine(value: string) {
  const raw = String(value ?? "");
  const idx = raw.indexOf("：");
  if (idx < 0) return { theme: "", body: raw };
  return {
    theme: raw.slice(0, idx).trim(),
    body: raw.slice(idx + 1).trim(),
  };
}

function splitSummaryLine(value: string) {
  const text = String(value ?? "").trim();
  const match = text.match(/^([^：:]{2,16})[：:]\s*(.*)$/);
  if (!match) return { label: "", body: text };
  return { label: match[1], body: match[2] || text };
}

function renderThemeLink(theme: string, subjectKey?: string, tradeDate?: string) {
  if (!subjectKey || subjectKey === "--") return theme;
  const suffix = tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : "";
  return (
    <button type="button" className="recap-theme-link" onClick={() => navigateTo(`/themes/${subjectKey}${suffix}`)}>
      {theme}
    </button>
  );
}

function renderScoredCell(value: string) {
  const raw = zh(value || "--");
  const [score, desc] = raw.split("｜", 2);
  return (
    <div className="recap-score-cell">
      <strong>{score || "--"}</strong>
      {desc && <p className="workspace-note">{desc}</p>}
    </div>
  );
}

function renderThemeStatusTags(values: string[]) {
  const items = values.map((item) => zh(item || "--")).filter((item) => item && item !== "--");
  if (items.length === 0) return <span className="workspace-note">--</span>;
  return (
    <div className="recap-tag-stack">
      {items.map((item, idx) => {
        let cls = "is-basis";
        if (item.includes("启动")) cls = "is-theme-start";
        else if (item.includes("发酵")) cls = "is-theme-fermentation";
        else if (item.includes("分歧")) cls = "is-theme-divergence";
        else if (item.includes("弱转强")) cls = "is-theme-rebound";
        else if (item.includes("高潮")) cls = "is-theme-climax";
        else if (item.includes("退潮")) cls = "is-theme-fade";
        else if (item.includes("主做")) cls = "is-role";
        else if (item.includes("试错") || item.includes("观察")) cls = "is-status";
        else if (item.includes("放弃") || item.includes("警惕")) cls = "is-abnormal-tail";
        return (
          <span key={`${item}-${idx}`} className={`recap-chip ${cls}`}>
            {item}
          </span>
        );
      })}
    </div>
  );
}

function renderAbnormalCapital(value: string) {
  const text = zh(value || "--");
  if (text === "--") return <span className="workspace-note">--</span>;
  const parts = text.split("；").map((item) => item.trim()).filter(Boolean);
  return (
    <div className="recap-tag-stack">
      {parts.map((part, idx) => {
        let cls = "is-basis";
        if (part.includes("游资买入")) cls = "is-role";
        else if (part.includes("机构净买")) cls = "is-status";
        else if (part.includes("主力净流入")) cls = "is-basis";
        return (
          <span key={`${part}-${idx}`} className={`recap-chip ${cls}`}>
            {part}
          </span>
        );
      })}
    </div>
  );
}

function renderAbnormalLabels(value: string) {
  const text = zh(value || "--");
  if (text === "--") return <span className="workspace-note">--</span>;
  const parts = text.split("/").map((item) => item.trim()).filter(Boolean);
  return (
    <div className="recap-tag-stack">
      {parts.map((part, idx) => {
        let cls = "is-basis";
        if (part.includes("换手")) cls = "is-abnormal-turnover";
        else if (part.includes("倍量") || part.includes("放量")) cls = "is-abnormal-volume";
        else if (part.includes("尾盘")) cls = "is-abnormal-tail";
        else if (part.includes("游资")) cls = "is-role";
        else if (part.includes("机构")) cls = "is-status";
        else if (part.includes("主力")) cls = "is-basis";
        return (
          <span key={`${part}-${idx}`} className={`recap-chip ${cls}`}>
            {part}
          </span>
        );
      })}
    </div>
  );
}

function renderF10CapitalSummary(value: unknown) {
  const f10 = value as Record<string, unknown> | undefined;
  if (!f10 || typeof f10 !== "object") return <span className="workspace-note">--</span>;
  const capitalFlow = (f10.capital_flow as Record<string, unknown> | undefined) || {};
  const dragonTiger = (f10.dragon_tiger as Record<string, unknown> | undefined) || {};
  const marginTrading = (f10.margin_trading as Record<string, unknown> | undefined) || {};
  const parts = [
    String(capitalFlow.summary || f10.summary || "").trim(),
    dragonTiger.summary ? `龙虎榜：${String(dragonTiger.summary)}` : "",
    marginTrading.summary ? `融资融券：${String(marginTrading.summary)}` : "",
  ].filter((item) => item && item !== "--");
  if (parts.length === 0) return <span className="workspace-note">--</span>;
  return <div style={{ lineHeight: 1.5 }}>{parts.join("；")}</div>;
}

export default function LegacyRecapSections({
  reportType,
  tradeDate,
  onShowEngine,
  highlights,
  marketEnvironmentSection,
  themeEnvironmentSection,
  themeSection,
  themeSummaryRows,
  themeCapitalFlowRows,
  strongStockSection,
  strongStockGroups,
  watchlistSection,
  watchlistRows,
  stockCapitalFlowSection,
  stockCapitalFlowRows,
  moneySection,
  moneyFlowRows,
  abnormalSection,
  abnormalNote,
  abnormalRows,
  sortedAbnormalRows,
  auctionSection,
  auctionValidationSection,
  auxSection,
  dragonTigerNote,
  dragonTigerRows,
  themeKeyByTheme,
}: Props) {
  const mainThemeRows = useMemo(() => themeSummaryRows.filter((row) => row.tier === "主线"), [themeSummaryRows]);
  const branchThemeRows = useMemo(() => themeSummaryRows.filter((row) => row.tier === "强分支"), [themeSummaryRows]);
  const showThemeMainlineCard = reportType === "post_market" || themeSection.length > 0;
  const showThemeCapitalFlowCard = reportType === "post_market" || themeCapitalFlowRows.length > 0;
  const showStrongStockCard = reportType === "post_market" || strongStockSection.length > 0;
  const showWatchlistCard = reportType === "post_market" || watchlistSection.length > 0;
  const showStockCapitalCard = reportType === "post_market" || stockCapitalFlowRows.length > 0;
  const showAbnormalCard = reportType === "post_market" || abnormalSection.length > 0;
  const showMoneyCard = reportType === "post_market" || moneySection.length > 0;
  const showAuxCard = reportType === "post_market" || auxSection.length > 0;

  return (
    <>
      {reportType === "post_market" && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          message="旧版 sections 仅用于排查与兼容展示，不参与交易结论。"
        />
      )}
      {reportType === "post_market" && onShowEngine && (
        <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
          <button type="button" className="tag tag-button" onClick={onShowEngine}>
            返回引擎视图
          </button>
        </div>
      )}
      {(marketEnvironmentSection.length > 0 || highlights.length > 0) && (
        <div className="workspace-card market-summary-group">
          <span className="metric-label section-title">市场总览</span>
          <div className="market-summary-grid">
            {marketEnvironmentSection.length > 0 && (
              <div className="market-bias-card market-summary-card">
                <span className="metric-label section-title">大盘环境总结</span>
                <div className="market-bias-hero">
                  <strong>{zh(marketEnvironmentSection[0])}</strong>
                  {marketEnvironmentSection[1] && (
                    <p className="workspace-note">{zh(marketEnvironmentSection[1])}</p>
                  )}
                </div>
                {marketEnvironmentSection.length > 2 && (
                  <ul className="workspace-list market-bias-list">
                    {marketEnvironmentSection.slice(2).map((item, idx) => {
                      const parsed = splitSummaryLine(item);
                      return (
                        <li key={`market-env-${idx}`}>
                          <strong>{parsed.label || `环境观察 ${idx + 1}`}</strong>
                          <p className="workspace-note">{zh(parsed.body)}</p>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            )}
            <div className="market-summary-card">
              <span className="metric-label section-title">核心要点</span>
              {highlights.length > 0 ? (
                <ul className="workspace-list">
                  {highlights.map((item, idx) => {
                    const parsed = splitSummaryLine(item);
                    return (
                      <li key={`highlight-${idx}`}>
                        <strong>{parsed.label || `要点 ${idx + 1}`}</strong>
                        <p className="workspace-note">{zh(parsed.body)}</p>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="workspace-note">暂无高亮摘要</p>
              )}
            </div>
          </div>
        </div>
      )}

      {showThemeMainlineCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">{reportType === "post_market" ? "主线与支线" : "可做主线与支线"}</span>
        {reportType === "post_market" ? (
          themeSummaryRows.length > 0 ? (
            <div className="recap-table-stack">
              <article className="workspace-card recap-table-card">
                <div className="recap-table-head"><strong>主线</strong></div>
                <div className="recap-table-wrap">
                  <table className="recap-table">
                    <thead>
                      <tr>
                        <th>题材</th>
                        <th>总净流入</th>
                        <th>龙头净流入</th>
                        <th>题材K线</th>
                        <th>事件分</th>
                        <th>市场分</th>
                        <th>周期阶段</th>
                        <th>操作建议</th>
                        <th>结论</th>
                      </tr>
                    </thead>
                    <tbody>
                      {mainThemeRows.map((row, idx) => (
                        <tr key={`main-theme-row-${idx}`}>
                          <td>{renderThemeLink(row.theme, row.subjectKey, tradeDate)}</td>
                          <td>{row.totalInflow}</td>
                          <td>{row.leaderInflow}</td>
                          <td>{row.themeKline}</td>
                          <td>{row.eventScore}</td>
                          <td>{row.marketScore}</td>
                          <td>{renderThemeStatusTags([row.cycleStage])}</td>
                          <td>{renderThemeStatusTags([row.actionAdvice])}</td>
                          <td>{row.conclusion}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </article>
              {branchThemeRows.length > 0 && (
                <article className="workspace-card recap-table-card">
                  <div className="recap-table-head"><strong>强分支</strong></div>
                  <div className="recap-table-wrap">
                    <table className="recap-table">
                      <thead>
                        <tr>
                          <th>题材</th>
                          <th>总净流入</th>
                          <th>龙头净流入</th>
                          <th>题材K线</th>
                          <th>事件分</th>
                          <th>市场分</th>
                          <th>周期阶段</th>
                          <th>操作建议</th>
                          <th>结论</th>
                        </tr>
                      </thead>
                      <tbody>
                        {branchThemeRows.map((row, idx) => (
                          <tr key={`branch-theme-row-${idx}`}>
                            <td>{renderThemeLink(row.theme, row.subjectKey, tradeDate)}</td>
                            <td>{row.totalInflow}</td>
                            <td>{row.leaderInflow}</td>
                            <td>{row.themeKline}</td>
                            <td>{row.eventScore}</td>
                            <td>{row.marketScore}</td>
                            <td>{renderThemeStatusTags([row.cycleStage])}</td>
                            <td>{renderThemeStatusTags([row.actionAdvice])}</td>
                            <td>{row.conclusion}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </article>
              )}
            </div>
          ) : (
            <p className="workspace-note">暂无数据，请检查 report.sections.主线与支线</p>
          )
        ) : (
          <ul className="workspace-list">
            {themeSection.map((item, idx) => {
              const parsed = splitThemeLine(item);
              return (
                <li key={`theme-watch-${idx}`}>
                  <strong>{parsed.theme || `条目 ${idx + 1}`}</strong>
                  <p className="workspace-note">{zh(parsed.body)}</p>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      )}

      {showThemeCapitalFlowCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">主线资金流入前10</span>
        {themeCapitalFlowRows.length > 0 ? (
          <div className="recap-table-wrap">
            <table className="recap-table">
              <thead>
                <tr>
                  <th>题材</th>
                  <th>层级</th>
                  <th>总净流入</th>
                  <th>前3净流入</th>
                  <th>龙头净流入</th>
                  <th>流入股数</th>
                  <th>题材K线</th>
                  <th>阶段</th>
                  <th>动作</th>
                </tr>
              </thead>
              <tbody>
                {themeCapitalFlowRows.map((row, idx) => (
                  <tr key={`theme-capital-${idx}`}>
                    <td>{renderThemeLink(row.theme, row.subjectKey, tradeDate)}</td>
                    <td>{row.tier}</td>
                    <td>{row.totalInflow}</td>
                    <td>{row.top3Inflow}</td>
                    <td>{row.leaderInflow}</td>
                    <td>{row.inflowCount}</td>
                    <td>{row.themeKline}</td>
                    <td>{renderThemeStatusTags([row.stage])}</td>
                    <td>{renderThemeStatusTags([row.action])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="workspace-note">暂无数据，请检查 report.sections.主线资金流入前10</p>
        )}
      </div>
      )}

      {showStrongStockCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">{reportType === "post_market" ? "强势股分层" : "盘前重点盯盘个股"}</span>
        {reportType === "post_market" ? (
          strongStockGroups.length > 0 ? (
            <div className="recap-table-stack">
              {strongStockGroups.map(([themeName, rows]) => (
                <article className="workspace-card recap-table-card" key={`stock-${themeName}`}>
                  <div className="recap-table-head">
                    <strong>{themeName}</strong>
                  </div>
                  <div className="recap-table-wrap">
                    <table className="recap-table">
                      <thead>
                        <tr>
                          <th>股票</th>
                          <th>角色</th>
                          <th>综合分</th>
                          <th>正宗性</th>
                          <th>领涨性</th>
                          <th>资金量能</th>
                          <th>结构位置</th>
                          <th>抗跌承接</th>
                          <th>资金</th>
                          <th>K线位置</th>
                          <th>K线形态</th>
                          <th>LLM判断</th>
                          <th>LLM理由</th>
                          <th>评分依据</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row, idx) => (
                          <tr key={`row-${themeName}-${idx}`} data-role={String(row.raw || "").includes("淘汰 ") ? "eliminated" : "other"}>
                            <td>{row.stockName}</td>
                            <td>{row.role}</td>
                            <td>{row.compositeScore}</td>
                            <td>{renderScoredCell(row.purityScore)}</td>
                            <td>{renderScoredCell(row.leadingScore)}</td>
                            <td>{renderScoredCell(row.capitalScore)}</td>
                            <td>{renderScoredCell(row.structureScore)}</td>
                            <td>{renderScoredCell(row.resilienceScore)}</td>
                            <td>{row.moneyFlow}</td>
                            <td>{row.klinePosition}</td>
                            <td>{row.klinePattern}</td>
                            <td>{renderThemeStatusTags([row.llmRole, row.llmLeaderStatus, row.llmConfirmationBasis])}</td>
                            <td className="recap-cell-wrap recap-cell-llm-reason">{row.llmReason}</td>
                            <td>{row.rationale}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <p className="workspace-note">暂无数据，请检查 report.sections.强势股分层</p>
          )
        ) : (
          <ul className="workspace-list">
            {strongStockSection.map((item, idx) => {
              const parsed = splitThemeLine(item);
              return (
                <li key={`watch-stock-${idx}`}>
                  <strong>{parsed.theme || `条目 ${idx + 1}`}</strong>
                  <p className="workspace-note">{zh(parsed.body)}</p>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      )}

      {showWatchlistCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">次日观察清单</span>
        {watchlistRows.length > 0 ? (
          <div className="recap-table-wrap">
            <table className="recap-table recap-table-watchlist">
              <thead>
                <tr>
                  <th>股票</th>
                  <th>类别</th>
                  <th>题材</th>
                  <th>角色</th>
                  <th>阶段</th>
                  <th>动作</th>
                  <th>量比</th>
                  <th>形态</th>
                  <th>Flag</th>
                  <th>龙虎榜</th>
                  <th>催化/异动</th>
                  <th>买入条件</th>
                  <th>失效条件</th>
                </tr>
              </thead>
              <tbody>
                {watchlistRows.map((row, idx) => (
                  <tr key={`watchlist-${idx}`}>
                    <td className="recap-stock-highlight">{row.stockName}</td>
                    <td>{row.category}</td>
                    <td>{row.showTheme ? renderThemeLink(row.theme, row.subjectKey, tradeDate) : ""}</td>
                    <td>{row.role}</td>
                    <td>{renderThemeStatusTags([row.stage])}</td>
                    <td>{row.action !== "--" ? row.action : "--"}</td>
                    <td>{row.volumeRatio !== "--" ? row.volumeRatio : "--"}</td>
                    <td className="recap-cell-wrap">{row.pattern !== "--" ? row.pattern : "--"}</td>
                    <td>{row.flag !== "--" ? row.flag : "--"}</td>
                    <td>{row.dragonDays !== "--" ? `${row.dragonDays}天` : "--"}</td>
                    <td className="recap-cell-wrap">{zh([row.catalyst !== "--" ? row.catalyst : "", row.labels !== "--" ? row.labels : ""].filter(Boolean).join("；") || "--")}</td>
                    <td className="recap-cell-wrap">{zh(row.buyCondition || "--")}</td>
                    <td className="recap-cell-wrap">{zh(row.invalidCondition || "--")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="workspace-note">暂无数据，请检查 report.sections.次日观察清单</p>
        )}
      </div>
      )}

      {showStockCapitalCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">股票资金流入前20</span>
        {stockCapitalFlowRows.length > 0 ? (
          <div className="recap-table-wrap">
            <table className="recap-table">
              <thead>
                <tr>
                  <th>股票</th>
                  <th>题材</th>
                  <th>主力净流入</th>
                  <th>题材内排名</th>
                  <th>涨幅</th>
                  <th>龙头</th>
                  <th>Flag</th>
                </tr>
              </thead>
              <tbody>
                {stockCapitalFlowRows.map((row, idx) => (
                  <tr key={`stock-capital-${idx}`}>
                    <td className="recap-stock-highlight">{row.stockName}</td>
                    <td>{renderThemeLink(row.theme, themeKeyByTheme.get(row.theme), tradeDate)}</td>
                    <td>{row.mainInflow}</td>
                    <td>{row.rankOrder}</td>
                    <td>{row.pctChg}</td>
                    <td>{row.isLeader}</td>
                    <td>{row.flag}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="workspace-note">暂无数据，请检查 report.sections.主线股票资金流入前20</p>
        )}
      </div>
      )}

      {showAbnormalCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">当日异动股与资金行为</span>
        {abnormalNote && <p className="workspace-note">{zh(abnormalNote)}</p>}
        {sortedAbnormalRows.length > 0 ? (
          <div className="recap-table-wrap">
            <table className="recap-table">
              <thead>
                <tr>
                  <th>股票</th>
                  <th>题材</th>
                  <th>异动分</th>
                  <th>换手率</th>
                  <th>量比</th>
                  <th>成交量/50日均量</th>
                  <th>资金</th>
                  <th>异动标签</th>
                  <th>结论</th>
                </tr>
              </thead>
              <tbody>
                {sortedAbnormalRows.map((row, idx) => (
                  <tr key={`abnormal-row-${idx}`}>
                    <td className="recap-stock-highlight">{row.stockName}</td>
                    <td>{row.theme}</td>
                    <td>{row.score}</td>
                    <td>{row.turnoverRate}</td>
                    <td>{row.volumeRatio}</td>
                    <td>{row.volumeVsMa50}</td>
                    <td>{renderAbnormalCapital(row.capital)}</td>
                    <td>{renderAbnormalLabels(row.labels)}</td>
                    <td>{row.conclusion}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="workspace-note">暂无数据，请检查 report.sections.当日异动股与资金行为</p>
        )}
      </div>
      )}

      {showMoneyCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">资金行为增强</span>
        {moneyFlowRows.length > 0 ? (
          <div className="recap-table-wrap">
            <table className="recap-table">
              <thead>
                <tr>
                  <th>题材</th>
                  <th>股票</th>
                  <th>资金角色</th>
                  <th>资金分层</th>
                  <th>得分</th>
                  <th>K线位置</th>
                  <th>K线形态</th>
                  <th>F10资金动向</th>
                  <th>说明</th>
                </tr>
              </thead>
              <tbody>
                {moneyFlowRows.map((row, idx) => (
                  <tr key={`money-flow-${idx}`}>
                    <td>{renderThemeLink(row.theme, themeKeyByTheme.get(row.theme), tradeDate)}</td>
                    <td className="recap-stock-highlight">{row.stockName}</td>
                    <td>{row.roleEnhanced}</td>
                    <td>{row.moneyTier}</td>
                    <td>{row.score}</td>
                    <td>{row.klinePosition}</td>
                    <td>{row.klinePattern}</td>
                    <td className="recap-cell-wrap">{renderF10CapitalSummary(row.f10_capital)}</td>
                    <td className="recap-cell-wrap">{row.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="workspace-note">暂无数据，请检查 report.sections.资金行为增强</p>
        )}
      </div>
      )}

      {auctionSection.length > 0 && (
        <div className="workspace-card">
          <span className="metric-label section-title">竞价确认</span>
          <ul className="workspace-list">
            {auctionSection.map((item, idx) => {
              const parsed = splitThemeLine(item);
              return (
                <li key={`auction-${idx}`}>
                  <strong>{parsed.theme || `竞价 ${idx + 1}`}</strong>
                  <p className="workspace-note">{zh(parsed.body)}</p>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {auctionValidationSection.length > 0 && (
        <div className="workspace-card">
          <span className="metric-label section-title">竞价验证回看</span>
          <ul className="workspace-list">
            {auctionValidationSection.map((item, idx) => {
              const parsed = splitThemeLine(item);
              return (
                <li key={`auction-validation-recap-${idx}`}>
                  <strong>{parsed.theme || `验证 ${idx + 1}`}</strong>
                  <p className="workspace-note">{zh(parsed.body)}</p>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {showAuxCard && (
      <div className="workspace-card">
        <span className="metric-label section-title">{reportType === "post_market" ? "龙虎榜" : "失效条件"}</span>
        {reportType === "post_market" ? (
          <>
            {dragonTigerNote && <p className="workspace-note">{zh(dragonTigerNote)}</p>}
            {dragonTigerRows.length > 0 ? (
              <div className="recap-table-wrap">
                <table className="recap-table">
                  <thead>
                    <tr>
                      <th>游资</th>
                      <th>题材</th>
                      <th>股票</th>
                      <th>买卖</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dragonTigerRows.flatMap((row, idx) =>
                      row.items.map((item, subIdx) => (
                        <tr key={`dragon-row-${idx}-${subIdx}`}>
                          <td>{subIdx === 0 ? row.hotMoneyName : ""}</td>
                          <td>{item.theme}</td>
                          <td>{item.stockName}</td>
                          <td>{item.sideNet}</td>
                        </tr>
                      )),
                    )}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="workspace-note">暂无数据，请检查 report.sections.龙虎榜</p>
            )}
          </>
        ) : (
          <ul className="workspace-list">
            {auxSection.map((item, idx) => {
              const parsed = splitThemeLine(item);
              return (
                <li key={`aux-${idx}`}>
                  <strong>{parsed.theme || `条目 ${idx + 1}`}</strong>
                  <p className="workspace-note">{zh(parsed.body)}</p>
                </li>
              );
            })}
          </ul>
        )}
      </div>
      )}
    </>
  );
}
