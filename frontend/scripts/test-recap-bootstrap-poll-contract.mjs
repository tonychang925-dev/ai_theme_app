import fs from "node:fs";
import path from "node:path";

const file = path.resolve("src/routes/recap/RecapPage.tsx");
const source = fs.readFileSync(file, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(
  source.includes("fetchPostMarketReadiness(tradeDate)"),
  "RecapPage should check readiness before deciding whether to show the start button",
);
assert(
  source.includes("fetchPostMarketJobsStatus(tradeDate)"),
  "RecapPage should use job status to distinguish no-report dates from in-progress generation",
);
assert(
  source.includes("request timeout after"),
  "RecapPage should still treat snapshot timeouts as retryable during bootstrap",
);

console.log("recap bootstrap poll contract: ok");
