import { Table, Tag } from "antd";
import type {
  DailyRecapEssentials,
  LimitUpLadderSummary,
  LimitUpThemeEventsSummary,
  LimitUpThemeMatrix,
  HotMoneySeatActivityEntry,
  HotMoneySeatActivityRow,
  NewHighSummary,
  SeatMoneyInstitutionRow,
  SeatMoneySummary,
} from "../../../lib/api";
import { navigateTo } from "../../../lib/navigation";
import MarketOverviewPanel from "./MarketOverviewPanel";

interface Props {
  essentials?: DailyRecapEssentials | null;
  ladder?: LimitUpLadderSummary | null;
  themeEvents?: LimitUpThemeEventsSummary | null;
  limitUpThemeMatrix?: LimitUpThemeMatrix | null;
  newHigh?: NewHighSummary | null;
  seatMoney?: SeatMoneySummary | null;
  subjectKeyToThemeName?: Map<string, string>;
  tradeDate?: string;
}

function fmtAmount(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  const abs = Math.abs(n);
  if (abs >= 1e8) return `${(n / 1e8).toFixed(2)}亿`;
  if (abs >= 1e4) return `${(n / 1e4).toFixed(2)}万`;
  return String(Math.round(n));
}

function fmtPrice(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  return Number.isInteger(n) ? String(n) : n.toFixed(2);
}

