import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const appPath = resolve("src/App.tsx");
const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");

const appSource = readFileSync(appPath, "utf8");
const recapSource = readFileSync(recapPagePath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(appSource.includes("const [search, setSearch] = useState(window.location.search);"), "AppRoutes must track search state");
assert(appSource.includes("const currentSearch = window.location.search;"), "AppRoutes must read current search on URL checks");
assert(appSource.includes("if (currentSearch !== search)"), "AppRoutes must update search when query string changes");
assert(appSource.includes("}, [path, search]);"), "AppRoutes effect must react to search changes");
assert(recapSource.includes("function openPostMarketLegacyView()"), "RecapPage must expose legacy view toggle");
assert(recapSource.includes('viewMode: "legacy"'), "RecapPage must set legacy view mode explicitly");

console.log("recap search navigation contract passed");
