import { useEffect, useMemo, useState } from "react";
import type { RecapViewModelV2 } from "../../lib/api";
import { fetchRecapSnapshot } from "../../lib/api";
import { navigateTo } from "../../lib/navigation";

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

function sectionMap(payload: RecapViewModelV2 | null) {
  const map = new Map<string, string[]>();
  for (const section of payload?.sections ?? []) {
    map.set(section.heading, section.items);
  }
  return map;
}

export function RecapPage() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const initialType = window.location.search.includes("report_type=pre_market") ? "pre_market" : "post_market";
  const initialDate = new URLSearchParams(window.location.search).get("date") ?? today;

  const [tradeDate, setTradeDate] = useState(initialDate);
  const [reportType, setReportType] = useState<"pre_market" | "post_market">(initialType);
  const [abnormalSortKey, setAbnormalSortKey] = useState<"score" | "turnoverRate" | "volumeRatio" | "volumeVsMa50">("score");
  const [abnormalSortDir, setAbnormalSortDir] = useState<"desc" | "asc">("desc");
  const [payload, setPayload] = useState<RecapViewModelV2 | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const sections = useMemo(() => sectionMap(payload), [payload]);
  const marketEnvironmentSection = sections.get("大盘环境总结") ?? [];
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
    return Array.from(groups.entries()).filter(([, rows]) => rows.length > 0);
  }, [strongStockSection]);
  const watchlistRows = useMemo(() => {
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
  }, [watchlistSection]);
  const themeSummaryRows = useMemo(
    () =>
      themeSection.map((item) => {
        const parsed = splitThemeLine(item);
        return parseThemeSummary(
          parsed.theme || "未分类",
          parsed.body,
          cycleByTheme.get(parsed.theme) ?? "",
        );
      }),
    [themeSection, cycleByTheme],
  );
  const themeCapitalFlowRows = useMemo(
    () => themeCapitalFlowSection.map((item) => parseThemeCapitalFlowRow(item)),
    [themeCapitalFlowSection],
  );
  const stockCapitalFlowRows = useMemo(
    () => stockCapitalFlowSection.map((item) => parseStockCapitalFlowRow(item)),
    [stockCapitalFlowSection],
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
    () =>
      moneySection.map((item) => {
        const parsed = splitThemeLine(item);
        return parseMoneyFlowRow(parsed.theme || "未分类", parsed.body);
      }),
    [moneySection],
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
    () =>
      abnormalDataSection.map((item) => {
        const parsed = splitThemeLine(item);
        return parseAbnormalSignalRow(parsed.theme || "未分类", parsed.body);
      }),
    [abnormalDataSection],
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
    () =>
      dragonTigerDataSection.map((item) => {
        const parsed = splitThemeLine(item);
        return parsed.body.includes("/")
          ? parseDragonTigerRow(parsed.theme || "--", parsed.body)
          : parseDragonTigerLegacyRow(parsed.theme || "--", parsed.body);
      }),
    [dragonTigerDataSection],
  );

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);
    fetchRecapSnapshot({ date: tradeDate, reportType })
      .then((data) => {
        if (active) {
          setPayload(data);
          const query = new URLSearchParams({ date: tradeDate, report_type: reportType });
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
  }, [tradeDate, reportType]);

  function toggleAbnormalSort(key: "score" | "turnoverRate" | "volumeRatio" | "volumeVsMa50") {
    if (abnormalSortKey === key) {
      setAbnormalSortDir((prev) => (prev === "desc" ? "asc" : "desc"));
      return;
    }
    setAbnormalSortKey(key);
    setAbnormalSortDir("desc");
  }

  return (
    <div className="workspace-page">
      <header className="workspace-topbar">
        <button className="back-button" type="button" onClick={() => navigateTo("/intel")}>
          返回情报台
        </button>
        <div>
          <p className="eyebrow">Recap Workspace</p>
          <h1>{payload?.title ?? "复盘工作台"}</h1>
          <p className="subtle">{payload?.summary ?? "读取 P3.phase2 真源表生成的盘前 / 盘后报告。"}</p>
        </div>
      </header>

      <section className="workspace-card">
        <div className="recap-toolbar">
          <label className="recap-toolbar-date">
            <span>交易日</span>
            <input type="date" value={tradeDate} onChange={(event) => setTradeDate(event.target.value)} />
          </label>
          <div className="recap-switch">
            <button
              type="button"
              className={`tag tag-button ${reportType === "post_market" ? "tag-active" : ""}`}
              onClick={() => setReportType("post_market")}
            >
              当日复盘
            </button>
            <button
              type="button"
              className={`tag tag-button ${reportType === "pre_market" ? "tag-active" : ""}`}
              onClick={() => setReportType("pre_market")}
            >
              盘前必读
            </button>
          </div>
        </div>
      </section>

      {loading && <div className="empty-state">正在加载复盘视图...</div>}
      {error && <div className="empty-state error">{error}</div>}

      {!loading && !error && payload && (
        <>
          <main className="workspace-layout single">
            <section className="workspace-column">
              {(marketEnvironmentSection.length > 0 || payload.highlights.length > 0) && (
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
                            {marketEnvironmentSection.slice(2).map((item, idx) => (
                              <li key={`market-env-${idx}`}>
                                <strong>{`环境要点 ${idx + 1}`}</strong>
                                <p className="workspace-note">{zh(item)}</p>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}

                    <div className="market-summary-card">
                      <span className="metric-label section-title">核心要点</span>
                      {payload.highlights.length > 0 ? (
                        <ul className="workspace-list">
                          {payload.highlights.map((item, idx) => (
                            <li key={`highlight-${idx}`}>
                              <strong>要点 {idx + 1}</strong>
                              <p className="workspace-note">{zh(item)}</p>
                            </li>
                          ))}
                        </ul>
                      ) : (
                        <p className="workspace-note">暂无高亮摘要</p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {(sections.get("主线与支线") ?? sections.get("可做主线与支线") ?? []).length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">{payload.report_type === "post_market" ? "主线与支线" : "可做主线与支线"}</span>
                  {payload.report_type === "post_market" ? (
                    <div className="recap-table-stack">
                      <article className="workspace-card recap-table-card">
                        <div className="recap-table-head">
                          <strong>主线</strong>
                        </div>
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
                          <div className="recap-table-head">
                            <strong>强分支</strong>
                          </div>
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

              {themeCapitalFlowRows.length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">主线资金流入前10</span>
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
                </div>
              )}

              {(sections.get("强势股分层") ?? sections.get("盘前重点盯盘个股") ?? []).length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">{payload.report_type === "post_market" ? "强势股分层" : "盘前重点盯盘个股"}</span>
                  {payload.report_type === "post_market" ? (
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
                                  <tr key={`row-${themeName}-${idx}`} data-role={strongStockBucket(row.raw)}>
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
                                  <td>{renderDecisionTags(row)}</td>
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

              {watchlistSection.length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">次日观察清单</span>
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
                            <td className="recap-cell-wrap">
                              {zh(
                                [row.catalyst !== "--" ? row.catalyst : "", row.labels !== "--" ? row.labels : ""]
                                  .filter(Boolean)
                                  .join("；") || "--",
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {stockCapitalFlowRows.length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">股票资金流入前20</span>
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
                </div>
              )}

              {abnormalSection.length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">当日异动股与资金行为</span>
                  {abnormalNote && <p className="workspace-note">{zh(abnormalNote)}</p>}
                  <div className="recap-table-wrap">
                    <table className="recap-table">
                      <thead>
                        <tr>
                          <th>股票</th>
                          <th>题材</th>
                          <th><button type="button" className="link-button" onClick={() => toggleAbnormalSort("score")}>异动分</button></th>
                          <th><button type="button" className="link-button" onClick={() => toggleAbnormalSort("turnoverRate")}>换手率</button></th>
                          <th><button type="button" className="link-button" onClick={() => toggleAbnormalSort("volumeRatio")}>量比</button></th>
                          <th><button type="button" className="link-button" onClick={() => toggleAbnormalSort("volumeVsMa50")}>成交量/50日均量</button></th>
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

              {auxSection.length > 0 && (
                <div className="workspace-card">
                  <span className="metric-label section-title">{payload.report_type === "post_market" ? "龙虎榜" : "失效条件"}</span>
                  {payload.report_type === "post_market" ? (
                    <>
                      {dragonTigerNote && <p className="workspace-note">{zh(dragonTigerNote)}</p>}
                      {dragonTigerRows.length > 0 && (
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
            </section>
          </main>
        </>
      )}
    </div>
  );
}
