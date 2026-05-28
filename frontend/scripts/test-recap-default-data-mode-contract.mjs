import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const source = readFileSync(recapPagePath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertDefaultModeResolver() {
  assert(
    source.includes("function normalizePostMarketDataMode"),
    "RecapPage must normalize post_market data_mode values in one place",
  );
  assert(
    source.includes("function resolvePostMarketDataMode"),
    "RecapPage must resolve the default post_market dataMode through a helper",
  );
  assert(
    source.includes('params.get("data_mode")'),
    "URL data_mode must be read before environment defaults",
  );
  assert(
    source.includes("import.meta.env.VITE_POST_MARKET_DEFAULT_DATA_MODE"),
    "default dataMode must be controlled by VITE_POST_MARKET_DEFAULT_DATA_MODE",
  );
  assert(
    source.includes('?? "daily_review_v2_first"'),
    "missing or invalid default dataMode must fall back to daily_review_v2_first after P5.1",
  );
}

function assertRollbackUrlIsSupported() {
  assert(
    source.includes('value === "sections_first"'),
    "data_mode=sections_first must be supported as a rollback URL override",
  );
  assert(
    source.includes('window.location.search.includes("data_mode=sections_first")'),
    "data_mode=sections_first must be a hard rollback guard in the browser URL",
  );
  assert(
    source.includes('value === "daily_review_v2"') && source.includes('value === "daily_review_v2_first"'),
    "daily_review_v2 and daily_review_v2_first URL/env aliases must both map to V2 mode",
  );
  assert(
    source.includes("const urlMode = normalizePostMarketDataMode(params.get(\"data_mode\"))"),
    "URL data_mode must have higher priority than VITE_POST_MARKET_DEFAULT_DATA_MODE",
  );
}

function assertV2StillUsesReadyGateAndFallback() {
  assert(
    source.includes("const dailyReviewV2PreviewEnabled = dataMode === \"daily_review_v2_first\""),
    "V2 takeover must still be guarded by daily_review_v2_first mode",
  );
  assert(source.includes("function isV2ModuleReady"), "V2 modules must keep the ready gate");
  assert(source.includes('coverage?.status === "ready"'), "V2 gate must require ready coverage");
  assert(source.includes('coverage?.source === "structured"'), "V2 gate must require structured source");
  assert(
    source.includes("(coverage.missing_fields?.length ?? 0) === 0"),
    "V2 gate must reject modules with missing_fields",
  );

  const fallbacks = [
    "themeSection",
    "themeCapitalFlowSection",
    "strongStockSection",
    "watchlistSection",
    "stockCapitalFlowSection",
    "abnormalDataSection",
    "moneySection",
    "dragonTigerDataSection",
  ];
  for (const fallback of fallbacks) {
    assert(source.includes(fallback), `sections fallback must remain for ${fallback}`);
  }
}

function assertDefaultSwitchUsesResolver() {
  assert(
    !source.includes('const dataMode = "daily_review_v2_first"'),
    "P5.1 default switch must still go through the resolver, not a hard-coded dataMode constant",
  );
}

assertDefaultModeResolver();
assertRollbackUrlIsSupported();
assertV2StillUsesReadyGateAndFallback();
assertDefaultSwitchUsesResolver();

console.log("recap default data_mode contract passed");
