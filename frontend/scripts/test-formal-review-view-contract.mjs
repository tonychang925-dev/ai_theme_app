import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const formalViewPath = resolve("src/routes/recap/components/FormalReviewView.tsx");
const apiPath = resolve("src/lib/api.ts");

const recapSource = readFileSync(recapPagePath, "utf8");
const formalSource = readFileSync(formalViewPath, "utf8");
const apiSource = readFileSync(apiPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertFormalReviewTypeExists() {
  assert(
    apiSource.includes("export interface FormalReviewProjection"),
    "api.ts must define FormalReviewProjection",
  );
  assert(
    apiSource.includes("formal_review?: FormalReviewProjection"),
    "PostMarketDailyReviewV2 must expose formal_review projection",
  );
}

function assertRecapUsesFormalReviewView() {
  assert(
    recapSource.includes("import FormalReviewView"),
    "RecapPage must import FormalReviewView",
  );
  assert(
    recapSource.includes("dailyReviewV2?.formal_review"),
    "RecapPage must gate FormalReviewView on dailyReviewV2.formal_review",
  );
  assert(
    recapSource.includes("<FormalReviewView"),
    "RecapPage must render FormalReviewView",
  );
}

function assertDualTrackLegacyViewsRemain() {
  assert(
    recapSource.includes("<WorkbenchSectionsPanel"),
    "PR4 must keep WorkbenchSectionsPanel for dual-track comparison",
  );
  assert(
    recapSource.includes("<EnginePostMarketView"),
    "PR4 must keep EnginePostMarketView for dual-track comparison",
  );
  assert(
    recapSource.indexOf("<FormalReviewView") < recapSource.indexOf("<WorkbenchSectionsPanel"),
    "FormalReviewView should render before legacy/workbench sections",
  );
}

function assertFormalViewConsumesProjectionOnly() {
  const forbiddenLegacyTokens = [
    "theme_reviews",
    "strong_stock_reviews",
    "watchlist_reviews",
    "stock_capital_reviews",
    "money_flow_reviews",
    "dragon_tiger_reviews",
    "post_market_decision_v2",
    "engine_summary",
  ];
  for (const token of forbiddenLegacyTokens) {
    assert(
      !formalSource.includes(token),
      `FormalReviewView must not read legacy DailyReviewV2 field ${token}`,
    );
  }
  assert(
    formalSource.includes("formalReview.executive_summary"),
    "FormalReviewView must render executive_summary from formal_review",
  );
  assert(
    formalSource.includes("formalReview.market_state"),
    "FormalReviewView must render market_state from formal_review",
  );
  assert(
    formalSource.includes("formalReview.theme_structure"),
    "FormalReviewView must render theme_structure from formal_review",
  );
  assert(
    formalSource.includes("formalReview.stock_structure"),
    "FormalReviewView must render stock_structure from formal_review",
  );
  assert(
    formalSource.includes("formalReview.capital_evidence"),
    "FormalReviewView must render capital_evidence from formal_review",
  );
  assert(
    formalSource.includes("formalReview.next_day_plan"),
    "FormalReviewView must render next_day_plan from formal_review",
  );
}

assertFormalReviewTypeExists();
assertRecapUsesFormalReviewView();
assertDualTrackLegacyViewsRemain();
assertFormalViewConsumesProjectionOnly();

console.log("formal review view contract passed");
