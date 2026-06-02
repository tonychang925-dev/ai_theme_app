import fs from "node:fs";
import path from "node:path";

const pageSource = fs.readFileSync(path.resolve("src/routes/intel/StrongStockWatchPage.tsx"), "utf8");
const apiSource = fs.readFileSync(path.resolve("src/lib/api.ts"), "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(pageSource.includes("dedupByStockEntryDate"), "strong watch page must dedupe across the full window by stock entry date");
assert(pageSource.includes("dedupByDate(filteredRows)"), "strong watch page must keep same-day dedupe");
assert(
  apiSource.includes("${SPS_BASE}/api/v1/strong_watch?"),
  "strong watch client must use the SPS_BASE v1 7-day history endpoint",
);
assert(
  apiSource.includes('trade_date'),
  "strong watch client must map date to trade_date for the v1 endpoint",
);

console.log("strong watch daily contract passed");
