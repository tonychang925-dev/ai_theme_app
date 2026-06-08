import { useEffect, useMemo, useState } from "react";
import type { NotionPublishResult, RecapViewModelV2 } from "../../lib/api";
import {
  fetchRecapSnapshot, fetchDailyReview, fetchDailyReviewV2, fetchPostMarketJobsStatus, publishRecapToNotion,
  type AbnormalStockReviewV2, type DailyReviewView, type DragonTigerReviewV2, type EngineMarketRegimeReview, type EngineSummary, type MainlineDailyStateReview, type MoneyFlowReviewV2, type PostMarketDailyReviewV2, type StockCapitalReviewV2, type StrongStockReviewV2, type ThemeCapitalReview, type ThemeReviewV2, type WatchlistReviewV2,
  fetchPostMarketReadiness,
  generateDailyReviewV2, generatePostMarketDerivedData, generatePostMarketRecap,
} from "../../lib/api";
import { navigateTo } from "../../lib/navigation";
import recapIcon from "../../assets/intel-icons/当日复盘.png";

// PR-14F: engine-first post_market recap view
import EngineMissingState from "./components/EngineMissingState";
import EnginePostMarketView from "./components/EnginePostMarketView";
import LegacyRecapSections from "./components/LegacyRecapSections";

const DISPLAY_REPLACEMENTS: Array<[string, string]> = [
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

function zh(value: string) {
  let text = String(value ?? "");
  for (const [from, to] of DISPLAY_REPLACEMENTS) {
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

function strongStockBucket(line: string) {
  if (line.includes("龙头 ")) return "leader";
  if (line.includes("龙二 ") || line.includes("卡位 ")) return "runner";
  if (line.includes("补涨 ") || line.includes("套利 ")) return "supplement";
  if (line.includes("淘汰 ")) return "eliminated";
  return "other";
}

type StrongStockRow = {
  role: string;
  stockName: string;
  compositeScore: string;
  purityScore: string;
  leadingScore: string;
  capitalScore: string;
  structureScore: string;
  resilienceScore: string;
  moneyFlow: string;
  klinePosition: string;
  klinePattern: string;
  llmRole: string;
  llmLeaderStatus: string;
  llmConfirmationBasis: string;
  llmReason: string;
  rationale: string;
  raw: string;
};

type RecapGenerationStep = {
  key: string;
  label: string;
  status: "pending" | "running" | "success" | "failed";
  progress: number;
};

const INITIAL_RECAP_GENERATION_STEPS: RecapGenerationStep[] = [
  { key: "readiness", label: "检查盘后数据状态", status: "pending", progress: 0 },
  { key: "derived", label: "生成动态复盘数据", status: "pending", progress: 0 },
  { key: "recap", label: "生成复盘报告", status: "pending", progress: 0 },
  { key: "daily_review_v2", label: "生成 DailyReview V2", status: "pending", progress: 0 },
  { key: "snapshot", label: "载入复盘报告", status: "pending", progress: 0 },
];

function initialRecapGenerationSteps(): RecapGenerationStep[] {
  return INITIAL_RECAP_GENERATION_STEPS.map((step) => ({ ...step }));
}

function initialDerivedGenerationSteps(): RecapGenerationStep[] {
  return INITIAL_RECAP_GENERATION_STEPS
    .filter((step) => step.key === "readiness" || step.key === "derived")
    .map((step) => ({ ...step }));
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

function renderThemeLink(theme: string, subjectKey?: string, tradeDate?: string) {
  if (!subjectKey || subjectKey === "--") return theme;
  const suffix = tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : "";
  return (
    <button type="button" className="recap-theme-link" onClick={() => navigateTo(`/themes/${subjectKey}${suffix}`)}>
      {theme}
    </button>
  );
}

function formatReviewAmount(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "--";
  const abs = Math.abs(value);
  if (abs >= 1e8) return `${(value / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(value / 1e4).toFixed(2)}万`;
  return value.toFixed(0);
}

function buildThemeSummaryRowsFromV2(rows: ThemeReviewV2[]): ThemeSummaryRow[] {
  return rows.map((item) => {
    const tier =
      item.tier === "mainline" || item.final_mainline_alive
        ? "主线"
        : item.tier === "strong_branch"
          ? "强分支"
          : zh(item.tier || "unknown");
    return {
      theme: item.theme_name || "--",
      subjectKey: item.subject_key || "--",
      tier,
      eventScore: item.event_score != null ? item.event_score.toFixed(2) : "--",
      marketScore: item.market_score != null ? item.market_score.toFixed(2) : "--",
      totalInflow: formatReviewAmount(item.total_inflow),
      leaderInflow: formatReviewAmount(item.leader_inflow),
      themeKline: zh(item.theme_kline || "--"),
      cycleStage: zh(item.cycle_stage || item.final_cycle_state || "--"),
      actionAdvice: zh(item.action_advice || "--"),
      conclusion: zh(item.conclusion || "--"),
    };
  });
}

function buildThemeCapitalFlowRowsFromV2(rows: ThemeCapitalReview[]): ThemeCapitalFlowRow[] {
  return [...rows]
    .sort((a, b) => (a.rank_order ?? 9999) - (b.rank_order ?? 9999))
    .map((item) => ({
      theme: item.theme_name || "--",
      subjectKey: item.subject_key || "--",
      tier: zh(item.tier || "unknown"),
      totalInflow: formatReviewAmount(item.total_inflow),
      top3Inflow: formatReviewAmount(item.top3_inflow),
      leaderInflow: formatReviewAmount(item.leader_inflow),
      inflowCount: item.inflow_stock_count != null ? String(item.inflow_stock_count) : "--",
      themeKline: zh(item.theme_kline || "--"),
      stage: zh(item.cycle_stage || "--"),
      action: zh(item.action || "--"),
    }));
}

function buildStrongStockGroupsFromV2(rows: StrongStockReviewV2[]): Array<[string, StrongStockRow[]]> {
  const groups = new Map<string, StrongStockRow[]>();
  for (const item of rows) {
    if (item.role === "reject") continue;
    const theme = item.theme_name || "未分类";
    const row: StrongStockRow = {
      role: zh(item.role_label || item.role || "--"),
      stockName: item.stock_name || item.stock_code || "--",
      compositeScore: item.composite_score != null ? item.composite_score.toFixed(2) : "--",
      purityScore: item.purity_score != null ? item.purity_score.toFixed(2) : "--",
      leadingScore: item.leading_score != null ? item.leading_score.toFixed(2) : "--",
      capitalScore: item.capital_score != null ? item.capital_score.toFixed(2) : zh(item.money_flow.money_flow_tier || "--"),
      structureScore: item.structure_score != null ? item.structure_score.toFixed(2) : zh(item.kline.position_label || "--"),
      resilienceScore: item.resilience_score != null ? item.resilience_score.toFixed(2) : "--",
      moneyFlow: formatReviewAmount(item.money_flow.main_net_inflow),
      klinePosition: zh(item.kline.position_label || "--"),
      klinePattern: zh(item.kline.pattern_labels.join("/") || item.kline.pattern_summary || "--"),
      llmRole: zh(item.llm.judgement || item.money_flow.role_enhanced || "--"),
      llmLeaderStatus: zh(item.candidate_level || "--"),
      llmConfirmationBasis: zh(item.llm.confirmation_basis || "--"),
      llmReason: zh(item.llm.reason || "--"),
      rationale: zh(item.rationale || "--"),
      raw: `${item.role} ${item.stock_name}`,
    };
    const current = groups.get(theme) ?? [];
    current.push(row);
    groups.set(theme, current);
  }
  return Array.from(groups.entries()).filter(([, groupedRows]) => groupedRows.length > 0);
}

function buildThemeSummaryRowsFromMainlineStates(
  rows: MainlineDailyStateReview[],
  engineSummary: EngineSummary | null,
  marketRegime: EngineMarketRegimeReview | null,
): ThemeSummaryRow[] {
  const actionAdvice = zh(engineSummary?.action_bias || marketRegime?.trade_mode || "--");
  const conclusion = zh(engineSummary?.conclusion || marketRegime?.mainline_environment || "--");
  return rows.map((item) => {
    const score = item.mainline_strength_score;
    const fade = item.fade_risk_score;
    return {
      theme: item.mainline_name || "--",
      subjectKey: item.canonical_subject_key || item.mainline_id || "--",
      tier: "主线",
      eventScore: score != null ? score.toFixed(2) : "--",
      marketScore: fade != null ? fade.toFixed(2) : "--",
      totalInflow: "--",
      leaderInflow: "--",
      themeKline: zh(item.lifecycle_state || "--"),
      cycleStage: zh(item.lifecycle_state || "--"),
      actionAdvice,
      conclusion: zh(item.conclusion || conclusion || "--"),
    };
  });
}

function buildStrongStockGroupsFromPool(
  rows: Record<string, unknown>[],
): Array<[string, StrongStockRow[]]> {
  const groups = new Map<string, StrongStockRow[]>();
  for (const raw of rows) {
    if (!raw || typeof raw !== "object") continue;
    const row = raw as Record<string, unknown>;
    const theme = String(row.mainline_name || row.theme_name || row.subject_key || "其他").trim() || "其他";
    const score = row.watch_score != null ? Number(row.watch_score) : null;
    const supportScore = row.support_score != null ? Number(row.support_score) : null;
    const mainlineScore = row.mainline_strength_score != null ? Number(row.mainline_strength_score) : null;
    const watchPriority = row.watch_priority != null ? Number(row.watch_priority) : null;
    const labels = Array.isArray(row.labels) ? row.labels.map((item) => zh(String(item || "").trim())).filter(Boolean) : [];
    const evidenceText = row.evidence && typeof row.evidence === "object" ? JSON.stringify(row.evidence, null, 0) : "";
    const diagnostics = row.diagnostics && typeof row.diagnostics === "object" ? (row.diagnostics as Record<string, unknown>) : {};
    const fallbackReason = [
      String(row.watch_status || "").trim(),
      String(row.pool_entry_type || "").trim(),
      String(row.source_tag || "").trim(),
      String(diagnostics.source || "").trim(),
    ].filter(Boolean).join("；") || "--";

    const mapped: StrongStockRow = {
      role: zh(String(row.relay_role || row.pool_entry_type || row.watch_status || "--")),
      stockName: String(row.stock_name || row.stock_id || "--"),
      compositeScore: score != null && Number.isFinite(score) ? score.toFixed(2) : "--",
      purityScore: supportScore != null && Number.isFinite(supportScore) ? supportScore.toFixed(2) : "--",
      leadingScore: mainlineScore != null && Number.isFinite(mainlineScore) ? mainlineScore.toFixed(2) : "--",
      capitalScore: watchPriority != null && Number.isFinite(watchPriority) ? watchPriority.toFixed(2) : "--",
      structureScore: zh(String(row.support_type || row.cycle_state || "--")),
      resilienceScore: supportScore != null && Number.isFinite(supportScore) ? supportScore.toFixed(2) : "--",
      moneyFlow: row.main_net_inflow != null && Number.isFinite(Number(row.main_net_inflow))
        ? formatReviewAmount(Number(row.main_net_inflow))
        : "--",
      klinePosition: zh(String(row.support_type || row.cycle_state || "--")),
      klinePattern: zh(labels.join("/") || String(row.watch_status || row.pool_entry_type || "--")),
      llmRole: zh(String(row.relay_role || row.watch_status || "--")),
      llmLeaderStatus: zh(String(row.pool_entry_type || "--")),
      llmConfirmationBasis: zh(String(row.source_tag || diagnostics.source || "--")),
      llmReason: zh(evidenceText || fallbackReason),
      rationale: zh(fallbackReason),
      raw: `${String(row.stock_id || "")} ${String(row.stock_name || "")}`.trim(),
    };
    const current = groups.get(theme) ?? [];
    current.push(mapped);
    groups.set(theme, current);
  }
  return Array.from(groups.entries()).filter(([, groupedRows]) => groupedRows.length > 0);
}

function buildLegacyMarketEnvironmentSectionFromEngine(
  engineSummary: EngineSummary | null,
  marketRegime: EngineMarketRegimeReview | null,
): string[] {
  if (!engineSummary && !marketRegime) return [];
  const allowTradeText = engineSummary?.allow_trade ? "可交易" : "不交易";
  const positionLimit = typeof engineSummary?.position_limit === "number" && Number.isFinite(engineSummary.position_limit)
    ? `${Math.round((engineSummary.position_limit || 0) * 100)}%`
    : "--";
  const riskNotes = [...(engineSummary?.risk_notes ?? []), ...(marketRegime?.no_trade_reasons ?? [])]
    .map((item) => zh(String(item || "").trim()))
    .filter((item) => item && item !== "--");

  return [
    `市场偏向 ${zh(String(marketRegime?.mainline_environment || engineSummary?.action_bias || "--"))}；动作 ${zh(String(engineSummary?.trade_mode || marketRegime?.trade_mode || "--"))}；环境总分 --`,
    `短线情绪 ${zh(String(marketRegime?.short_term_sentiment || "--"))}；交易权限 ${allowTradeText}；仓位上限 ${positionLimit}`,
    `风险提示 ${riskNotes.length > 0 ? riskNotes.slice(0, 3).join("；") : zh(String(engineSummary?.no_trade_blocking_rule || "--"))}`,
  ];
}

function buildLegacyHighlightsFromEngine(
  engineSummary: EngineSummary | null,
  marketRegime: EngineMarketRegimeReview | null,
): string[] {
  if (!engineSummary && !marketRegime) return [];
  const riskNotes = [...(engineSummary?.risk_notes ?? []), ...(marketRegime?.no_trade_reasons ?? [])]
    .map((item) => zh(String(item || "").trim()))
    .filter((item) => item && item !== "--");
  const actionBias = zh(String(engineSummary?.action_bias || marketRegime?.mainline_environment || "--"));
  const tradeMode = zh(String(engineSummary?.trade_mode || marketRegime?.trade_mode || "--"));
  const positionLimit = typeof engineSummary?.position_limit === "number" && Number.isFinite(engineSummary.position_limit)
    ? `${Math.round((engineSummary.position_limit || 0) * 100)}%`
    : "--";
  const conclusion = zh(String(engineSummary?.conclusion || marketRegime?.short_term_sentiment || "--"));
  return [
    `交易权限：${engineSummary?.allow_trade ? "可交易" : "不交易"}；模式 ${tradeMode}；仓位 ${positionLimit}`,
    `市场定性：${actionBias}；${zh(String(marketRegime?.short_term_sentiment || "--"))}；${zh(String(marketRegime?.broad_market_regime || "--"))}`,
    `结论：${conclusion}`,
    `风险提示：${riskNotes.length > 0 ? riskNotes.slice(0, 3).join("；") : zh(String(engineSummary?.no_trade_blocking_rule || "--"))}`,
  ];
}

function isMetadataOnlyHighlights(items: string[]): boolean {
  const normalized = items.map((item) => String(item || "").trim()).filter(Boolean);
  if (normalized.length === 0) return true;
  return normalized.every((item) => item.startsWith("snapshot_version:") || item.startsWith("strong_watch_history_count:"));
}

function buildWatchlistRowsFromV2(rows: WatchlistReviewV2[]): WatchlistDisplayRow[] {
  const mapped = [...rows]
    .sort((a, b) => {
      const themeCompare = (a.theme_name || "").localeCompare(b.theme_name || "", "zh-CN");
      if (themeCompare !== 0) return themeCompare;
      const categoryCompare = (a.category || "").localeCompare(b.category || "", "zh-CN");
      if (categoryCompare !== 0) return categoryCompare;
      const priorityCompare = (a.priority ?? 9999) - (b.priority ?? 9999);
      if (priorityCompare !== 0) return priorityCompare;
      return (a.stock_name || "").localeCompare(b.stock_name || "", "zh-CN");
    })
    .map((item): WatchlistRow => ({
      category: item.category || "--",
      theme: item.theme_name || "--",
      subjectKey: item.subject_key || "--",
      stockName: item.stock_name || item.stock_code || "--",
      role: zh(item.role_label || "--"),
      stage: zh(item.stage || "--"),
      action: zh(item.action || "--"),
      volumeRatio: item.volume_ratio != null ? item.volume_ratio.toFixed(2) : "--",
      pattern: zh(item.pattern || "--"),
      flag: zh(item.flags?.join("/") || "--"),
      dragonDays: item.dragon_tiger_days != null ? String(item.dragon_tiger_days) : "--",
      catalyst: zh(item.catalyst || item.reason || "--"),
      labels: zh(item.abnormal_labels?.join("/") || "--"),
      buyCondition: Array.isArray(item.buy_condition) ? item.buy_condition.join(" / ") : undefined,
      invalidCondition: Array.isArray(item.invalid_condition) ? item.invalid_condition.join(" / ") : undefined,
      riskLevel: item.risk_level ?? undefined,
      suggestedPosition: typeof item.suggested_position === "number" ? `${Math.round(item.suggested_position * 100)}%` : undefined,
    }));

  let lastTheme = "";
  return mapped.map((row): WatchlistDisplayRow => {
    const showTheme = row.theme !== lastTheme;
    lastTheme = row.theme;
    return { ...row, showTheme };
  });
}

function buildStockCapitalFlowRowsFromV2(rows: StockCapitalReviewV2[]): StockCapitalFlowRow[] {
  return [...rows]
    .sort((a, b) => {
      const rankA = a.rank_overall ?? a.rank_in_theme ?? 9999;
      const rankB = b.rank_overall ?? b.rank_in_theme ?? 9999;
      if (rankA !== rankB) return rankA - rankB;
      return (b.main_net_inflow ?? 0) - (a.main_net_inflow ?? 0);
    })
    .map((item) => ({
      stockName: item.stock_name || item.stock_code || "--",
      theme: item.theme_name || "--",
      mainInflow: formatReviewAmount(item.main_net_inflow),
      rankOrder: item.rank_in_theme != null ? String(item.rank_in_theme) : item.rank_overall != null ? String(item.rank_overall) : "--",
      pctChg: item.pct_chg != null ? `${item.pct_chg.toFixed(2)}%` : item.turnover_rate != null ? `换手${item.turnover_rate.toFixed(2)}%` : "--",
      isLeader: item.is_leader ? "是" : "否",
      flag: zh(item.flags?.join("/") || "--"),
    }));
}

function buildAbnormalRowsFromV2(rows: AbnormalStockReviewV2[]): AbnormalSignalRow[] {
  return rows.map((item) => {
    const capitalParts = [
      item.capital.main_net_inflow != null ? `主力净流入 ${formatReviewAmount(item.capital.main_net_inflow)}` : "",
      item.capital.inflow_rank != null ? `题材内净流入排名 ${item.capital.inflow_rank}` : "",
      item.capital.money_flow_tier ? `资金分层 ${zh(item.capital.money_flow_tier)}` : "",
    ].filter(Boolean);
    return {
      theme: item.theme_name || "--",
      stockName: item.stock_name || item.stock_code || "--",
      score: item.abnormal_score != null ? item.abnormal_score.toFixed(2) : "--",
      turnoverRate: item.turnover_rate != null ? `${item.turnover_rate.toFixed(2)}%` : "--",
      volumeRatio: item.volume_ratio != null ? item.volume_ratio.toFixed(2) : "--",
      volumeVsMa50: item.volume_vs_ma50 != null ? item.volume_vs_ma50.toFixed(2) : "--",
      capital: capitalParts.join("；") || "--",
      labels: zh(item.labels?.join("/") || "--"),
      conclusion: zh(item.conclusion || "--"),
    };
  });
}

function buildMoneyFlowRowsFromV2(rows: MoneyFlowReviewV2[]): MoneyFlowRow[] {
  return rows.map((item) => {
    const noteParts = [
      item.conclusion,
      item.institution_signal ? `机构 ${zh(item.institution_signal)}` : "",
      item.hot_money_signal ? `游资 ${zh(item.hot_money_signal)}` : "",
      item.dragon_tiger_signal ? `龙虎榜 ${zh(item.dragon_tiger_signal)}` : "",
    ].filter(Boolean);
    return {
      theme: item.theme_name || "--",
      stockName: item.stock_name || item.stock_code || "--",
      roleEnhanced: zh(item.role_enhanced || item.institution_signal || item.hot_money_signal || "--"),
      moneyTier: zh(item.money_flow_tier || "--"),
      score: item.main_net_inflow != null ? formatReviewAmount(item.main_net_inflow) : "--",
      klinePosition: zh(item.kline?.position_label || "--"),
      klinePattern: zh(item.kline?.pattern_labels?.join("/") || item.kline?.pattern_summary || "--"),
      note: zh(noteParts.join("；") || "--"),
    };
  });
}

function isV2ModuleReady(
  dailyReviewV2: PostMarketDailyReviewV2 | null,
  moduleKey: keyof PostMarketDailyReviewV2["diagnostics"]["module_coverage"],
  rows: unknown[] | undefined,
): boolean {
  const coverage = dailyReviewV2?.diagnostics?.module_coverage?.[moduleKey];
  return Boolean(
    dailyReviewV2 &&
    rows &&
    rows.length > 0 &&
    coverage?.status === "ready" &&
    coverage?.source === "structured" &&
    (coverage.missing_fields?.length ?? 0) === 0,
  );
}

function renderDecisionTags(row: StrongStockRow) {
  const tags = [
    row.llmRole !== "--" ? { text: row.llmRole, cls: "is-role" } : null,
    row.llmLeaderStatus !== "--" ? { text: row.llmLeaderStatus, cls: "is-status" } : null,
    row.llmConfirmationBasis !== "--" ? { text: row.llmConfirmationBasis, cls: "is-basis" } : null,
  ].filter(Boolean) as Array<{ text: string; cls: string }>;

  if (tags.length === 0) {
    return <span className="workspace-note">--</span>;
  }

  return (
    <div className="recap-tag-stack">
      {tags.map((tag, idx) => (
        <span key={`${tag.text}-${idx}`} className={`recap-chip ${tag.cls}`}>
          {tag.text}
        </span>
      ))}
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

type ThemeSummaryRow = {
  theme: string;
  subjectKey: string;
  tier: string;
  eventScore: string;
  marketScore: string;
  totalInflow: string;
  leaderInflow: string;
  themeKline: string;
  cycleStage: string;
  actionAdvice: string;
  conclusion: string;
};

type MoneyFlowRow = {
  theme: string;
  stockName: string;
  roleEnhanced: string;
  moneyTier: string;
  score: string;
  klinePosition: string;
  klinePattern: string;
  note: string;
};

type DragonTigerRow = {
  hotMoneyName: string;
  items: Array<{
    theme: string;
    stockName: string;
    sideNet: string;
  }>;
};

type AbnormalSignalRow = {
  theme: string;
  stockName: string;
  score: string;
  turnoverRate: string;
  volumeRatio: string;
  volumeVsMa50: string;
  capital: string;
  labels: string;
  conclusion: string;
};

type ThemeCapitalFlowRow = {
  theme: string;
  subjectKey: string;
  tier: string;
  totalInflow: string;
  top3Inflow: string;
  leaderInflow: string;
  inflowCount: string;
  themeKline: string;
  stage: string;
  action: string;
};

type StockCapitalFlowRow = {
  stockName: string;
  theme: string;
  mainInflow: string;
  rankOrder: string;
  pctChg: string;
  isLeader: string;
  flag: string;
};

type WatchlistRow = {
  category: string;
  theme: string;
  subjectKey: string;
  stockName: string;
  role: string;
  stage: string;
  action: string;
  volumeRatio: string;
  pattern: string;
  flag: string;
  dragonDays: string;
  catalyst: string;
  labels: string;
  buyCondition?: string;
  invalidCondition?: string;
  riskLevel?: string;
  suggestedPosition?: string;
};

type WatchlistDisplayRow = WatchlistRow & {
  showTheme: boolean;
};

function parseStrongStockBody(body: string): StrongStockRow {
  const segments = body.split("；").map((item) => item.trim()).filter(Boolean);
  const first = segments[0] ?? "";
  const firstParts = first.split(/\s+/);
  const role = firstParts[0] ?? "--";
  const stockName = firstParts.slice(1).join(" ") || "--";

  let compositeScore = "--";
  let purityScore = "--";
  let leadingScore = "--";
  let capitalScore = "--";
  let structureScore = "--";
  let resilienceScore = "--";
  let moneyFlow = "--";
  let klinePosition = "--";
  let klinePattern = "--";
  let llmRole = "--";
  let llmLeaderStatus = "--";
  let llmConfirmationBasis = "--";
  let llmReason = "--";
  let rationale = "--";
  const notes: string[] = [];

  for (const segment of segments.slice(1)) {
    if (segment.startsWith("综合分 ")) {
      compositeScore = segment.replace("综合分 ", "").trim();
      continue;
    }
    if (segment.startsWith("正宗性 ")) {
      purityScore = segment.replace("正宗性 ", "").trim();
      continue;
    }
    if (segment.startsWith("领涨性 ")) {
      leadingScore = segment.replace("领涨性 ", "").trim();
      continue;
    }
    if (segment.startsWith("资金量能 ")) {
      capitalScore = segment.replace("资金量能 ", "").trim();
      continue;
    }
    if (segment.startsWith("结构位置 ")) {
      structureScore = segment.replace("结构位置 ", "").trim();
      continue;
    }
    if (segment.startsWith("抗跌承接 ")) {
      resilienceScore = segment.replace("抗跌承接 ", "").trim();
      continue;
    }
    if (segment.startsWith("资金 ")) {
      moneyFlow = segment.replace("资金 ", "").trim();
      continue;
    }
    if (segment.startsWith("K线位置 ")) {
      klinePosition = segment.replace("K线位置 ", "").trim();
      continue;
    }
    if (segment.startsWith("K线形态 ")) {
      klinePattern = segment.replace("K线形态 ", "").trim();
      continue;
    }
    if (segment.startsWith("LLM裁决角色 ")) {
      llmRole = segment.replace("LLM裁决角色 ", "").trim();
      continue;
    }
    if (segment.startsWith("LLM确认状态 ")) {
      llmLeaderStatus = segment.replace("LLM确认状态 ", "").trim();
      continue;
    }
    if (segment.startsWith("确认依据 ")) {
      llmConfirmationBasis = segment.replace("确认依据 ", "").trim();
      continue;
    }
    if (segment.startsWith("LLM理由 ")) {
      llmReason = segment.replace("LLM理由 ", "").trim();
      continue;
    }
    if (segment.startsWith("评分依据 ")) {
      rationale = segment.replace("评分依据 ", "").trim();
      continue;
    }
    notes.push(segment);
  }

  return {
    role,
    stockName,
    compositeScore,
    purityScore,
    leadingScore,
    capitalScore,
    structureScore,
    resilienceScore,
    moneyFlow: zh(moneyFlow),
    klinePosition: zh(klinePosition),
    klinePattern: zh(klinePattern),
    llmRole: zh(llmRole),
    llmLeaderStatus: zh(llmLeaderStatus),
    llmConfirmationBasis: zh(llmConfirmationBasis),
    llmReason: zh(llmReason),
    rationale: zh([rationale, ...notes].filter((item) => item && item !== "--").join("；") || "--"),
    raw: body,
  };
}

function parseWatchlistLine(value: string): WatchlistRow {
  const raw = String(value || "");
  const [category, bodyRaw = ""] = raw.split("：", 2);
  const body = bodyRaw.trim();
  const parts = body.split("｜").map((item) => item.trim()).filter(Boolean);
  const theme = parts[0] || "--";
  const stock = parts[1] || "--";
  const detailParts = parts.slice(2);

  const findValue = (prefix: string) =>
    detailParts.find((item) => item.startsWith(prefix))?.slice(prefix.length).trim() || "--";

  return {
    category: category || "--",
    theme,
    subjectKey: findValue("subject_key "),
    stockName: stock,
    role: findValue("角色 "),
    stage: findValue("阶段 "),
    action: findValue("动作 "),
    volumeRatio: findValue("量比 "),
    pattern: findValue("形态 "),
    flag: findValue("flag "),
    dragonDays: findValue("近7日龙虎榜 "),
    catalyst: findValue("催化 "),
    labels: findValue("异动 "),
  };
}

function parseThemeCapitalFlowRow(value: string): ThemeCapitalFlowRow {
  const parsed = splitThemeLine(value);
  const parts = parsed.body.split("；").map((item) => item.trim()).filter(Boolean);
  const findValue = (prefix: string) => parts.find((item) => item.startsWith(prefix))?.slice(prefix.length).trim() || "--";
  return {
    theme: parsed.theme || "--",
    subjectKey: findValue("subject_key "),
    tier: zh(findValue("层级 ")),
    totalInflow: findValue("总净流入 "),
    top3Inflow: findValue("前3净流入 "),
    leaderInflow: findValue("龙头净流入 "),
    inflowCount: findValue("流入股 "),
    themeKline: zh(findValue("题材K线 ")),
    stage: findValue("阶段 "),
    action: findValue("动作 "),
  };
}

function parseStockCapitalFlowRow(value: string): StockCapitalFlowRow {
  const parsed = splitThemeLine(value);
  const parts = parsed.body.split("；").map((item) => item.trim()).filter(Boolean);
  const findValue = (prefix: string) => parts.find((item) => item.startsWith(prefix))?.slice(prefix.length).trim() || "--";
  return {
    stockName: parsed.theme || "--",
    theme: parts[0] || "--",
    mainInflow: findValue("主力净流入 "),
    rankOrder: findValue("题材内排名 "),
    pctChg: findValue("涨幅 "),
    isLeader: findValue("龙头 "),
    flag: findValue("flag "),
  };
}

function parseThemeSummary(theme: string, body: string, cycleAction: string): ThemeSummaryRow {
  const segments = body.split("；").map((item) => item.trim()).filter(Boolean);
  const cycleSegments = cycleAction.split("；").map((item) => item.trim()).filter(Boolean);
  const findValue = (prefix: string) => segments.find((item) => item.startsWith(prefix))?.slice(prefix.length).trim() || "--";
  const rawTier = findValue("层级 ");
  const mainlineAlive = findValue("主线存活 ");
  const state = findValue("状态 ");
  const mainlineStrength = findValue("主线强度 ");
  const fadeRisk = findValue("退潮风险 ");
  const stageRaw = (cycleSegments[0] ?? "").replace("阶段 ", "").trim();
  const stageMap: Record<string, string> = {
    start: "启动",
    fermentation: "发酵",
    divergence: "分歧",
    rebound: "弱转强",
    climax: "高潮",
    fade: "退潮",
  };
  const tier =
    rawTier === "main"
      ? "主线"
      : rawTier === "strong_branch"
        ? "强分支"
        : mainlineAlive === "是"
          ? "主线"
          : mainlineAlive === "否"
            ? "强分支"
            : zh(rawTier);
  const cycleStage = zh((stageMap[stageRaw] ?? stageRaw) || (state !== "--" ? state : "--"));
  return {
    theme,
    subjectKey: findValue("subject_key "),
    tier,
    eventScore: findValue("事件 ") !== "--" ? findValue("事件 ") : mainlineStrength,
    marketScore: findValue("市场 ") !== "--" ? findValue("市场 ") : fadeRisk,
    totalInflow: findValue("总净流入 "),
    leaderInflow: findValue("龙头净流入 "),
    themeKline: zh(findValue("题材K线 ")),
    cycleStage,
    actionAdvice: zh((cycleSegments[1] ?? "").replace("动作 ", "").trim() || "--"),
    conclusion: zh((cycleSegments[2] ?? "").replace("结论 ", "").trim() || "--"),
  };
}

function parseMoneyFlowRow(theme: string, body: string): MoneyFlowRow {
  const segments = body.split("；").map((item) => item.trim()).filter(Boolean);
  return {
    theme,
    stockName: segments[0] ?? "--",
    roleEnhanced: zh(segments[1] ?? "--"),
    moneyTier: zh((segments[2] ?? "").replace("资金分层 ", "").trim() || "--"),
    score: (segments[3] ?? "").replace("得分 ", "").trim() || "--",
    klinePosition: zh((segments.find((item) => item.startsWith("K线位置 ")) ?? "").replace("K线位置 ", "").trim() || "--"),
    klinePattern: zh((segments.find((item) => item.startsWith("K线形态 ")) ?? "").replace("K线形态 ", "").trim() || "--"),
    note: zh(segments.filter((item) => !item.startsWith("K线位置 ") && !item.startsWith("K线形态 ")).slice(4).join("；") || "--"),
  };
}

function parseDragonTigerRow(hotMoneyName: string, body: string): DragonTigerRow {
  const items = body
    .split("；")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((item) => {
      const parts = item.split("/").map((part) => zh(part.trim())).filter(Boolean);
      return {
        theme: parts[0] ?? "--",
        stockName: parts[1] ?? "--",
        sideNet: parts[2] ?? "--",
      };
    });
  return {
    hotMoneyName,
    items: items.length > 0 ? items : [{ theme: "--", stockName: "--", sideNet: "--" }],
  };
}

function parseDragonTigerLegacyRow(hotMoneyName: string, body: string): DragonTigerRow {
  return {
    hotMoneyName,
    items: [{ theme: "--", stockName: zh(body || "--"), sideNet: "--" }],
  };
}

function parseAbnormalSignalRow(theme: string, body: string): AbnormalSignalRow {
  const segments = body.split("；").map((item) => item.trim()).filter(Boolean);
  const findValue = (prefix: string) =>
    segments.find((item) => item.startsWith(prefix))?.slice(prefix.length).trim() || "--";
  const stockName =
    segments.find(
      (item) =>
        !item.startsWith("异动分 ") &&
        !item.startsWith("换手率 ") &&
        !item.startsWith("量比 ") &&
        !item.startsWith("成交量/50日均量 ") &&
        !item.startsWith("资金 ") &&
        !item.startsWith("标签 ") &&
        !item.startsWith("结论 "),
    ) || "--";
  return {
    theme,
    stockName,
    score: findValue("异动分 "),
    turnoverRate: findValue("换手率 "),
    volumeRatio: findValue("量比 "),
    volumeVsMa50: findValue("成交量/50日均量 "),
    capital: zh(findValue("资金 ")),
    labels: zh(findValue("标签 ")),
    conclusion: zh(findValue("结论 ")),
  };
}

function numericPart(value: string) {
  const matched = String(value ?? "").match(/-?\d+(\.\d+)?/);
  return matched ? Number(matched[0]) : -Infinity;
}

function buildThemeCycleMap(lines: string[]) {
  const result = new Map<string, string>();
  for (const line of lines) {
    const parsed = splitThemeLine(line);
    if (parsed.theme) result.set(parsed.theme, parsed.body);
  }
  return result;
}

function buildThemeTextMap(lines: string[]) {
  const result = new Map<string, string>();
  for (const line of lines) {
    const parsed = splitThemeLine(line);
    if (parsed.theme) result.set(parsed.theme, parsed.body);
  }
  return result;
}

function splitSummaryLine(value: string) {
  const text = String(value ?? "").trim();
  const match = text.match(/^([^：:]{2,16})[：:]\s*(.*)$/);
  if (!match) return { label: "", body: text };
  return { label: match[1], body: match[2] || text };
}

function sectionMap(payload: RecapViewModelV2 | null) {
  const map = new Map<string, string[]>();
  for (const section of payload?.sections ?? []) {
    map.set(section.heading, section.items);
  }
  return map;
}

type PostMarketDataMode = "sections_first" | "daily_review_v2_first";
type RecapViewMode = "engine" | "legacy";

function normalizePostMarketDataMode(value: string | null | undefined): PostMarketDataMode | null {
  if (value === "daily_review_v2" || value === "daily_review_v2_first") {
    return "daily_review_v2_first";
  }
  if (value === "sections_first") {
    return "sections_first";
  }
  return null;
}

function resolvePostMarketDataMode(params: URLSearchParams): PostMarketDataMode {
  if (window.location.search.includes("data_mode=sections_first")) {
    return "sections_first";
  }
  const urlMode = normalizePostMarketDataMode(params.get("data_mode"));
  if (urlMode) {
    return urlMode;
  }
  return normalizePostMarketDataMode(import.meta.env.VITE_POST_MARKET_DEFAULT_DATA_MODE) ?? "daily_review_v2_first";
}

function resolveRecapViewMode(params: URLSearchParams): RecapViewMode {
  if (params.get("view") === "legacy" || params.get("legacy_sections") === "1") {
    return "legacy";
  }
  return "engine";
}

function isEngineReportReady(dailyReviewV2: PostMarketDailyReviewV2 | null) {
  return Boolean(
    dailyReviewV2?.engine_summary &&
    dailyReviewV2?.market_regime_review &&
    Array.isArray(dailyReviewV2?.mainline_daily_states) &&
    (dailyReviewV2?.mainline_daily_states?.length ?? 0) > 0 &&
    dailyReviewV2?.post_market_decision_v2,
  );
}

function buildRecapSearchParams({
  tradeDate,
  reportType,
  dataMode,
  viewMode,
}: {
  tradeDate: string;
  reportType: "pre_market" | "post_market";
  dataMode?: PostMarketDataMode | null;
  viewMode?: RecapViewMode | null;
}) {
  const query = new URLSearchParams({ date: tradeDate, report_type: reportType });
  if (reportType === "post_market" && dataMode) {
    query.set("data_mode", dataMode === "daily_review_v2_first" ? "daily_review_v2" : "sections_first");
  }
  if (viewMode === "legacy") {
    query.set("view", "legacy");
  }
  return query;
}

function todayString() {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

function isMissingPostMarketSnapshotError(message: string) {
  return message.includes("post-market snapshot is unavailable or unmappable")
    || message.includes("request timeout after");
}

function hasRunningPostMarketJob(status?: { summary?: { has_running?: boolean }; items?: Array<{ status?: string }> } | null) {
  return Boolean(status?.summary?.has_running) || Boolean(status?.items?.some((item) => item.status === "running"));
}

export function RecapPage() {
  const today = useMemo(() => todayString(), []);
  const initialParams = new URLSearchParams(window.location.search);
  const initialType = window.location.search.includes("report_type=pre_market") ? "pre_market" : "post_market";
  const initialDate = initialParams.get("date") ?? today;
  const dataMode = resolvePostMarketDataMode(initialParams);
  const viewMode = resolveRecapViewMode(initialParams);
  const effectiveDataMode = viewMode === "legacy" ? "sections_first" : dataMode;
  const dailyReviewV2PreviewEnabled = effectiveDataMode === "daily_review_v2_first";

  const [tradeDate, setTradeDate] = useState(initialDate);
  const [reportType, setReportType] = useState<"pre_market" | "post_market">(initialType);
  const [abnormalSortKey, setAbnormalSortKey] = useState<"score" | "turnoverRate" | "volumeRatio" | "volumeVsMa50">("score");
  const [abnormalSortDir, setAbnormalSortDir] = useState<"desc" | "asc">("desc");
  const [payload, setPayload] = useState<RecapViewModelV2 | null>(null);
  const [dailyReview, setDailyReview] = useState<DailyReviewView | null>(null);
  const [dailyReviewV2, setDailyReviewV2] = useState<PostMarketDailyReviewV2 | null>(null);
  const [derivedDataBusy, setDerivedDataBusy] = useState(false);
  const [recapBusy, setRecapBusy] = useState(false);
  const [generationSteps, setGenerationSteps] = useState<RecapGenerationStep[]>([]);
  const effectiveReportType = payload?.report_type ?? reportType;
  const rawHighlights = payload?.highlights ?? [];
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [publishResult, setPublishResult] = useState<NotionPublishResult | null>(null);
  const sections = useMemo(() => sectionMap(payload), [payload]);
  const isGeneratingRecap = derivedDataBusy || recapBusy;
  const recapGenerationProgress = useMemo(() => {
    if (!generationSteps.length) return 0;
    const total = generationSteps.reduce((sum, step) => sum + Math.max(0, Math.min(100, step.progress)), 0);
    return Math.round(total / generationSteps.length);
  }, [generationSteps]);
  const recapGenerationCurrentStep = useMemo(() => {
    const failed = generationSteps.find((step) => step.status === "failed");
    if (failed) return failed;
    return generationSteps.find((step) => step.status === "running")
      ?? generationSteps.find((step) => step.status === "pending")
      ?? generationSteps[generationSteps.length - 1];
  }, [generationSteps]);
  const isPostMarket = effectiveReportType === "post_market";
  const legacyViewEnabled = isPostMarket && viewMode === "legacy";
  const engineReportReady = isEngineReportReady(dailyReviewV2);
  const engineSummary = dailyReviewV2?.engine_summary ?? null;
  const marketRegimeReview = dailyReviewV2?.market_regime_review ?? null;
  const mainlineDailyStates = dailyReviewV2?.mainline_daily_states ?? [];
  const postMarketDecisionV2 = dailyReviewV2?.post_market_decision_v2 ?? null;
  const highlights = useMemo(() => {
    if (!isMetadataOnlyHighlights(rawHighlights)) return rawHighlights;
    if (dailyReviewV2PreviewEnabled) {
      const fallback = buildLegacyHighlightsFromEngine(engineSummary, marketRegimeReview);
      if (fallback.length > 0) return fallback;
    }
    return rawHighlights;
  }, [dailyReviewV2PreviewEnabled, engineSummary, marketRegimeReview, rawHighlights]);
  const marketEnvironmentSection = useMemo(() => {
    const legacySection = sections.get("大盘环境总结") ?? [];
    if (legacySection.length > 0) return legacySection;
    if (dailyReviewV2PreviewEnabled) {
      const fallback = buildLegacyMarketEnvironmentSectionFromEngine(engineSummary, marketRegimeReview);
      if (fallback.length > 0) return fallback;
    }
    return legacySection;
  }, [dailyReviewV2PreviewEnabled, engineSummary, marketRegimeReview, sections]);
  const themeEnvironmentSection = sections.get("板块环境总结") ?? [];
  const themeSection = sections.get("主线与支线") ?? sections.get("可做主线与支线") ?? [];
  const themeCapitalFlowSection = sections.get("主线资金流入前10") ?? sections.get("题材资金流入前10") ?? [];
  const cycleSection = sections.get("周期与动作") ?? [];
  const strongStockSection = sections.get("强势股分层") ?? sections.get("盘前重点盯盘个股") ?? [];
  const watchlistSection = sections.get("次日观察清单") ?? [];
  const stockCapitalFlowSection = sections.get("主线股票资金流入前20") ?? sections.get("股票资金流入前20") ?? [];
  const moneySection = sections.get("资金行为增强") ?? [];
  const abnormalSection = sections.get("当日异动股与资金行为") ?? [];
  const auctionSection = sections.get("竞价确认") ?? [];
  const auctionValidationSection = sections.get("竞价验证回看") ?? [];
  const auxSection = sections.get("龙虎榜") ?? sections.get("龙虎榜与来源链") ?? sections.get("失效条件") ?? [];
  const cycleByTheme = useMemo(() => buildThemeCycleMap(cycleSection), [cycleSection]);
  const strongStockGroups = useMemo(() => {
    const v2Rows = dailyReviewV2?.strong_stock_reviews;
    if (dailyReviewV2PreviewEnabled && isV2ModuleReady(dailyReviewV2, "strong_stock_reviews", v2Rows)) {
      return buildStrongStockGroupsFromV2(v2Rows ?? []);
    }
    const groups = new Map<string, StrongStockRow[]>();
    for (const item of strongStockSection) {
      const parsed = splitThemeLine(item);
      const key = parsed.theme || "未分类";
      const row = parseStrongStockBody(parsed.body);
      if (row.role === "淘汰") continue;
      const current = groups.get(key) ?? [];
      current.push(row);
      groups.set(key, current);
    }
    if (groups.size > 0) {
      return Array.from(groups.entries()).filter(([, rows]) => rows.length > 0);
    }
    const poolRows = postMarketDecisionV2?.strong_stock_pool_reviews;
    if (
      dailyReviewV2PreviewEnabled &&
      isV2ModuleReady(dailyReviewV2, "post_market_decision_v2", poolRows)
    ) {
      return buildStrongStockGroupsFromPool((poolRows ?? []) as Record<string, unknown>[]);
    }
    return Array.from(groups.entries()).filter(([, rows]) => rows.length > 0);
  }, [dailyReviewV2PreviewEnabled, dailyReviewV2, postMarketDecisionV2, strongStockSection]);
  const watchlistRows = useMemo(() => {
    const v2Rows = dailyReviewV2?.watchlist_reviews;
    if (dailyReviewV2PreviewEnabled && isV2ModuleReady(dailyReviewV2, "watchlist_reviews", v2Rows)) {
      return buildWatchlistRowsFromV2(v2Rows ?? []);
    }
    const rows = watchlistSection.map((item) => parseWatchlistLine(item));
    rows.sort((a, b) => {
      const themeCompare = a.theme.localeCompare(b.theme, "zh-CN");
      if (themeCompare !== 0) return themeCompare;
      const categoryCompare = a.category.localeCompare(b.category, "zh-CN");
      if (categoryCompare !== 0) return categoryCompare;
      return a.stockName.localeCompare(b.stockName, "zh-CN");
    });
    let lastTheme = "";
    return rows.map((row): WatchlistDisplayRow => {
      const showTheme = row.theme !== lastTheme;
      lastTheme = row.theme;
      return {
        ...row,
        showTheme,
      };
    });
  }, [dailyReviewV2PreviewEnabled, dailyReviewV2, watchlistSection]);
  const themeSummaryRows = useMemo(
    () => {
      const v2Rows = dailyReviewV2?.theme_reviews;
      if (dailyReviewV2PreviewEnabled && isV2ModuleReady(dailyReviewV2, "theme_reviews", v2Rows)) {
        return buildThemeSummaryRowsFromV2(v2Rows ?? []);
      }
      const legacyRows = themeSection.map((item) => {
        const parsed = splitThemeLine(item);
        return parseThemeSummary(
          parsed.theme || "未分类",
          parsed.body,
          cycleByTheme.get(parsed.theme) ?? "",
        );
      });
      if (legacyRows.length > 0) {
        return legacyRows;
      }
      const mainlineRows = dailyReviewV2?.mainline_daily_states;
      if (
        dailyReviewV2PreviewEnabled &&
        isV2ModuleReady(dailyReviewV2, "mainline_daily_states", mainlineRows)
      ) {
        return buildThemeSummaryRowsFromMainlineStates(
          mainlineRows ?? [],
          engineSummary,
          marketRegimeReview,
        );
      }
      return legacyRows;
    },
    [dailyReviewV2PreviewEnabled, dailyReviewV2, themeSection, cycleByTheme, engineSummary, marketRegimeReview],
  );
  const themeCapitalFlowRows = useMemo(
    () => {
      const v2Rows = dailyReviewV2?.theme_capital_reviews;
      if (
        dailyReviewV2PreviewEnabled &&
        isV2ModuleReady(dailyReviewV2, "theme_capital_reviews", v2Rows)
      ) {
        return buildThemeCapitalFlowRowsFromV2(v2Rows ?? []);
      }
      return themeCapitalFlowSection.map((item) => parseThemeCapitalFlowRow(item));
    },
    [dailyReviewV2PreviewEnabled, dailyReviewV2, themeCapitalFlowSection],
  );
  const stockCapitalFlowRows = useMemo(
    () => {
      const v2Rows = dailyReviewV2?.stock_capital_reviews;
      if (dailyReviewV2PreviewEnabled && isV2ModuleReady(dailyReviewV2, "stock_capital_reviews", v2Rows)) {
        return buildStockCapitalFlowRowsFromV2(v2Rows ?? []);
      }
      return stockCapitalFlowSection.map((item) => parseStockCapitalFlowRow(item));
    },
    [dailyReviewV2PreviewEnabled, dailyReviewV2, stockCapitalFlowSection],
  );
  const mainThemeRows = useMemo(() => themeSummaryRows.filter((row) => row.tier === "主线"), [themeSummaryRows]);
  const branchThemeRows = useMemo(() => themeSummaryRows.filter((row) => row.tier === "强分支"), [themeSummaryRows]);
  const themeKeyByTheme = useMemo(() => {
    const result = new Map<string, string>();
    for (const row of themeSummaryRows) {
      if (row.theme && row.subjectKey && row.subjectKey !== "--") result.set(row.theme, row.subjectKey);
    }
    for (const row of themeCapitalFlowRows) {
      if (row.theme && row.subjectKey && row.subjectKey !== "--" && !result.has(row.theme)) {
        result.set(row.theme, row.subjectKey);
      }
    }
    for (const row of watchlistRows) {
      if (row.theme && row.subjectKey && row.subjectKey !== "--" && !result.has(row.theme)) {
        result.set(row.theme, row.subjectKey);
      }
    }
    return result;
  }, [themeSummaryRows, themeCapitalFlowRows, watchlistRows]);
  const moneyFlowRows = useMemo(
    () => {
      const v2Rows = dailyReviewV2?.money_flow_reviews;
      if (dailyReviewV2PreviewEnabled && isV2ModuleReady(dailyReviewV2, "money_flow_reviews", v2Rows)) {
        return buildMoneyFlowRowsFromV2(v2Rows ?? []);
      }
      return moneySection.map((item) => {
        const parsed = splitThemeLine(item);
        return parseMoneyFlowRow(parsed.theme || "未分类", parsed.body);
      });
    },
    [dailyReviewV2PreviewEnabled, dailyReviewV2, moneySection],
  );
  const abnormalNote = useMemo(
    () => abnormalSection.find((item) => item.startsWith("补充说明：")) ?? "",
    [abnormalSection],
  );
  const abnormalDataSection = useMemo(
    () => abnormalSection.filter((item) => !item.startsWith("补充说明：")),
    [abnormalSection],
  );
  const dragonTigerNote = useMemo(
    () => auxSection.find((item) => item.startsWith("说明：")) ?? "",
    [auxSection],
  );
  const dragonTigerDataSection = useMemo(
    () => auxSection.filter((item) => !item.startsWith("说明：")),
    [auxSection],
  );
  const abnormalRows = useMemo(
    () => {
      const v2Rows = dailyReviewV2?.abnormal_reviews;
      if (dailyReviewV2PreviewEnabled && isV2ModuleReady(dailyReviewV2, "abnormal_reviews", v2Rows)) {
        return buildAbnormalRowsFromV2(v2Rows ?? []);
      }
      return abnormalDataSection.map((item) => {
        const parsed = splitThemeLine(item);
        return parseAbnormalSignalRow(parsed.theme || "未分类", parsed.body);
      });
    },
    [dailyReviewV2PreviewEnabled, dailyReviewV2, abnormalDataSection],
  );
  const sortedAbnormalRows = useMemo(() => {
    const rows = [...abnormalRows];
    rows.sort((a, b) => {
      const left = numericPart(a[abnormalSortKey]);
      const right = numericPart(b[abnormalSortKey]);
      return abnormalSortDir === "desc" ? right - left : left - right;
    });
    return rows;
  }, [abnormalRows, abnormalSortDir, abnormalSortKey]);
  const dragonTigerRows = useMemo(
    () => {
      if (dragonTigerDataSection.length > 0) {
        return dragonTigerDataSection.map((item) => {
          const parsed = splitThemeLine(item);
          return parsed.body.includes("/")
            ? parseDragonTigerRow(parsed.theme || "--", parsed.body)
            : parseDragonTigerLegacyRow(parsed.theme || "--", parsed.body);
        });
      }
      return [];
    },
    [dragonTigerDataSection],
  );

  useEffect(() => {
    let active = true;
    setPayload(null);
    setDailyReview(null);
    setDailyReviewV2(null);
    setGenerationSteps([]);
    setLoading(true);
    setError(null);

    if (reportType === "post_market") {
      let bootstrapFinalized = false;
      const finalizeBootstrap = (action: () => void) => {
        if (!active || bootstrapFinalized) return;
        bootstrapFinalized = true;
        action();
      };

      const snapshotPromise = fetchRecapSnapshot({ date: tradeDate, reportType });
      const readinessPromise = fetchPostMarketReadiness(tradeDate).catch(() => null);
      const jobsPromise = fetchPostMarketJobsStatus(tradeDate).catch(() => null);

      snapshotPromise
        .then((snapshot) => {
          finalizeBootstrap(() => {
            setPayload(snapshot);
            const query = buildRecapSearchParams({
              tradeDate,
              reportType,
              dataMode: dailyReviewV2PreviewEnabled ? "daily_review_v2_first" : "sections_first",
              viewMode,
            });
            window.history.replaceState(null, "", `/recap?${query.toString()}`);
            setLoading(false);
          });
        })
        .catch((err: Error) => {
          if (!active || bootstrapFinalized) return;
          if (isMissingPostMarketSnapshotError(err.message)) {
            return;
          }
          bootstrapFinalized = true;
          setError(err.message);
          setLoading(false);
        });

      void (async () => {
        const [readiness, jobs] = await Promise.all([readinessPromise, jobsPromise]);
        if (!active || bootstrapFinalized) return;
        if (readiness?.status === "failed_precondition" && !hasRunningPostMarketJob(jobs)) {
          bootstrapFinalized = true;
          setLoading(false);
          return;
        }
      })();

      fetchDailyReview(tradeDate)
        .then((data) => {
          if (!active) return;
          setDailyReview(data);
        })
        .catch(() => {});
      if (dailyReviewV2PreviewEnabled) {
        fetchDailyReviewV2(tradeDate)
          .then((data) => {
            if (!active) return;
            setDailyReviewV2(data);
          })
          .catch(() => {});
      }
      return () => { active = false; };
    }

    // pre_market: 原逻辑不变
    fetchRecapSnapshot({ date: tradeDate, reportType })
      .then((data) => {
        if (active) {
          setPayload(data);
          const query = buildRecapSearchParams({
            tradeDate,
            reportType,
            dataMode: dailyReviewV2PreviewEnabled ? "daily_review_v2_first" : "sections_first",
          });
          window.history.replaceState(null, "", `/recap?${query.toString()}`);
        }
      })
      .catch((err: Error) => {
        if (active) setError(err.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tradeDate, reportType, dailyReviewV2PreviewEnabled]);

  useEffect(() => {
    if (!derivedDataBusy && !recapBusy) return;
    const timer = window.setInterval(() => {
      setGenerationSteps((prev) =>
        prev.map((step) => {
          if (step.status !== "running") return step;
          const increment = step.progress < 60 ? 7 : 3;
          return { ...step, progress: Math.min(92, step.progress + increment) };
        }),
      );
    }, 800);
    return () => window.clearInterval(timer);
  }, [derivedDataBusy, recapBusy]);

  function toggleAbnormalSort(key: "score" | "turnoverRate" | "volumeRatio" | "volumeVsMa50") {
    if (abnormalSortKey === key) {
      setAbnormalSortDir((prev) => (prev === "desc" ? "asc" : "desc"));
      return;
    }
    setAbnormalSortKey(key);
    setAbnormalSortDir("desc");
  }

  async function handlePublishNotion() {
    if (!tradeDate || publishing) return;
    setPublishing(true);
    setPublishResult(null);
    try {
      const result = await publishRecapToNotion(tradeDate);
      setPublishResult(result);
    } catch (err) {
      setPublishResult({ ok: false, action: `error: ${err instanceof Error ? err.message : "unknown"}` });
    } finally {
      setPublishing(false);
    }
  }

  function openPostMarketLegacyView() {
    const query = buildRecapSearchParams({
      tradeDate,
      reportType: "post_market",
      dataMode: "sections_first",
      viewMode: "legacy",
    });
    navigateTo(`/recap?${query.toString()}`);
  }

  function openPostMarketEngineView() {
    const query = buildRecapSearchParams({
      tradeDate,
      reportType: "post_market",
      dataMode: "daily_review_v2_first",
    });
    navigateTo(`/recap?${query.toString()}`);
  }

  async function refreshPostMarketStatus() {
    return fetchPostMarketReadiness(tradeDate).catch(() => null);
  }

  async function refreshPostMarketViews() {
    const [snapshot, dr, v2] = await Promise.all([
      fetchRecapSnapshot({ date: tradeDate, reportType: "post_market" }).catch(() => null),
      fetchDailyReview(tradeDate).catch(() => null),
      dailyReviewV2PreviewEnabled ? fetchDailyReviewV2(tradeDate).catch(() => null) : Promise.resolve(null),
    ]);
    if (snapshot) setPayload(snapshot);
    if (dr) setDailyReview(dr);
    if (v2) setDailyReviewV2(v2);
    return snapshot;
  }

  function updateGenerationStep(key: string, patch: Partial<RecapGenerationStep>) {
    setGenerationSteps((prev) => prev.map((item) => (item.key === key ? { ...item, ...patch } : item)));
  }

  function requirePostMarketCommandOk(result: Record<string, unknown>, fallback: string) {
    if (result.ok !== false) return;
    const missingTables = Array.isArray(result.missing_tables) ? result.missing_tables.map(String).filter(Boolean) : [];
    const errorCode = typeof result.error_code === "string" ? result.error_code : "";
    const suffix = missingTables.length > 0 ? `缺失表: ${missingTables.join(", ")}` : errorCode;
    throw new Error(suffix ? `${fallback}: ${suffix}` : fallback);
  }

  async function handleStartPostMarketRecap() {
    if (derivedDataBusy || recapBusy) return;
    setError(null);
    setLoading(false);
    setDerivedDataBusy(true);
    setRecapBusy(true);
    setGenerationSteps(initialRecapGenerationSteps());
    try {
      updateGenerationStep("readiness", { status: "running", progress: 30 });
      const initialReadiness = await refreshPostMarketStatus();
      updateGenerationStep("readiness", { status: "success", progress: 100 });
      if (initialReadiness?.status === "ready") {
        updateGenerationStep("derived", { status: "success", progress: 100 });
      } else {
        updateGenerationStep("derived", { status: "running", progress: 35 });
        const derivedResult = await generatePostMarketDerivedData(tradeDate, true);
        requirePostMarketCommandOk(derivedResult, "生成动态复盘数据失败");
        updateGenerationStep("derived", { status: "success", progress: 100 });
      }
      updateGenerationStep("readiness", { status: "running", progress: 70 });
      const readiness = await refreshPostMarketStatus();
      if (readiness?.status !== "ready") {
        updateGenerationStep("readiness", { status: "failed", progress: 100 });
        setError("盘后复盘数据尚未 ready，请查看“盘后复盘数据状态”中的缺失项。");
        return;
      }
      updateGenerationStep("readiness", { status: "success", progress: 100 });
      updateGenerationStep("recap", { status: "running", progress: 35 });
      const recapResult = await generatePostMarketRecap(tradeDate, true);
      requirePostMarketCommandOk(recapResult, "生成复盘报告失败");
      updateGenerationStep("recap", { status: "success", progress: 100 });
      updateGenerationStep("daily_review_v2", { status: "running", progress: 40 });
      await generateDailyReviewV2(tradeDate, true).catch(() => null);
      updateGenerationStep("daily_review_v2", { status: "success", progress: 100 });
      await refreshPostMarketStatus();
      updateGenerationStep("snapshot", { status: "running", progress: 60 });
      const snapshot = await refreshPostMarketViews();
      if (!snapshot) {
        updateGenerationStep("snapshot", { status: "failed", progress: 100 });
        setError("复盘报告已触发生成，但当前还没有可读取的 snapshot，请稍后刷新。");
      } else {
        updateGenerationStep("snapshot", { status: "success", progress: 100 });
      }
    } catch (err) {
      setGenerationSteps((prev) => prev.map((item) => (item.status === "running" ? { ...item, status: "failed", progress: 100 } : item)));
      setError(err instanceof Error ? err.message : "开始复盘失败");
    } finally {
      setDerivedDataBusy(false);
      setRecapBusy(false);
    }
  }

  return (
    <div className="workspace-page recap-dark-theme">
      <section className="strong-watch-toolbar">
        <img src={recapIcon} alt="" style={{ height: 64, width: 64, flexShrink: 0 }} />
        <h1 className="strong-watch-title">{reportType === "post_market" ? "当日复盘" : "盘前必读"}</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginLeft: "auto" }}>
          <label style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ fontSize: 12, color: "#66d9ef" }}>交易日</span>
            <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)}
              style={{ border: "1px solid #2a2a2a", borderRadius: 6, background: "#1a1a1a", color: "#f5f5f5", padding: "4px 8px" }} />
          </label>
          <div className="recap-switch">
            <button type="button" className={`tag tag-button ${reportType === "post_market" ? "tag-active" : ""}`}
              style={{ fontSize: 16, padding: "8px 16px" }} onClick={() => setReportType("post_market")}>
              当日复盘
            </button>
            <button type="button" className="tag tag-button" style={{ fontSize: 16, padding: "8px 16px" }}
              onClick={() => navigateTo(`/pre-market-brief?trade_date=${tradeDate}`)}>
              盘前必读
            </button>
          </div>
          {reportType === "post_market" && (
            <>
              {payload && (
                <button
                  className="tag tag-button is-pass"
                  type="button"
                  style={{ fontSize: 16, padding: "8px 16px" }}
                  disabled={loading || isGeneratingRecap}
                  onClick={handleStartPostMarketRecap}
                >
                  {isGeneratingRecap ? "复盘中..." : "重新复盘"}
                </button>
              )}
              <button className="tag tag-button is-pass" type="button" style={{ fontSize: 16, padding: "8px 16px" }}
                disabled={publishing || loading || isGeneratingRecap} onClick={handlePublishNotion}>
                {publishing ? "发布中..." : "发布到 Notion"}
              </button>
            </>
          )}
          {publishResult?.page_url && (
            <a href={publishResult.page_url} target="_blank" rel="noreferrer" className="tag">
              打开 Notion 页面
            </a>
          )}
        </div>
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>
          返回
        </button>
      </section>

      {loading && <div className="empty-state">正在加载复盘视图...</div>}
      {error && <div className="empty-state error">{error}</div>}
      {!loading && reportType === "post_market" && !payload && (
        <div style={{ marginBottom: 12 }}>
          <button
            className="tag tag-button is-pass"
            type="button"
            disabled={derivedDataBusy || recapBusy}
            onClick={handleStartPostMarketRecap}
          >
            {derivedDataBusy || recapBusy ? "复盘中..." : "开始复盘"}
          </button>
        </div>
      )}

      {isGeneratingRecap && (
        <div className="collection-modal-backdrop">
          <div className="collection-modal recap-progress-modal" role="dialog" aria-modal="true" aria-label="复盘生成进度">
            <span className="metric-label section-title">正在生成当日复盘</span>
            <p className="workspace-note">复盘生成需要一些时间，请保持页面打开并等待完成。</p>
            <div className="collection-progress-panel">
              <div className="collection-progress-head">
                <span>{recapGenerationCurrentStep?.label ?? "准备复盘"}</span>
                <strong>{recapGenerationProgress}%</strong>
              </div>
              <div className="collection-progress-bar">
                <span style={{ width: `${recapGenerationProgress}%` }} />
              </div>
            </div>
          </div>
        </div>
      )}
      {!loading && !error && payload && (
        <>
          <main className="workspace-layout single">
            <section className="workspace-column">
              {isPostMarket ? (
                legacyViewEnabled ? (
                  <LegacyRecapSections
                    reportType="post_market"
                    tradeDate={tradeDate}
                    onShowEngine={openPostMarketEngineView}
                    highlights={highlights}
                    marketEnvironmentSection={marketEnvironmentSection}
                    themeEnvironmentSection={themeEnvironmentSection}
                    themeSection={themeSection}
                    themeSummaryRows={themeSummaryRows}
                    themeCapitalFlowRows={themeCapitalFlowRows}
                    strongStockSection={strongStockSection}
                    strongStockGroups={strongStockGroups}
                    watchlistSection={watchlistSection}
                    watchlistRows={watchlistRows}
                    stockCapitalFlowSection={stockCapitalFlowSection}
                    stockCapitalFlowRows={stockCapitalFlowRows}
                    moneySection={moneySection}
                    moneyFlowRows={moneyFlowRows}
                    abnormalSection={abnormalSection}
                    abnormalNote={abnormalNote}
                    abnormalRows={abnormalRows}
                    sortedAbnormalRows={sortedAbnormalRows}
                    auctionSection={auctionSection}
                    auctionValidationSection={auctionValidationSection}
                    auxSection={auxSection}
                    dragonTigerNote={dragonTigerNote}
                    dragonTigerRows={dragonTigerRows}
                    themeKeyByTheme={themeKeyByTheme}
                  />
                ) : engineReportReady ? (
                  <EnginePostMarketView
                    dailyReviewV2={dailyReviewV2!}
                    tradeDate={tradeDate}
                    onShowLegacy={openPostMarketLegacyView}
                  />
                ) : (
                  <EngineMissingState
                    dailyReviewV2={dailyReviewV2}
                    onRetry={handleStartPostMarketRecap}
                    onShowLegacy={openPostMarketLegacyView}
                  />
                )
              ) : (
                <LegacyRecapSections
                  reportType="pre_market"
                  tradeDate={tradeDate}
                  highlights={highlights}
                  marketEnvironmentSection={marketEnvironmentSection}
                  themeEnvironmentSection={themeEnvironmentSection}
                  themeSection={themeSection}
                  themeSummaryRows={themeSummaryRows}
                  themeCapitalFlowRows={themeCapitalFlowRows}
                  strongStockSection={strongStockSection}
                  strongStockGroups={strongStockGroups}
                  watchlistSection={watchlistSection}
                  watchlistRows={watchlistRows}
                  stockCapitalFlowSection={stockCapitalFlowSection}
                  stockCapitalFlowRows={stockCapitalFlowRows}
                  moneySection={moneySection}
                  moneyFlowRows={moneyFlowRows}
                  abnormalSection={abnormalSection}
                  abnormalNote={abnormalNote}
                  abnormalRows={abnormalRows}
                  sortedAbnormalRows={sortedAbnormalRows}
                  auctionSection={auctionSection}
                  auctionValidationSection={auctionValidationSection}
                  auxSection={auxSection}
                  dragonTigerNote={dragonTigerNote}
                  dragonTigerRows={dragonTigerRows}
                  themeKeyByTheme={themeKeyByTheme}
                />
              )}
            </section>
          </main>
        </>
      )}
    </div>
  );
}
