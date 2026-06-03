import { Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import type { MarketHotspotOverview, MarketHotspotRow } from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";

interface Props {
  marketHotspotOverview?: MarketHotspotOverview | null;
  tradeDate?: string;
}

function formatAmount(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const abs = Math.abs(Number(value));
  if (abs >= 1e8) return `${(Number(value) / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(Number(value) / 1e4).toFixed(2)}万`;
  return String(Math.round(Number(value)));
}

function formatHeat(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  return Number(value).toFixed(1);
}

function displayLifecycle(value?: string | null) {
  const key = String(value || "").trim();
  const map: Record<string, string> = {
    divergence: "分歧",
    start: "启动",
    fermentation: "发酵",
    watch: "观察",
    fade_watch: "退潮观察",
    fade_confirmed: "退潮确认",
    fade: "退潮",
  };
  return map[key] || key || "--";
}

function themeHref(theme: MarketHotspotRow, tradeDate?: string) {
  if (!theme.subject_key) return "";
  return `/themes/${encodeURIComponent(theme.subject_key)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function stockHref(stockId: string, tradeDate?: string) {
  if (!stockId) return "";
  return `/stocks/${encodeURIComponent(stockId)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function renderThemeName(row: MarketHotspotRow, tradeDate?: string) {
  const href = themeHref(row, tradeDate);
  return href ? (
    <button type="button" className="recap-theme-link" onClick={() => navigateTo(href)}>
      {row.theme_name || row.subject_key || "--"}
    </button>
  ) : (
    <span>{row.theme_name || row.subject_key || "--"}</span>
  );
}

export default function MarketHotspotOverviewPanel({ marketHotspotOverview, tradeDate }: Props) {
  if (!marketHotspotOverview || (marketHotspotOverview.hotspot_rows?.length ?? 0) === 0) return null;
  const diagnostics = marketHotspotOverview.diagnostics as Record<string, unknown> | undefined;
  const sourceTables = Array.isArray(diagnostics?.source_tables) ? diagnostics.source_tables : [];

  const rows = [...(marketHotspotOverview.hotspot_rows || [])].sort(
    (left, right) => (left.rank_order ?? 999) - (right.rank_order ?? 999),
  );

  const columns: ColumnsType<MarketHotspotRow & { key: string }> = [
    {
      title: "题材",
      key: "theme_name",
      dataIndex: "theme_name",
      width: 170,
      fixed: "left",
      render: (_: unknown, row: MarketHotspotRow) => (
        <div className="recap-tag-stack" style={{ gap: 6 }}>
          {renderThemeName(row, tradeDate)}
          <div className="recap-tag-stack" style={{ gap: 4, flexWrap: "wrap" }}>
            {row.is_confirmed_mainline ? <Tag color="green">主线相关</Tag> : <Tag color="default">轮动观察</Tag>}
            {row.mainline_name && row.mainline_name !== row.theme_name && <Tag color="blue">{row.mainline_name}</Tag>}
          </div>
        </div>
      ),
    },
    {
      title: "热度",
      key: "heat_score",
      width: 92,
      render: (_: unknown, row: MarketHotspotRow) => <Tag color="magenta">{formatHeat(row.heat_score)}</Tag>,
    },
    {
      title: "涨停数",
      key: "limit_up_count",
      width: 88,
      render: (_: unknown, row: MarketHotspotRow) => <span>{row.limit_up_count ?? "--"}</span>,
    },
    {
      title: "强股数",
      key: "strong_stock_count",
      width: 88,
      render: (_: unknown, row: MarketHotspotRow) => <span>{row.strong_stock_count ?? "--"}</span>,
    },
    {
      title: "资金流入",
      key: "total_inflow",
      width: 110,
      render: (_: unknown, row: MarketHotspotRow) => <span>{formatAmount(row.total_inflow ?? null)}</span>,
    },
    {
      title: "主线状态",
      key: "mainline_state",
      width: 100,
      render: (_: unknown, row: MarketHotspotRow) => (
        <Tag color={row.is_confirmed_mainline ? "green" : "default"}>{row.is_confirmed_mainline ? "主线" : "轮动"}</Tag>
      ),
    },
    {
      title: "生命周期",
      key: "lifecycle_state",
      width: 110,
      render: (_: unknown, row: MarketHotspotRow) => <Tag color={row.is_confirmed_mainline ? "blue" : "default"}>{displayLifecycle(row.lifecycle_state)}</Tag>,
    },
    {
      title: "代表股",
      key: "representative_stocks",
      width: 260,
      render: (_: unknown, row: MarketHotspotRow) => (
        <div className="recap-tag-stack" style={{ gap: 6, flexWrap: "wrap" }}>
          {(row.representative_stocks || []).length > 0 ? (
            row.representative_stocks.slice(0, 3).map((stock) => {
              const href = stockHref(stock.stock_id, tradeDate);
              return href ? (
                <button
                  key={`${row.subject_key}-${stock.stock_id}`}
                  type="button"
                  className="recap-theme-link recap-stock-highlight"
                  onClick={() => navigateTo(href)}
                >
                  {stock.stock_name || stock.stock_id || "--"}
                </button>
              ) : (
                <Tag key={`${row.subject_key}-${stock.stock_id}`}>{stock.stock_name || stock.stock_id || "--"}</Tag>
              );
            })
          ) : (
            <span className="workspace-note">--</span>
          )}
        </div>
      ),
    },
    {
      title: "明日动作",
      key: "action_advice",
      width: 180,
      render: (_: unknown, row: MarketHotspotRow) => <span>{row.action_advice || "--"}</span>,
    },
  ];

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        行情概览
        <Tag color="gold" style={{ marginLeft: 8 }}>今日热点</Tag>
        {marketHotspotOverview.source && <Tag color={marketHotspotOverview.source === "structured" ? "green" : "blue"}>{marketHotspotOverview.source}</Tag>}
      </h3>

      <div style={{ background: "rgba(255,214,102,0.08)", border: "1px solid rgba(255,214,102,0.18)", borderRadius: 8, padding: 14, marginBottom: 12 }}>
        <div className="workspace-note" style={{ marginBottom: 6 }}>热点摘要</div>
        <div style={{ fontSize: 16, fontWeight: 700, lineHeight: 1.6 }}>{marketHotspotOverview.summary}</div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">强势题材</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {marketHotspotOverview.strongest_themes.length > 0 ? marketHotspotOverview.strongest_themes.map((item) => <Tag key={item} color="blue">{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">主线相关</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {marketHotspotOverview.mainline_related_themes.length > 0 ? marketHotspotOverview.mainline_related_themes.map((item) => <Tag key={item} color="green">{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">轮动观察</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {marketHotspotOverview.rotation_themes.length > 0 ? marketHotspotOverview.rotation_themes.map((item) => <Tag key={item}>{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">风险主题</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {marketHotspotOverview.risk_themes.length > 0 ? marketHotspotOverview.risk_themes.map((item) => <Tag key={item} color="red">{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div style={{ overflowX: "auto" }}>
        <Table
          className="recap-table"
          dataSource={rows.map((row) => ({ ...row, key: `${row.rank_order ?? row.subject_key}-${row.subject_key}` }))}
          columns={columns}
          size="small"
          pagination={false}
          scroll={{ x: 1300 }}
          rowClassName={(row) => (row.is_confirmed_mainline ? "recap-row-focus" : "")}
        />
      </div>

      {marketHotspotOverview.diagnostics && (
        <div className="workspace-note" style={{ marginTop: 8 }}>
          诊断：主题 {String(diagnostics?.row_count ?? "--")}，来源 {String(sourceTables.length)}，涨停总数 {String(diagnostics?.limit_up_total ?? "--")}
        </div>
      )}
    </div>
  );
}
