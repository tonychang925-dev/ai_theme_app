import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const stylesPath = resolve("src/styles.css");
const hotspotPath = resolve("src/routes/recap/components/MarketHotspotOverviewPanel.tsx");
const evidencePath = resolve("src/routes/recap/components/EvidenceLayerPanel.tsx");

const styles = readFileSync(stylesPath, "utf8");
const hotspot = readFileSync(hotspotPath, "utf8");
const evidence = readFileSync(evidencePath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertRootOverflowIsHidden() {
  assert(styles.includes(".workspace-page") && styles.includes("overflow-x: hidden;"), "workspace-page must hide page-level horizontal overflow");
  assert(styles.includes(".recap-dark-theme") && styles.includes("overflow-x: hidden;"), "recap-dark-theme must hide page-level horizontal overflow");
  assert(styles.includes(".recap-dark-theme .workspace-column") && styles.includes("overflow-x: auto;"), "recap workspace-column must own local horizontal scroll");
  assert(styles.includes(".recap-dark-theme .workspace-layout") && styles.includes("overflow-x: hidden;"), "recap workspace-layout must not create horizontal overflow");
}

function assertTagStackNoLongerForcesWidth() {
  assert(styles.includes(".recap-tag-stack") && styles.includes("min-width: 0;"), "recap-tag-stack must not force a minimum width");
  assert(styles.includes(".recap-dark-theme .recap-tag-stack") && styles.includes("max-width: 100%;"), "dark recap tag stacks must stay within container width");
}

function assertTableShellOwnsHorizontalScroll() {
  assert(styles.includes(".recap-table-shell") && styles.includes("contain: inline-size;"), "recap-table-shell must isolate inline size");
  assert(styles.includes(".recap-table-shell") && styles.includes("overflow-x: auto;"), "recap-table-shell must own horizontal scroll");
  assert(styles.includes(".recap-dark-theme .recap-table-shell .ant-table-wrapper") && styles.includes("overflow: hidden;"), "table shell must clip nested AntD wrapper overflow");
  assert(styles.includes(".recap-table-wrap") && styles.includes("overflow-x: auto;"), "recap-table-wrap must own horizontal scroll for legacy-style tables");
  assert(styles.includes(".recap-antd-table") && styles.includes("min-width: 0;"), "AntD recap tables must not inherit legacy min-width");
  assert(styles.includes(".recap-engine-panel") && styles.includes("min-width: 0;"), "recap engine panels must stay shrinkable");
}

function assertToolbarDoesNotForcePageOverflow() {
  assert(styles.includes(".recap-dark-theme .strong-watch-toolbar") && styles.includes("overflow-x: hidden;"), "recap toolbar must not create page-level horizontal overflow");
  assert(styles.includes(".recap-dark-theme .strong-watch-toolbar > div") && styles.includes("min-width: 0;"), "recap toolbar content must not force max-content width");
}

function assertHotspotPanelDoesNotForceBrowserScroll() {
  assert(hotspot.includes('className="recap-table-wrap"'), "MarketHotspotOverviewPanel table must be wrapped by recap-table-wrap");
  assert(hotspot.includes('className="recap-antd-table"'), "MarketHotspotOverviewPanel must use recap-antd-table");
  assert(!hotspot.includes('fixed: "left"'), "MarketHotspotOverviewPanel must not use fixed left column");
  assert(hotspot.includes('scroll={{ x: 1300 }}'), "MarketHotspotOverviewPanel may keep internal table scroll");
}

function assertEvidencePanelUsesTableShell() {
  assert(evidence.includes('className="recap-table-wrap"'), "EvidenceLayerPanel table must be wrapped by recap-table-wrap");
  assert(evidence.includes('className="recap-antd-table"'), "EvidenceLayerPanel must use recap-antd-table");
  assert(evidence.includes('scroll={{ x: 1450 }}'), "EvidenceLayerPanel may keep internal table scroll");
}

assertRootOverflowIsHidden();
assertTagStackNoLongerForcesWidth();
assertTableShellOwnsHorizontalScroll();
assertToolbarDoesNotForcePageOverflow();
assertHotspotPanelDoesNotForceBrowserScroll();
assertEvidencePanelUsesTableShell();

console.log("recap overflow contract passed");
