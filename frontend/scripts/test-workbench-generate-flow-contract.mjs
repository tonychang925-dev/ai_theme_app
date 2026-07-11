import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const workspacePagePath = resolve("src/components/analyst/AnalystWorkspacePage.tsx");
const emotionDashboardPath = resolve("src/components/analyst/EmotionDashboard.tsx");
const workbenchSectionsPath = resolve("src/routes/recap/components/WorkbenchSectionsPanel.tsx");

const workspaceSource = readFileSync(workspacePagePath, "utf8");
const emotionSource = readFileSync(emotionDashboardPath, "utf8");
const sectionsSource = readFileSync(workbenchSectionsPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertWorkbenchGenerateFlowMatchesCurrentArchitecture() {
  assert(
    workspaceSource.includes("生成复盘动态数据"),
    "Analyst Workspace generate progress must start with post-market derived data",
  );
  assert(
    workspaceSource.includes("生成图表证据"),
    "Analyst Workspace generate progress must include evidence chart generation",
  );
  assert(
    workspaceSource.includes("生成情绪分析"),
    "Analyst Workspace generate progress must include emotion generation",
  );
  assert(
    workspaceSource.includes("构建 AI Draft"),
    "Analyst Workspace generate progress must include AI draft construction",
  );
  assert(
    workspaceSource.includes("generation_steps"),
    "Analyst Workspace must display backend generation_steps instead of fake progress only",
  );
  assert(
    workspaceSource.includes("/api/v1/analyst-workbench/${dateInput}/session"),
    "Analyst Workspace must poll the workbench session while generate is running",
  );
  assert(
    !workspaceSource.includes("生成 AI 图表数据"),
    "Analyst Workspace must not present the legacy chart-only generate step",
  );
}

function assertEmptyStatesUseWorkbenchFirstLanguage() {
  const combined = `${emotionSource}\n${sectionsSource}`;
  assert(
    combined.includes("复盘动态数据"),
    "Empty states must point users to the current Workbench First data flow",
  );
  assert(
    !combined.includes("生成 AI 图表"),
    "Empty states must not tell users that Start Analysis only generates AI charts",
  );
}

assertWorkbenchGenerateFlowMatchesCurrentArchitecture();
assertEmptyStatesUseWorkbenchFirstLanguage();

console.log("workbench generate flow contract passed");
