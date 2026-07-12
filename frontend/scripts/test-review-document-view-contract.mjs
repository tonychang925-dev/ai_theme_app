import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const componentPath = path.join(root, "src", "components", "review-document", "ReviewDocumentView.tsx");
const source = fs.readFileSync(componentPath, "utf8");

const forbiddenPatterns = [
  "fetch(",
  "/api/emotion",
  "/api/analyst-charts",
  "/daily-review-v2",
  "EmotionDashboard",
  "ChartRenderer",
  "FormalReviewView",
];

for (const pattern of forbiddenPatterns) {
  if (source.includes(pattern)) {
    throw new Error(`ReviewDocumentView must not depend on legacy data source: ${pattern}`);
  }
}

if (!source.includes("document: ReviewDocument")) {
  throw new Error("ReviewDocumentView must consume the ReviewDocument prop contract");
}

console.log("ReviewDocumentView contract OK");
