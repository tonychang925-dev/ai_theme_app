import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const legacySectionsPath = resolve("src/routes/recap/components/LegacyRecapSections.tsx");
const apiPath = resolve("src/lib/api.ts");

const recapPageSource = readFileSync(recapPagePath, "utf8");
const legacySource = readFileSync(legacySectionsPath, "utf8");
const apiSource = readFileSync(apiPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertRecapPageKeepsLegacyDebugEntryOptIn() {
  assert(
    recapPageSource.includes('params.get("view") === "legacy"'),
    "RecapPage must support ?view=legacy for the raw debug view",
  );
  assert(
    recapPageSource.includes('params.get("legacy_sections") === "1"'),
    "RecapPage must support ?legacy_sections=1 for the raw debug view",
  );
  assert(
    recapPageSource.includes('const effectiveDataMode = viewMode === "legacy" ? "sections_first" : dataMode'),
    "RecapPage must force sections_first in legacy mode",
  );
  assert(
    recapPageSource.includes("const legacyViewEnabled = isPostMarket && viewMode === \"legacy\""),
    "post_market legacy debug view must remain opt-in",
  );
  assert(
    recapPageSource.includes("LegacyRecapSections"),
    "RecapPage must still render the legacy debug component on demand",
  );
  assert(
    recapPageSource.includes("EnginePostMarketView"),
    "RecapPage must keep engine-first as the default post-market path",
  );
  assert(
    !recapPageSource.includes("dailyReviewV2?.dragon_tiger_reviews"),
    "legacy recap dragon tiger view must not fall back to DailyReview V2 rows",
  );
}

function assertSnapshotMapperKeepsNestedLegacyReport() {
  assert(
    apiSource.includes('recapDoc["report"]') && apiSource.includes('recapDoc["recap"]'),
    "snapshot mapper must read nested legacy recap_doc report sections",
  );
}

function assertLegacyDebugCopyIsExplicit() {
  assert(
    legacySource.includes("旧版 sections 仅用于排查与兼容展示，不参与交易结论。"),
    "LegacyRecapSections must keep the original warning text",
  );
  assert(
    legacySource.includes("返回引擎视图"),
    "LegacyRecapSections must keep the original return CTA",
  );
}

function assertLegacyEmptyStatesAreNavigationHints() {
  const expectedHints = [
    "暂无数据，请检查 report.sections.主线与支线",
    "暂无数据，请检查 report.sections.主线资金流入前10",
    "暂无数据，请检查 report.sections.强势股分层",
    "暂无数据，请检查 report.sections.次日观察清单",
    "暂无数据，请检查 report.sections.主线股票资金流入前20",
    "暂无数据，请检查 report.sections.当日异动股与资金行为",
    "暂无数据，请检查 report.sections.资金行为增强",
    "暂无数据，请检查 report.sections.龙虎榜",
  ];

  for (const hint of expectedHints) {
    assert(legacySource.includes(hint), `LegacyRecapSections must use navigation hint: ${hint}`);
  }
}

function assertGenerationTimeoutBudgetsStillHold() {
  assert(
    apiSource.includes("POST_MARKET_DERIVED_DATA_GENERATE_TIMEOUT_MS = 600000"),
    "盘后派生数据生成请求必须允许 10 分钟，避免长任务被代理超时截断",
  );
  assert(
    apiSource.includes("POST_MARKET_RECAP_GENERATE_TIMEOUT_MS = 300000"),
    "盘后复盘报告生成请求必须允许 5 分钟",
  );
  assert(
    apiSource.includes("POST_MARKET_DAILY_REVIEW_V2_GENERATE_TIMEOUT_MS = 180000"),
    "DailyReview V2 生成请求必须允许 3 分钟",
  );
}

assertRecapPageKeepsLegacyDebugEntryOptIn();
assertSnapshotMapperKeepsNestedLegacyReport();
assertLegacyDebugCopyIsExplicit();
assertLegacyEmptyStatesAreNavigationHints();
assertGenerationTimeoutBudgetsStillHold();

console.log("recap legacy debug view contract passed");
