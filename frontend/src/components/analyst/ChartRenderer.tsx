import React from "react";

interface ChartData {
  chart_id: string;
  trade_date: string;
  chart_type: string;
  title: string;
  data: Record<string, any>;
  interpretation: string;
}

export function ChartRenderer({ chart }: { chart: ChartData }) {
  switch (chart.chart_type) {
    case "market_breadth": return <BreadthChart data={chart.data} interpretation={chart.interpretation} />;
    case "emotion_momentum": return <MomentumChart data={chart.data} interpretation={chart.interpretation} />;
    case "active_capital": return <CapitalChart data={chart.data} interpretation={chart.interpretation} />;
    case "relay_ecology": return <RelayChart data={chart.data} interpretation={chart.interpretation} />;
    case "institution_style": return <StyleTable data={chart.data} title="机构资金审美" interpretation={chart.interpretation} />;
    case "hot_money_style": return <StyleTable data={chart.data} title="游资情绪方向" interpretation={chart.interpretation} />;
    case "limitup_classification": return <LimitUpChart data={chart.data} interpretation={chart.interpretation} />;
    default: return <pre style={{ fontSize: 10, color: "#5a7a8a" }}>{JSON.stringify(chart.data, null, 2)}</pre>;
  }
}

// ── Breadth Chart (bar comparison) ──

function BreadthChart({ data, interpretation }: { data: any; interpretation: string }) {
  const up = data.up_count || 0;
  const down = data.down_count || 0;
  const total = up + down || 1;
  const upPct = (up / total * 100);
  const downPct = (down / total * 100);

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ marginBottom: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricBox label="涨停" value={data.limit_up_count} color="#e53e3e" />
        <MetricBox label="跌停" value={data.limit_down_count} color="#38a169" />
        <MetricBox label="成交额" value={`${data.turnover_yi}万亿`} color="#d69e2e" />
        <MetricBox label="评分" value={data.composite_score} color={data.composite_score >= 0 ? "#38a169" : "#e53e3e"} />
        <MetricBox label="状态" value={data.label} color="#66d9ef" />
      </div>
      <div style={{ marginBottom: 4, fontSize: 11, color: "#8ddcff" }}>涨跌分布</div>
      <div style={{ display: "flex", height: 20, borderRadius: 3, overflow: "hidden", marginBottom: 4 }}>
        <div style={{ width: `${upPct}%`, background: "#38a169", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#fff" }}>
          {upPct > 10 ? `↑${up} (${upPct.toFixed(0)}%)` : ""}
        </div>
        <div style={{ width: `${downPct}%`, background: "#e53e3e", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, color: "#fff" }}>
          {downPct > 10 ? `↓${down} (${downPct.toFixed(0)}%)` : ""}
        </div>
      </div>
      <div style={{ fontSize: 10, color: "#5a7a8a" }}>{interpretation}</div>
    </div>
  );
}

// ── Momentum Chart (gauge style) ──

function MomentumChart({ data, interpretation }: { data: any; interpretation: string }) {
  const score = data.emotion_momentum_score || 0;
  const pct = Math.max(0, Math.min(100, (score + 18) / 28 * 100));
  const color = score >= 5 ? "#38a169" : score >= 0 ? "#d69e2e" : score >= -5 ? "#dd6b20" : score >= -10 ? "#e53e3e" : "#66d9ef";

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ marginBottom: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricBox label="首板红盘比" value={`${(data.first_board_red_ratio * 100).toFixed(0)}%`} color="#38a169" />
        <MetricBox label="首板大面比" value={`${(data.first_board_big_loss_ratio * 100).toFixed(0)}%`} color="#e53e3e" />
        <MetricBox label="连板红盘比" value={`${(data.chain_board_red_ratio * 100).toFixed(0)}%`} color="#d69e2e" />
        <MetricBox label="情绪动能" value={score.toFixed(1)} color={color} />
      </div>
      <div style={{ marginBottom: 4, fontSize: 11, color: "#8ddcff" }}>动能仪表 (-18 ~ +10)</div>
      <div style={{ height: 8, background: "#1a2a3a", borderRadius: 4, position: "relative", marginBottom: 4 }}>
        <div style={{ position: "absolute", left: `${pct}%`, top: -2, width: 12, height: 12, borderRadius: "50%", background: color }} />
      </div>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#5a7a8a" }}>
        <span>冰点(-18)</span><span>退潮(-10)</span><span>分歧(-5)</span><span>正常(0)</span><span>活跃(+5)</span><span>高涨(+10)</span>
      </div>
      <div style={{ marginTop: 4, fontSize: 10, color: "#5a7a8a" }}>{interpretation}</div>
    </div>
  );
}

// ── Active Capital Chart ──

function CapitalChart({ data, interpretation }: { data: any; interpretation: string }) {
  const total = data.total_amount_wan_yi || 0;
  const active = data.active_amount_wan_yi || 0;
  const pct = total > 0 ? (active / total * 100) : 3;

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ marginBottom: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricBox label="全市场成交" value={`${total}万亿`} color="#d69e2e" />
        <MetricBox label="活跃资金" value={`${active}万亿`} color="#66d9ef" />
        <MetricBox label="涨停数" value={data.limit_up_count} color="#e53e3e" />
        <MetricBox label="状态" value={data.label} color="#dd6b20" />
      </div>
      <div style={{ marginBottom: 4, fontSize: 11, color: "#8ddcff" }}>活跃资金占比 (~{pct.toFixed(0)}%)</div>
      <div style={{ height: 6, background: "#1a2a3a", borderRadius: 3, marginBottom: 4 }}>
        <div style={{ width: `${pct * 10}%`, height: "100%", background: "#66d9ef", borderRadius: 3 }} />
      </div>
      <div style={{ fontSize: 10, color: "#5a7a8a" }}>{interpretation}</div>
    </div>
  );
}

