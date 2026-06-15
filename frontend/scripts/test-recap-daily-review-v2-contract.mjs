import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const source = readFileSync(recapPagePath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const modules = [
  {
    key: "theme_reviews",
    heading: "主线与支线",
    fallback: "themeSection",
    builder: "buildThemeSummaryRowsFromV2",
  },
  {
    key: "theme_capital_reviews",
    heading: "主线资金流入前10",
    fallback: "themeCapitalFlowSection",
    builder: "buildThemeCapitalFlowRowsFromV2",
  },
  {
    key: "strong_stock_reviews",
    heading: "强势股分层",
    fallback: "strongStockSection",
    builder: "buildStrongStockGroupsFromV2",
  },
  {
    key: "watchlist_reviews",
    heading: "次日观察清单",
    fallback: "watchlistSection",
    builder: "buildWatchlistRowsFromV2",
  },
  {
    key: "stock_capital_reviews",
    heading: "主线股票资金流入前20",
    fallback: "stockCapitalFlowSection",
    builder: "buildStockCapitalFlowRowsFromV2",
  },
  {
    key: "abnormal_reviews",
    heading: "当日异动股与资金行为",
    fallback: "abnormalDataSection",
    builder: "buildAbnormalRowsFromV2",
  },
  {
    key: "money_flow_reviews",
    heading: "资金行为增强",
    fallback: "moneySection",
    builder: "buildMoneyFlowRowsFromV2",
  },
];

function assertDefaultModeStaysSectionsFirst() {
  assert(
    source.includes("resolvePostMarketDataMode(initialParams)"),
    "RecapPage must resolve dataMode through the P4.4 default-mode helper",
  );
  assert(
    source.includes('?? "daily_review_v2_first"'),
    "RecapPage default dataMode must be daily_review_v2_first after P5.1",
  );
  assert(
    !source.includes('const dataMode = "daily_review_v2_first"'),
    "RecapPage must not hard-code daily_review_v2_first as the default",
  );
}

function assertV2GateExists() {
  assert(source.includes("dailyReviewV2PreviewEnabled"), "RecapPage must keep a V2 preview gate");
  assert(source.includes("function isV2ModuleReady"), "RecapPage must define isV2ModuleReady");
  assert(source.includes('coverage?.status === "ready"'), "V2 gate must require ready coverage");
  assert(source.includes('coverage?.source === "structured"'), "V2 gate must require structured source");
  assert(
    source.includes("(coverage.missing_fields?.length ?? 0) === 0"),
    "V2 gate must reject modules with missing_fields",
  );
}

function assertEveryModuleUsesReadyGateAndFallback() {
  for (const module of modules) {
    const gatePattern = new RegExp(
      `isV2ModuleReady\\(\\s*dailyReviewV2,\\s*"${module.key}",\\s*v2Rows\\s*\\)`,
      "m",
    );
    assert(gatePattern.test(source), `${module.key} must use isV2ModuleReady before structured takeover`);
    assert(source.includes(`dailyReviewV2?.${module.key}`), `${module.key} must read DailyReview V2 rows`);
    assert(source.includes(module.builder), `${module.key} must have a structured row builder`);
    assert(source.includes(module.fallback), `${module.key} must keep legacy sections fallback: ${module.fallback}`);
  }
}

function assertNoV1MainPathReturns() {
  assert(
    !source.includes("if (dailyReview?.theme_reviews?.length)"),
    "DailyReview V1 theme_reviews must not retake the recap body",
  );
  assert(
    !source.includes("if (dailyReview?.strong_stock_reviews?.length)"),
    "DailyReview V1 strong_stock_reviews must not retake the recap body",
  );
}

assertDefaultModeStaysSectionsFirst();
assertV2GateExists();
assertEveryModuleUsesReadyGateAndFallback();
assertNoV1MainPathReturns();

console.log("recap daily_review_v2 contract passed");
