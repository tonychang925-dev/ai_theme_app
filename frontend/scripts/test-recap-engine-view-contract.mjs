import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const source = readFileSync(recapPagePath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertViewResolver() {
  assert(source.includes("function resolveRecapViewMode"), "RecapPage must resolve recap view mode in one place");
  assert(source.includes('params.get("view") === "legacy"'), "RecapPage must support ?view=legacy");
  assert(source.includes('params.get("legacy_sections") === "1"'), "RecapPage must support ?legacy_sections=1");
  assert(source.includes("const legacyViewEnabled = isPostMarket && viewMode === \"legacy\""), "post_market legacy view must be opt-in");
}

function assertEngineReadyGate() {
  assert(source.includes("function isEngineReportReady"), "RecapPage must define engine readiness gate");
  assert(source.includes("engine_summary"), "engine readiness must require engine_summary");
  assert(source.includes("market_regime_review"), "engine readiness must require market_regime_review");
  assert(source.includes("mainline_daily_states"), "engine readiness must require mainline_daily_states");
  assert(source.includes("post_market_decision_v2"), "engine readiness must require post_market_decision_v2");
  assert(source.includes("const engineReportReady = isEngineReportReady(dailyReviewV2)"), "RecapPage must compute engineReportReady");
}

function assertPostMarketBranching() {
  assert(source.includes("EnginePostMarketView"), "post_market engine view must be rendered");
  assert(source.includes("EngineMissingState"), "post_market missing state must be rendered when engine is incomplete");
  assert(source.includes("LegacyRecapSections"), "legacy recap sections must remain available");
  assert(source.includes("engineReportReady ?"), "post_market main path must branch on engine readiness");
  assert(source.includes("legacyViewEnabled ?"), "post_market main path must branch on legacy mode");
  assert(source.includes("onShowLegacy={openPostMarketLegacyView}"), "engine view must expose a legacy toggle");
  assert(source.includes("onRetry={handleStartPostMarketRecap}"), "missing state must allow re-running recap");
}

function assertNoDirectEnginePanelsInPage() {
  assert(!source.includes("RecapDataQualityBar"), "RecapPage must not directly render RecapDataQualityBar");
  assert(!source.includes("EngineDecisionHeader"), "RecapPage must not directly render EngineDecisionHeader");
  assert(!source.includes("MarketRegimePanel"), "RecapPage must not directly render MarketRegimePanel");
  assert(!source.includes("MarketOverviewPanel"), "RecapPage must not directly render MarketOverviewPanel");
  assert(!source.includes("MainlineStateBoard"), "RecapPage must not directly render MainlineStateBoard");
  assert(!source.includes("D1NextDayWatchPanel"), "RecapPage must not directly render D1NextDayWatchPanel");
  assert(!source.includes("LayerCStrongPoolPanel"), "RecapPage must not directly render LayerCStrongPoolPanel");
}

assertViewResolver();
assertEngineReadyGate();
assertPostMarketBranching();
assertNoDirectEnginePanelsInPage();

console.log("recap engine view contract passed");