// ── Relay Ecology (ladder table) ──

function RelayChart({ data, interpretation }: { data: any; interpretation: string }) {
  const promotions = [
    { label: "一进二", rate: data.promotion_1_to_2, color: "#38a169" },
    { label: "二进三", rate: data.promotion_2_to_3, color: "#d69e2e" },
    { label: "三进四", rate: data.promotion_3_to_4, color: "#dd6b20" },
  ];

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ marginBottom: 6, display: "flex", gap: 12, flexWrap: "wrap" }}>
        <MetricBox label="最高板" value={data.max_board_height} color="#e53e3e" />
        <MetricBox label="首板封板率" value={`${(data.first_board_success_rate * 100).toFixed(0)}%`} color="#38a169" />
        <MetricBox label="状态" value={data.label} color="#66d9ef" />
      </div>
      <div style={{ marginBottom: 4, fontSize: 11, color: "#8ddcff" }}>晋级率</div>
      {promotions.map(p => (
        <div key={p.label} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
          <span style={{ width: 50, fontSize: 11, color: "#8ddcff" }}>{p.label}</span>
          <div style={{ flex: 1, height: 6, background: "#1a2a3a", borderRadius: 3 }}>
            <div style={{ width: `${p.rate * 100}%`, height: "100%", background: p.color, borderRadius: 3 }} />
          </div>
          <span style={{ width: 35, fontSize: 10, color: "#5a7a8a" }}>{(p.rate * 100).toFixed(0)}%</span>
        </div>
      ))}
      <div style={{ marginTop: 4, fontSize: 10, color: "#5a7a8a" }}>{interpretation}</div>
    </div>
  );
}

// ── Institution / Hot Money Style Table ──

function StyleTable({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  const directions: { name: string; state: string; score?: number; inflow?: number }[] = data.directions || [];

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ marginBottom: 6, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, color: "#8ddcff", fontWeight: 600 }}>{title}</span>
        <span style={{ fontSize: 11, color: "#5a7a8a" }}>{data.label}</span>
        {data.market_mode && <span style={{ fontSize: 11, color: "#d69e2e" }}>mode: {data.market_mode}</span>}
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 4 }}>
        {directions.slice(0, 10).map((d, i) => (
          <span key={i} style={{
            fontSize: 10, padding: "2px 6px", borderRadius: 3,
            background: d.state.includes("调整") || d.state.includes("退潮") ? "#e53e3e20" : d.state.includes("修复") || d.state.includes("启动") || d.state.includes("趋势") ? "#38a16920" : "#1a2a3a",
            color: d.state.includes("调整") ? "#e53e3e" : d.state.includes("修复") || d.state.includes("启动") || d.state.includes("趋势") ? "#38a169" : "#8ddcff",
          }}>
            {d.name} {d.state}
            {d.score !== undefined && <span style={{ marginLeft: 2, color: "#5a7a8a" }}>{d.score}</span>}
          </span>
        ))}
      </div>
      <div style={{ fontSize: 10, color: "#5a7a8a" }}>{interpretation}</div>
    </div>
  );
}

// ── Limit-up Classification ──

function LimitUpChart({ data, interpretation }: { data: any; interpretation: string }) {
  const categories: Record<string, string[]> = data.categories || {};
  const stocks: { name: string; theme: string; role: string }[] = data.top_stocks || [];

  return (
    <div style={{ fontSize: 12 }}>
      <MetricBox label="涨停总数" value={data.limit_up_count} color="#e53e3e" />
      <div style={{ marginTop: 6, fontSize: 11, color: "#8ddcff", marginBottom: 4 }}>涨停分类</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 6 }}>
        {Object.entries(categories).map(([cat, names]) => (
          <div key={cat} style={{ fontSize: 10 }}>
            <div style={{ color: "#d69e2e", marginBottom: 2 }}>{cat}</div>
            {(names as string[]).map((n, i) => (
              <div key={i} style={{ color: "#8ddcff", padding: "1px 0" }}>{n}</div>
            ))}
          </div>
        ))}
      </div>
      {stocks.length > 0 && (
        <div style={{ fontSize: 10, color: "#5a7a8a" }}>
          {stocks.slice(0, 6).map((s, i) => (
            <span key={i} style={{ marginRight: 8 }}>{s.name}({s.role})</span>
          ))}
        </div>
      )}
      <div style={{ marginTop: 4, fontSize: 10, color: "#5a7a8a" }}>{interpretation}</div>
    </div>
  );
}

// ── Shared ──

function MetricBox({ label, value, color }: { label: string; value: any; color: string }) {
  return (
    <div style={{ textAlign: "center", minWidth: 60 }}>
      <div style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 9, color: "#5a7a8a" }}>{label}</div>
    </div>
  );
}
