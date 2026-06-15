import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const engineViewPath = resolve("src/routes/recap/components/EnginePostMarketView.tsx");
const evidencePanelPath = resolve("src/routes/recap/components/EvidenceLayerPanel.tsx");

const engineViewSource = readFileSync(engineViewPath, "utf8");
const evidencePanelSource = readFileSync(evidencePanelPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

assert(engineViewSource.includes("EvidenceLayerPanel"), "engine view must render evidence layer panel");
assert(evidencePanelSource.includes('renderSection("个股资金证据"'), "engine evidence layer must keep stock-capital evidence");
assert(
  !evidencePanelSource.includes('renderSection("资金行为证据"'),
  "engine evidence layer must not render duplicate money-flow evidence",
);

console.log("recap engine view contract passed");
