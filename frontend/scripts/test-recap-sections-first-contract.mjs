import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const recapPagePath = resolve("src/routes/recap/RecapPage.tsx");
const source = readFileSync(recapPagePath, "utf8");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

const coreModules = [
  { title: "主线与支线", heading: "主线与支线", field: "theme_reviews" },
  { title: "主线资金流入前10", heading: "主线资金流入前10", field: "theme_capital_reviews" },
  { title: "强势股分层", heading: "强势股分层", field: "strong_stock_reviews" },
  { title: "次日观察清单", heading: "次日观察清单", field: "watchlist_reviews" },
  { title: "股票资金流入前20", heading: "主线股票资金流入前20", field: "stock_capital_reviews" },
  { title: "当日异动股与资金行为", heading: "当日异动股与资金行为", field: "abnormal_reviews" },
  { title: "资金行为增强", heading: "资金行为增强", field: "money_flow_reviews" },
  { title: "龙虎榜", heading: "龙虎榜", field: "dragon_tiger_reviews" },
];

function sectionMap(sections) {
  return new Map(sections.map((section) => [section.heading, section.items]));
}

function buildSectionsFixture(emptyHeading = null) {
  return {
    report_type: "post_market",
    trade_date: "2026-05-26",
    title: "2026-05-26 盘后复盘",
    summary: "contract fixture",
    highlights: [],
    sections: coreModules.map((module) => ({
      heading: module.heading,
      items: module.heading === emptyHeading ? [] : [`${module.heading}：fixture item`],
    })),
    source: "recap_v2_report",
  };
}

function buildVisibleModuleContract(payload) {
  const sections = sectionMap(payload.sections);
  return coreModules.map((module) => {
    const rows = sections.get(module.heading) ?? [];
    return {
      title: module.title,
      rows,
      visible: payload.report_type === "post_market" || rows.length > 0,
      emptyText: `暂无数据，请检查 report.sections.${module.heading}`,
    };
  });
}

function assertFullFixtureDisplaysAllModules() {
  const modules = buildVisibleModuleContract(buildSectionsFixture());
  for (const module of modules) {
    assert(module.visible, `完整 fixture 下模块必须展示: ${module.title}`);
    assert(module.rows.length > 0, `完整 fixture 下模块必须有数据: ${module.title}`);
  }
}

function assertEmptyFixtureKeepsModuleVisible() {
  for (const target of coreModules) {
    const modules = buildVisibleModuleContract(buildSectionsFixture(target.heading));
    const module = modules.find((item) => item.title === target.title);
    assert(module, `缺少模块 contract: ${target.title}`);
    assert(module.visible, `空模块不得静默消失: ${target.title}`);
    assert(module.rows.length === 0, `空模块 fixture 应为空: ${target.title}`);
    assert(
      source.includes(module.emptyText),
      `RecapPage 必须包含空态提示: ${module.emptyText}`,
    );
  }
}

function assertDailyReviewDoesNotOverrideSectionsFirst() {
  assert(
    !source.includes("if (dailyReview?.theme_reviews?.length)"),
    "sections_first 禁止 dailyReview.theme_reviews 接管主线与支线主体渲染",
  );
  assert(
    !source.includes("if (dailyReview?.strong_stock_reviews?.length)"),
    "sections_first 禁止 dailyReview.strong_stock_reviews 接管强势股主体渲染",
  );
  assert(
    source.includes('fetchRecapSnapshot({ date: tradeDate, reportType })'),
    "sections_first 主体加载必须调用 fetchRecapSnapshot",
  );
  assert(
    source.includes("{!loading && !error && payload && ("),
    "sections_first 主体渲染必须以 payload 为前置条件",
  );
}

function assertCoreTitlesArePinned() {
  for (const module of coreModules) {
    assert(source.includes(module.title), `RecapPage 必须固定显示核心模块标题: ${module.title}`);
  }
}

function assertPostMarketPrimaryCtaIsAlwaysVisible() {
  assert(
    source.includes('{derivedDataBusy || recapBusy ? "复盘中..." : "开始复盘"}'),
    "盘后复盘状态面板必须固定显示单一主 CTA: 开始复盘",
  );
  assert(
    !source.includes("仅生成动态数据"),
    "盘后复盘状态面板不得再显示单独的仅生成动态数据按钮",
  );
  assert(
    !source.includes("{payload && (\n                <button className=\"tag tag-button is-pass\""),
    "开始复盘/重新生成主 CTA 不得被 payload 条件隐藏",
  );
}

assertFullFixtureDisplaysAllModules();
assertEmptyFixtureKeepsModuleVisible();
assertDailyReviewDoesNotOverrideSectionsFirst();
assertCoreTitlesArePinned();
assertPostMarketPrimaryCtaIsAlwaysVisible();

console.log("recap sections_first contract passed");