function stockLink(stockId?: string, tradeDate?: string) {
  if (!stockId) return "";
  return `/stocks/${encodeURIComponent(stockId)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function themeLink(subjectKey?: string, tradeDate?: string) {
  if (!subjectKey) return "";
  return `/themes/${encodeURIComponent(subjectKey)}${tradeDate ? `?date=${encodeURIComponent(tradeDate)}` : ""}`;
}

function renderSummaryPoints(points: string[] = []) {
  if (!points.length) return <span className="workspace-note">暂无复盘要点</span>;
  return (
    <ul className="workspace-list">
      {points.map((point, idx) => (
        <li key={`daily-recap-point-${idx}`}>
          <div className="workspace-note">{point}</div>
        </li>
      ))}
    </ul>
  );
}

function fmtPct(value?: number | null) {
  if (value == null || Number.isNaN(Number(value))) return "--";
  const n = Number(value);
  return `${n.toFixed(2)}%`;
}

function renderMoneyCell(entry?: HotMoneySeatActivityEntry | null, kind?: "buy" | "sell") {
  if (!entry) return <span className="workspace-note">--</span>;
  const amount = kind === "sell" ? Math.abs(Number(entry.net_amount || 0)) : entry.net_amount;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
      <span>{entry.stock_name || entry.stock_id || "--"}</span>
      <span className="workspace-note">{fmtAmount(amount)}</span>
    </div>
  );
}

function renderHotMoneyRows(rows: HotMoneySeatActivityRow[] = [], kind: "buy" | "sell") {
  if (!rows.length) return <span className="workspace-note">暂无结构化游资数据</span>;
  const entriesKey = kind === "buy" ? "buy_entries" : "sell_entries";
  return (
    <Table
      className="recap-antd-table"
      size="small"
      pagination={false}
      dataSource={rows.map((row) => ({ ...row, key: row.hot_money_name }))}
      columns={[
        { title: "游资", dataIndex: "hot_money_name", width: 120 },
        {
          title: kind === "buy" ? "净买入1" : "净卖出1",
          dataIndex: entriesKey,
          render: (_: unknown, row: Record<string, any>) => renderMoneyCell((row[entriesKey] || [])[0], kind),
        },
        {
          title: kind === "buy" ? "净买入2" : "净卖出2",
          dataIndex: entriesKey,
          render: (_: unknown, row: Record<string, any>) => renderMoneyCell((row[entriesKey] || [])[1], kind),
        },
        {
          title: kind === "buy" ? "净买入3" : "净卖出3",
          dataIndex: entriesKey,
          render: (_: unknown, row: Record<string, any>) => renderMoneyCell((row[entriesKey] || [])[2], kind),
        },
      ]}
    />
  );
}

function renderInstitutionRows(rows: SeatMoneyInstitutionRow[] = [], kind: "buy" | "sell") {
  if (!rows.length) return <span className="workspace-note">暂无结构化机构席位数据</span>;
  return (
    <Table
      className="recap-antd-table"
      size="small"
      pagination={false}
      dataSource={rows.map((row, idx) => ({ ...row, key: `${row.stock_id || row.stock_name || idx}-${kind}` }))}
      columns={[
        { title: "序号", dataIndex: "rank", width: 60, render: (_: unknown, __: unknown, index: number) => index + 1 },
        { title: "代码", dataIndex: "stock_id", width: 90 },
        { title: "名称", dataIndex: "stock_name", width: 110 },
        { title: "收盘价", dataIndex: "close_price", width: 90, render: (_: unknown, row: SeatMoneyInstitutionRow) => fmtPrice(row.close_price) },
        { title: "涨跌幅", dataIndex: "pct_change", width: 90, render: (_: unknown, row: SeatMoneyInstitutionRow) => fmtPct(row.pct_change) },
        { title: "买方机构数", dataIndex: "buy_seat_count", width: 90 },
        { title: "卖方机构数", dataIndex: "sell_seat_count", width: 90 },
        { title: "机构买入", dataIndex: "institution_buy_amount", width: 100, render: (_: unknown, row: SeatMoneyInstitutionRow) => fmtAmount(row.institution_buy_amount) },
        { title: "机构卖出", dataIndex: "institution_sell_amount", width: 100, render: (_: unknown, row: SeatMoneyInstitutionRow) => fmtAmount(row.institution_sell_amount) },
        { title: "机构净额", dataIndex: "net_buy", width: 100, render: (_: unknown, row: SeatMoneyInstitutionRow) => fmtAmount(row.net_buy) },
      ]}
    />
  );
}

function buildThemeEventRowsFromMatrix(matrix?: LimitUpThemeMatrix | null): LimitUpThemeEventsSummary["rows"] {
  return (matrix?.columns || []).map((col) => ({
    subject_key: col.subject_key,
    theme_name: col.theme_name,
    limit_up_count: Number(col.limit_up_count || 0),
    active_mainline: Boolean(col.active_mainline),
    lifecycle_state: col.lifecycle_state || undefined,
    trade_action: col.trade_action || undefined,
    representative_stocks: (col.focus_stocks || []).slice(0, 3).map((stock) => ({
      stock_id: stock.stock_id || "",
      stock_name: stock.stock_name || "",
      board_count: stock.board_count ?? null,
      role_label: stock.role_label || undefined,
      trade_action: stock.trade_action || undefined,
    })),
    catalyst_events: (col.catalyst_events || []).slice(0, 3).map((event) => ({
      event_id: event.event_id || null,
      summary: event.summary || null,
      event_time: event.event_time || null,
      confidence: event.confidence ?? null,
      match_reason: event.match_reason || null,
    })),
  }));
}

export default function DailyRecapStoryPanel({
  essentials,
  ladder,
  themeEvents,
  limitUpThemeMatrix,
  newHigh,
  seatMoney,
  subjectKeyToThemeName,
  tradeDate,
}: Props) {
  const themeRows = buildThemeEventRowsFromMatrix(limitUpThemeMatrix);
  const themeEventRows = themeRows.length > 0 ? themeRows : (themeEvents?.rows || []);
  const newHighRows = newHigh?.industry_summary || [];
  const resolveThemeName = (value?: string | null) => {
    const text = String(value || "").trim();
    if (!text) return "";
    const mapped = subjectKeyToThemeName?.get(text) || text;
    if (mapped === "__independent__" || mapped.toLowerCase() === "independent" || mapped.startsWith("__")) {
      return "未归类";
    }
    return mapped;
  };
  const seatMoneySummaryText = seatMoney?.summary || (() => {
    const institutionNames = [
      ...(seatMoney?.institution_buy_rows || []).map((row) => row.stock_name),
      ...(seatMoney?.institution_sell_rows || []).map((row) => row.stock_name),
    ].filter(Boolean).slice(0, 3);
    const hotMoneyNames = [
      ...(seatMoney?.hot_money_buy_rows || []).map((row) => row.hot_money_name),
      ...(seatMoney?.hot_money_sell_rows || []).map((row) => row.hot_money_name),
    ].filter(Boolean).slice(0, 3);
    const themeNames = [
      ...(seatMoney?.institution_buy_rows || []).map((row) => resolveThemeName(row.theme_name)).filter(Boolean),
      ...(seatMoney?.institution_sell_rows || []).map((row) => resolveThemeName(row.theme_name)).filter(Boolean),
      ...(seatMoney?.hot_money_buy_rows || []).flatMap((row) => row.buy_entries || []).map((entry) => resolveThemeName(entry.theme_name)).filter(Boolean),
      ...(seatMoney?.hot_money_sell_rows || []).flatMap((row) => row.sell_entries || []).map((entry) => resolveThemeName(entry.theme_name)).filter(Boolean),
    ].filter(Boolean) as string[];
    if (!institutionNames.length && !hotMoneyNames.length && !themeNames.length) return "";
    const parts: string[] = [];
    if (institutionNames.length > 0) parts.push(`机构关注 ${institutionNames.join("、")}`);
    if (hotMoneyNames.length > 0) parts.push(`游资关注 ${hotMoneyNames.join("、")}`);
    if (seatMoney?.cohesion) parts.push(`资金整体${seatMoney.cohesion}`);
    if (themeNames.length > 0) parts.push(`主题聚焦 ${Array.from(new Set(themeNames)).slice(0, 3).join("、")}`);
    return parts.join("，");
  })() || "暂无结构化机构席位/游资数据";
  const isPlaceholderTheme = (value?: string | null) => {
    const text = String(value || "").trim();
    if (!text) return true;
    return text === "__independent__" || text.toLowerCase() === "independent" || text === "未归类" || text.startsWith("__");
  };

  return (
    <div className="recap-engine-groups">
      <section className="workspace-card recap-engine-group">
        <h3 className="section-title recap-panel-title">
          今日复盘要点
          {essentials?.source && <Tag color={essentials.source === "engine_template" ? "green" : "blue"} style={{ marginLeft: 8 }}>{essentials.source}</Tag>}
        </h3>
        <div className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="recap-hero-text">{essentials?.headline || "今日复盘要点"}</div>
        </div>
        <div className="workspace-card" style={{ marginBottom: 12 }}>
          {renderSummaryPoints(essentials?.summary_points || [])}
        </div>
        <div className="workspace-card">
          <div className="workspace-note">次日观察</div>
          <div className="recap-body-text">{essentials?.next_day_strategy || "--"}</div>
        </div>
      </section>

      <section className="workspace-card recap-engine-group">
        <h3 className="section-title recap-panel-title">涨停热点总览</h3>
        {limitUpThemeMatrix && (
          <div className="workspace-card" style={{ marginBottom: 12 }}>
            <MarketOverviewPanel
              limitUpThemeMatrix={limitUpThemeMatrix}
              tradeDate={tradeDate}
              subjectKeyToThemeName={subjectKeyToThemeName}
            />
          </div>
        )}
        <div className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="recap-body-text">{limitUpThemeMatrix?.summary || ladder?.summary || "暂无结构化连板梯队数据"}</div>
        </div>
        <div className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="recap-body-text">{limitUpThemeMatrix?.summary || themeEvents?.summary || "暂无结构化涨停题材事件"}</div>
        </div>
        <Table
          className="recap-antd-table"
          size="small"
          pagination={false}
          dataSource={themeEventRows.map((row) => ({ ...row, key: row.subject_key }))}
          columns={[
            {
              title: "题材",
              dataIndex: "theme_name",
              width: 150,
              render: (_: unknown, row: { subject_key?: string; theme_name?: string }) => (
                row.subject_key && !isPlaceholderTheme(row.subject_key) ? (
                  <button type="button" className="recap-theme-link" onClick={() => navigateTo(themeLink(row.subject_key, tradeDate))}>
                    {resolveThemeName(row.subject_key) || resolveThemeName(row.theme_name) || "--"}
                  </button>
                ) : (
                  <span>{resolveThemeName(row.subject_key) || resolveThemeName(row.theme_name) || "--"}</span>
                )
              ),
            },
            { title: "涨停数", dataIndex: "limit_up_count", width: 80 },
            {
              title: "代表板位股",
              dataIndex: "representative_stocks",
              render: (_: unknown, row: any) => (
                <div className="recap-tag-stack" style={{ gap: 6, flexWrap: "wrap" }}>
                  {(row.representative_stocks || []).length > 0
                    ? row.representative_stocks!.slice(0, 3).map((stock: any, idx: number) => (
                        <Tag key={`${stock.stock_id || stock.stock_name || idx}`}>{stock.stock_name || stock.stock_id || "--"}</Tag>
                      ))
                    : <span className="workspace-note">--</span>}
                </div>
              ),
            },
            {
              title: "催化事件",
              dataIndex: "catalyst_events",
              render: (_: unknown, row: any) => (
                <div className="workspace-note">
                  {(row.catalyst_events || []).length > 0 ? (row.catalyst_events || []).slice(0, 2).map((event: any) => event.summary).filter(Boolean).join("；") : "--"}
                </div>
              ),
            },
          ]}
        />
      </section>

      <section className="workspace-card recap-engine-group">
        <h3 className="section-title recap-panel-title">股价新高与行业趋势</h3>
        <div className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="recap-body-text">{newHigh?.summary || "暂无结构化创新高数据"}</div>
        </div>
        <Table
          className="recap-antd-table"
          size="small"
          pagination={false}
          dataSource={newHighRows.map((row) => ({ ...row, key: row.industry_name }))}
          columns={[
            { title: "行业", dataIndex: "industry_name", width: 160 },
            { title: "数量", dataIndex: "count", width: 80 },
            {
              title: "代表股",
              dataIndex: "representative_stocks",
              render: (_: unknown, row: any) => (
                <div className="recap-tag-stack" style={{ gap: 6, flexWrap: "wrap" }}>
                  {(row.representative_stocks || []).length > 0
                    ? row.representative_stocks!.slice(0, 3).map((stock: any) => {
                        const href = stockLink(stock.stock_id, tradeDate);
                        return (
                          <button
                            key={`${stock.stock_id || stock.stock_name}`}
                            type="button"
                            className="recap-theme-link recap-stock-highlight"
                            onClick={() => href && navigateTo(href)}
                          >
                            {stock.stock_name || stock.stock_id || "--"}
                          </button>
                        );
                      })
                    : <span className="workspace-note">--</span>}
                </div>
              ),
            },
          ]}
        />
      </section>

      <section className="workspace-card recap-engine-group">
        <h3 className="section-title recap-panel-title">机构席位和游资动向</h3>
        <div className="workspace-card" style={{ marginBottom: 12 }}>
          <div className="recap-body-text">{seatMoneySummaryText}</div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 12, marginBottom: 12 }}>
          <div className="workspace-card">
            <div className="workspace-note" style={{ marginBottom: 8 }}>游资净买入</div>
            {renderHotMoneyRows(seatMoney?.hot_money_buy_rows || [], "buy")}
          </div>
          <div className="workspace-card">
            <div className="workspace-note" style={{ marginBottom: 8 }}>游资净卖出</div>
            {renderHotMoneyRows(seatMoney?.hot_money_sell_rows || [], "sell")}
          </div>
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 12 }}>
          <div className="workspace-card">
            <div className="workspace-note" style={{ marginBottom: 8 }}>机构当日净买入</div>
            {renderInstitutionRows(seatMoney?.institution_buy_rows || [], "buy")}
          </div>
          <div className="workspace-card">
            <div className="workspace-note" style={{ marginBottom: 8 }}>机构当日净卖出</div>
            {renderInstitutionRows(seatMoney?.institution_sell_rows || [], "sell")}
          </div>
        </div>
      </section>
    </div>
  );
}
