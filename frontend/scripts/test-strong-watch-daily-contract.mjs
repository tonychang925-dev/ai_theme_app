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
  apiSource.includes("/api/v2/strong_watch/watch?"),
  "strong watch client must use the BFF strong watch watch endpoint",
);
assert(
  apiSource.includes('query.set("date", params.date)'),
  "strong watch client must map date to the BFF watch endpoint",
);

console.log("strong watch daily contract passed");
