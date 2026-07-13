import fs from "node:fs";
import path from "node:path";

const root = process.cwd();
const componentPath = path.join(root, "src", "components", "analyst", "ChartRenderer.tsx");
const source = fs.readFileSync(componentPath, "utf8");

if (!source.includes("key_metrics?: Record<string, any>")) {
  throw new Error("ChartRenderer must accept key_metrics chart payloads");
}

if (!source.includes("function chartData(chart: ChartData): Record<string, any>")) {
  throw new Error("ChartRenderer must normalize chart data through chartData()");
}

if (!source.includes("chart.key_metrics")) {
  throw new Error("chartData() must use chart.key_metrics when chart.data is absent");
}

const dispatcher = source.slice(
  source.indexOf("export function ChartRenderer"),
  source.indexOf("function chartData"),
);

if (dispatcher.includes("data={chart.data}")) {
  throw new Error("ChartRenderer dispatcher must not pass chart.data directly");
}

if (!source.includes("const TREND_VISIBLE_POINTS = 15")) {
  throw new Error("TrendLineChart must use a 15 trading-day visible window");
}

if (!source.includes("overflowX: \"auto\"")) {
  throw new Error("TrendLineChart must allow horizontal scrolling for longer history");
}

if (!source.includes("scrollRef.current.scrollLeft = scrollRef.current.scrollWidth")) {
  throw new Error("TrendLineChart must default-scroll to the latest trading window");
}

console.log("ChartRenderer data contract OK");
