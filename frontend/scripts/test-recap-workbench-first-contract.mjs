import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const apiPath = resolve("src/lib/api.ts");
const recapSource = readFileSync(recapPagePath, "utf8");
const apiSource = readFileSync(apiPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertRecapDoesNotGenerateDerivedData() {
  assert(
    !recapSource.includes("generatePostMarketDerivedData"),
    "RecapPage must not import or call generatePostMarketDerivedData",
  );
  assert(
    !recapSource.includes("/post-market/derived-data/generate"),
    "RecapPage must not call the derived-data generate endpoint directly",
  );
  assert(
    !recapSource.includes("生成动态复盘数据"),
    "RecapPage progress UI must not present derived-data production as a recap responsibility",
  );
}

function assertBackendApiRemainsAvailable() {
  assert(
    apiSource.includes("export async function generatePostMarketDerivedData"),
    "Backend derived-data API helper should remain available for internal/admin tools",
  );
}

function assertWorkbenchEntryRemainsVisible() {
  assert(
    recapSource.includes("/analyst-workspace?trade_date="),
    "RecapPage must keep a visible path to Analyst Workbench for starting analysis",
  );
  assert(
    recapSource.includes("分析师工作台"),
    "RecapPage must label the analyst workbench entry",
  );
}

function assertFormalReportLanguage() {
  assert(
    recapSource.includes("生成正式报告") || recapSource.includes("刷新正式报告"),
    "RecapPage must describe report generation as formal report generation/refresh",
  );
  assert(
    !recapSource.includes("重新复盘") && !recapSource.includes("生成遗留报告"),
    "RecapPage must not use legacy recap production labels",
  );
}

assertRecapDoesNotGenerateDerivedData();
assertBackendApiRemainsAvailable();
assertWorkbenchEntryRemainsVisible();
assertFormalReportLanguage();

console.log("recap workbench-first contract passed");
