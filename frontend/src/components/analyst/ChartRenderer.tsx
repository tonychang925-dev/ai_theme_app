import React from "react";

interface ChartData {
  chart_id: string; trade_date: string; chart_type: string;
  title: string; data: Record<string, any>; interpretation: string;
}

// ═══════════════════════════════════════════════════════════
// Multi-day Line Chart (analyst style: 6/25~7/8 trend)
// ═══════════════════════════════════════════════════════════

export function TrendLineChart({ title, data, yKey, yLabel, color, yMax }: {
  title: string; data: any[]; yKey: string; yLabel: string; color: string; yMax?: number;
}) {
  if (!data || data.length < 2) return null;
  const W = 700, H = 140, PAD = { top: 12, right: 16, bottom: 28, left: 48 };
  const vals = data.map(d => d[yKey] || 0);
  const maxV = yMax || Math.max(...vals, 1);
  const minV = Math.min(0, Math.min(...vals));
  const range = maxV - minV || 1;
  const px = PAD.left, py = PAD.top, pw = W - PAD.left - PAD.right, ph = H - PAD.top - PAD.bottom;

  const pts = data.map((d, i) => {
    const x = px + (i / (data.length - 1)) * pw;
    const y = py + ph - ((d[yKey] - minV) / range) * ph;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const areaPath = `${px.toFixed(1)},${(py + ph).toFixed(1)} ${pts} ${(px + pw).toFixed(1)},${(py + ph).toFixed(1)}`;

  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 4, fontSize: 12, borderLeft: "3px solid #d69e2e", paddingLeft: 8 }}>{title}</div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} style={{ background: "#0c1118", borderRadius: 4 }}>
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = py + ph * (1 - pct);
          return <g key={pct}>
            <line x1={px} y1={y} x2={px + pw} y2={y} stroke="#1a2a3a" strokeWidth={0.5} />
            <text x={px - 6} y={y + 4} textAnchor="end" fill="#5a7a8a" fontSize={9}>{Math.round(minV + range * pct)}</text>
          </g>;
        })}
        <polygon points={areaPath} fill={color} opacity={0.08} />
        <polyline points={pts} fill="none" stroke={color} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
        {data.map((d, i) => {
          const x = px + (i / (data.length - 1)) * pw;
          const y = py + ph - ((d[yKey] - minV) / range) * ph;
          return <g key={i}>
            <circle cx={x} cy={y} r={4} fill="#0c1118" stroke={color} strokeWidth={2} />
            <text x={x} y={y - 10} textAnchor="middle" fill={color} fontSize={9} fontWeight={700}>{d[yKey]}</text>
          </g>;
        })}
        {data.map((d, i) => {
          const x = px + (i / (data.length - 1)) * pw;
          const label = (d.date || "").slice(5);
          return <text key={i} x={x} y={H - 6} textAnchor="middle" fill="#5a7a8a" fontSize={9}>{label}</text>;
        })}
      </svg>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Shared helper: metric box
// ═══════════════════════════════════════════════════════════

function MetricBox({ label, value, unit, color }: { label: string; value: number; unit: string; color: string }) {
  return (
    <div style={{ background: "#0c1118", borderRadius: 4, padding: "6px 10px", textAlign: "center" }}>
      <div style={{ fontSize: 9, color: "#5a7a8a", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color }}>{value}<span style={{ fontSize: 11, fontWeight: 400, marginLeft: 2 }}>{unit}</span></div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Main dispatcher
// ═══════════════════════════════════════════════════════════

export function ChartRenderer({ chart, trendData }: { chart: ChartData; trendData?: any }) {
  switch (chart.chart_type) {
    case "market_breadth": return <AnalystBreadthChart data={chart.data} interpretation={chart.interpretation} trend={trendData?.breadth} />;
    case "emotion_momentum": return <AnalystMomentumChart data={chart.data} interpretation={chart.interpretation} trend={trendData?.momentum} />;
    case "active_capital": return <AnalystCapitalChart data={chart.data} interpretation={chart.interpretation} trend={trendData?.capital} />;
    case "relay_ecology": return <AnalystRelayChart data={chart.data} interpretation={chart.interpretation} trend={trendData?.relay} />;
    case "institution_style": return <AnalystStyleTable data={chart.data} title="机构资金审美方向" interpretation={chart.interpretation} theme="institution" />;
    case "hot_money_style": return <AnalystStyleTable data={chart.data} title="游资情绪方向" interpretation={chart.interpretation} theme="hotmoney" />;
    case "limitup_classification": return <AnalystLimitUpChart data={chart.data} interpretation={chart.interpretation} />;
    default: return <pre style={{ fontSize: 10, color: "#5a7a8a" }}>{JSON.stringify(chart.data, null, 2)}</pre>;
  }
}

// ═══════════════════════════════════════════════════════════
// Chart 1: 大盘势能 — multi-day line + score gauge + metrics
// ═══════════════════════════════════════════════════════════

function AnalystBreadthChart({ data, interpretation, trend }: { data: any; interpretation: string; trend?: any[] }) {
  const up = data.up_count || 0; const down = data.down_count || 0;
  const score = data.composite_score ?? 0;
  const label = data.label || "";
  const scoreBarW = ((score + 10) / 20) * 100;
  const scoreColor = score >= 2 ? "#38a169" : score >= -5 ? "#d69e2e" : "#e53e3e";

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 8, fontSize: 13, borderLeft: "3px solid #e53e3e", paddingLeft: 8 }}>大盘势能</div>

      {/* Multi-day trend line */}
      {trend && trend.length >= 3 && <TrendLineChart title="涨停数趋势 (6/25~7/8)" data={trend} yKey="limit_up" yLabel="涨停" color="#e53e3e" />}

      {/* Score gauge */}
      <div style={{ background: "#0c1118", borderRadius: 6, padding: 10, marginBottom: 8 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
          <span style={{ fontSize: 10, color: "#5a7a8a" }}>今日综合评分</span>
          <span style={{ fontSize: 18, fontWeight: 700, color: scoreColor }}>{score}</span>
          <span style={{ fontSize: 12, color: scoreColor, fontWeight: 600 }}>{label}</span>
        </div>
        <div style={{ height: 8, background: "#1a2a3a", borderRadius: 4, overflow: "hidden" }}>
          <div style={{ width: `${Math.max(2, scoreBarW)}%`, height: "100%", background: "linear-gradient(90deg, #e53e3e, #d69e2e, #38a169)", borderRadius: 4 }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#5a7a8a", marginTop: 2 }}>
          <span>-10</span><span>0</span><span>+10</span>
        </div>
      </div>

      {/* Metrics grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 6 }}>
        <MetricBox label="涨停家数" value={data.limit_up_count || 0} unit="家" color="#e53e3e" />
        <MetricBox label="跌停家数" value={data.limit_down_count || 0} unit="家" color="#805ad5" />
        <MetricBox label="上涨" value={up} unit="家" color="#38a169" />
        <MetricBox label="下跌" value={down} unit="家" color="#e53e3e" />
      </div>

      <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.5, padding: "4px 6px", background: "#0c1118", borderRadius: 3 }}>{interpretation}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Chart 2: 情绪动能 — multi-day line + gauge + factor table
// ═══════════════════════════════════════════════════════════

function AnalystMomentumChart({ data, interpretation, trend }: { data: any; interpretation: string; trend?: any[] }) {
  const score = data.emotion_momentum_score ?? 0;
  const label = data.label || "";
  const zones = [
    { min: -18, max: -10, color: "#66d9ef", label: "冰点" },
    { min: -10, max: -5, color: "#805ad5", label: "退潮" },
    { min: -5, max: 0, color: "#dd6b20", label: "分歧" },
    { min: 0, max: 5, color: "#d69e2e", label: "正常" },
    { min: 5, max: 10, color: "#38a169", label: "活跃" },
  ];
  const factors = [
    { label: "首板红盘比", value: data.first_board_red_ratio, warn: (data.first_board_red_ratio || 0) < 0.2 },
    { label: "首板大面比", value: data.first_board_big_loss_ratio, warn: (data.first_board_big_loss_ratio || 0) > 0.3 },
    { label: "连板红盘比", value: data.chain_board_red_ratio, warn: (data.chain_board_red_ratio || 0) < 0.3 },
    { label: "连板大面比", value: data.chain_board_big_loss_ratio, warn: (data.chain_board_big_loss_ratio || 0) > 0.3 },
  ];

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 8, fontSize: 13, borderLeft: "3px solid #dd6b20", paddingLeft: 8 }}>情绪动能</div>

      {/* Multi-day trend */}
      {trend && trend.length >= 3 && <TrendLineChart title="情绪动能趋势 (6/25~7/8)" data={trend} yKey="score" yLabel="动能" color="#dd6b20" />}

      {/* Gauge */}
      <div style={{ background: "#0c1118", borderRadius: 6, padding: 10, marginBottom: 8 }}>
        <svg width={340} height={60} style={{ display: "block", margin: "0 auto" }}>
          {zones.map((z, i) => {
            const left = ((z.min + 18) / 28) * 340;
            const w = ((z.max - z.min) / 28) * 340;
            return <rect key={i} x={left} y={15} width={w} height={20} fill={z.color} opacity={0.25} rx={2} />;
          })}
          {(() => {
            const nx = ((score + 18) / 28) * 340;
            return <g>
              <line x1={nx} y1={8} x2={nx} y2={42} stroke="#ffd85e" strokeWidth={2.5} />
              <circle cx={nx} cy={25} r={6} fill="#ffd85e" />
            </g>;
          })()}
          <text x={170} y={54} textAnchor="middle" fill="#ffd85e" fontSize={13} fontWeight={700}>动能: {score.toFixed(1)}</text>
        </svg>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#5a7a8a", padding: "0 4px" }}>
          <span>-18</span><span>-10</span><span>-5</span><span>0</span><span>+5</span><span>+10</span>
        </div>
      </div>

      {/* Factor table */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, marginBottom: 6 }}>
        {factors.map((f, i) => (
          <div key={i} style={{
            padding: "4px 8px", borderRadius: 3, fontSize: 10,
            background: f.warn ? "#e53e3e15" : "#0c1118",
            border: `1px solid ${f.warn ? "#e53e3e30" : "#1a2a3a"}`,
            display: "flex", justifyContent: "space-between",
          }}>
            <span style={{ color: "#8ddcff" }}>{f.label}</span>
            <span style={{ color: f.warn ? "#e53e3e" : "#38a169", fontWeight: 600 }}>
              {f.value != null ? `${(f.value * 100).toFixed(0)}%` : "--"}
            </span>
          </div>
        ))}
      </div>

      <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.5, padding: "4px 6px", background: "#0c1118", borderRadius: 3 }}>
        {label && <span style={{ fontWeight: 600, marginRight: 6, color: score < -5 ? "#e53e3e" : "#d69e2e" }}>{label}</span>}
        {interpretation}
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Chart 3: 活跃资金成交量 — multi-day line + proportion bar
// ═══════════════════════════════════════════════════════════

function AnalystCapitalChart({ data, interpretation, trend }: { data: any; interpretation: string; trend?: any[] }) {
  const total = data.total_amount_yi || 0;
  const active = data.active_amount_yi || 0;
  const lu = data.limit_up_count || 0;
  const label = data.label || "";

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 8, fontSize: 13, borderLeft: "3px solid #66d9ef", paddingLeft: 8 }}>活跃资金成交量</div>

      {/* Multi-day trend */}
      {trend && trend.length >= 3 && <TrendLineChart title="活跃资金趋势 (6/25~7/8)" data={trend} yKey="active_yi" yLabel="亿" color="#66d9ef" />}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 8 }}>
        <MetricBox label="活跃资金" value={active} unit="亿" color="#66d9ef" />
        <MetricBox label="涨停数" value={lu} unit="家" color="#e53e3e" />
      </div>

      <div style={{ background: "#0c1118", borderRadius: 6, padding: 10, marginBottom: 6 }}>
        <div style={{ fontSize: 10, color: "#5a7a8a", marginBottom: 4 }}>活跃资金占全市场比例</div>
        <div style={{ height: 14, background: "#1a2a3a", borderRadius: 7, overflow: "hidden" }}>
          <div style={{ width: `${Math.min(100, (active / Math.max(total, 1)) * 30)}%`, height: "100%", background: "linear-gradient(90deg, #66d9ef, #38a169)", borderRadius: 7 }} />
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 9, color: "#5a7a8a", marginTop: 3 }}>
          <span>{active.toFixed(0)}亿</span>
          <span>{label}</span>
        </div>
      </div>

      <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.5, padding: "4px 6px", background: "#0c1118", borderRadius: 3 }}>{interpretation}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Chart 4: 核心板块节律 — ladder + promotion + stock names
// ═══════════════════════════════════════════════════════════

function AnalystRelayChart({ data, interpretation, trend }: { data: any; interpretation: string; trend?: any[] }) {
  const maxH = data.max_board_height || 0;
  const p1 = data.promotion_1_to_2 || 0;
  const p2 = data.promotion_2_to_3 || 0;
  const p3 = data.promotion_3_to_4 || 0;
  const fb = data.feedback_score || 0;
  const fbLabel = data.feedback_label || "";
  const label = data.label || "";
  const yesterdayCount = data.yesterday_limitup_count || 0;
  const continueRatio = data.continue_ratio || 0;

  // Get today's leaders from trend data (last entry)
  const todayLeaders = (trend && trend.length > 0) ? (trend[trend.length - 1]?.leaders || []) : [];

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 8, fontSize: 13, borderLeft: "3px solid #805ad5", paddingLeft: 8 }}>核心板块节律</div>

      {/* Multi-day board height trend */}
      {trend && trend.length >= 3 && (
        <TrendLineChart title="最高板趋势 (6/25~7/8)" data={trend} yKey="max_height" yLabel="板" color="#d69e2e" />
      )}

      {/* Ladder with stock names */}
      <div style={{ background: "#0c1118", borderRadius: 6, padding: 10, marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "flex-end", gap: 16, height: 100, justifyContent: "center" }}>
          {[1, 2, 3, 4, 5, 6, 7].map(h => {
            const active = h <= maxH;
            const barH = active ? 25 + h * 10 : 8;
            return (
              <div key={h} style={{ textAlign: "center" }}>
                {active && todayLeaders.filter((l: any) => l.height === h).map((l: any, i: number) => (
                  <div key={i} style={{ fontSize: 7, color: "#8ddcff", marginBottom: 2, whiteSpace: "nowrap" }}>{l.name}</div>
                ))}
                <div style={{
                  width: 32, height: barH,
                  background: active ? (h >= 5 ? "#38a169" : h >= 3 ? "#d69e2e" : "#66d9ef") : "#1a2a3a",
                  borderRadius: "4px 4px 0 0", margin: "0 auto 4px",
                  border: active ? "1px solid #243040" : "1px solid #1a2a3a",
                }} />
                <div style={{ fontSize: 10, color: active ? "#ffd85e" : "#5a7a8a", fontWeight: active ? 700 : 400 }}>{h}板</div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stats row */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 6, marginBottom: 6 }}>
        <div style={{ textAlign: "center", background: "#0c1118", borderRadius: 4, padding: 6 }}>
          <div style={{ fontSize: 9, color: "#5a7a8a" }}>昨涨停</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: "#8ddcff" }}>{yesterdayCount}</div>
        </div>
        <div style={{ textAlign: "center", background: "#0c1118", borderRadius: 4, padding: 6 }}>
          <div style={{ fontSize: 9, color: "#5a7a8a" }}>继续率</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: continueRatio < 0.2 ? "#e53e3e" : "#38a169" }}>{(continueRatio * 100).toFixed(0)}%</div>
        </div>
        <div style={{ textAlign: "center", background: "#0c1118", borderRadius: 4, padding: 6 }}>
          <div style={{ fontSize: 9, color: "#5a7a8a" }}>反馈</div>
          <div style={{ fontSize: 16, fontWeight: 700, color: fb < -20 ? "#e53e3e" : "#38a169" }}>{fbLabel}</div>
        </div>
      </div>

      {/* Promotion rates */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 4, marginBottom: 6 }}>
        <PromoBox label="一进二" value={p1} color="#38a169" />
        <PromoBox label="二进三" value={p2} color="#d69e2e" />
        <PromoBox label="三进四" value={p3} color="#dd6b20" />
      </div>

      <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.5, padding: "4px 6px", background: "#0c1118", borderRadius: 3 }}>
        <span style={{ fontWeight: 600, marginRight: 6, color: "#e53e3e" }}>{label}</span>
        {interpretation}
      </div>
    </div>
  );
}

function PromoBox({ label, value, color }: { label: string; value: number; color: string }) {
  const pct = (value * 100).toFixed(0);
  const warn = value < 0.1;
  return (
    <div style={{
      textAlign: "center", padding: "6px 4px", borderRadius: 4,
      background: warn ? "#e53e3e10" : "#0c1118",
      border: `1px solid ${warn ? "#e53e3e30" : "#1a2a3a"}`,
    }}>
      <div style={{ fontSize: 9, color: "#5a7a8a", marginBottom: 2 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 700, color: warn ? "#e53e3e" : color }}>{pct}%</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Chart 5/6: 机构资金 / 游资方向
// ═══════════════════════════════════════════════════════════

function AnalystStyleTable({ data, title, interpretation, theme }: { data: any; title: string; interpretation: string; theme: string }) {
  const dirs: { name: string; state: string; score?: number }[] = data.directions || [];
  const stateStyle = (state: string) => {
    if (state.includes("调整") || state.includes("退潮")) return { bg: "#e53e3e15", border: "#e53e3e30", dot: "#e53e3e", color: "#e53e3e" };
    if (state.includes("启动") || state.includes("修复") || state.includes("关注")) return { bg: "#38a16915", border: "#38a16930", dot: "#38a169", color: "#38a169" };
    if (state.includes("观察") || state.includes("跟踪")) return { bg: "#d69e2e15", border: "#d69e2e30", dot: "#d69e2e", color: "#d69e2e" };
    return { bg: "#1a2a3a", border: "#243040", dot: "#5a7a8a", color: "#5a7a8a" };
  };

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 8, fontSize: 13, borderLeft: `3px solid ${theme === "institution" ? "#d69e2e" : "#dd6b20"}`, paddingLeft: 8 }}>
        {title}
        <span style={{ fontSize: 10, color: "#5a7a8a", fontWeight: 400, marginLeft: 8 }}>{data.label}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 3, marginBottom: 8 }}>
        {dirs.map((d, i) => {
          const s = stateStyle(d.state);
          return (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 8px", borderRadius: 3, fontSize: 10, background: s.bg, border: `1px solid ${s.border}` }}>
              <span style={{ color: "#8ddcff" }}>{d.name}</span>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: s.dot, display: "inline-block" }} />
                <span style={{ color: s.color, fontWeight: 600 }}>{d.state}</span>
              </div>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.5, padding: "4px 6px", background: "#0c1118", borderRadius: 3 }}>{interpretation}</div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════
// Chart 7: 涨停分类
// ═══════════════════════════════════════════════════════════

function AnalystLimitUpChart({ data, interpretation }: { data: any; interpretation: string }) {
  const cats: Record<string, string[]> = data.categories || {};
  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 8, fontSize: 13, borderLeft: "3px solid #38a169", paddingLeft: 8 }}>
        涨停股分类 <span style={{ fontSize: 16, color: "#e53e3e", fontWeight: 700, marginLeft: 8 }}>{data.limit_up_count || 0}家</span>
      </div>
      {/* Filter garbage theme names (pure numbers, ids starting with digits) */}
      {(() => {
        const clean = (s: string) => !/^\d+$/.test(s) && !s.startsWith("90") && s.length < 20;
        const validCats = Object.fromEntries(
          Object.entries(cats).filter(([k]) => clean(k)).slice(0, 6)
        );
        return Object.keys(validCats).length > 0 && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, marginBottom: 8 }}>
            {Object.entries(validCats).map(([cat, names]) => (
              <div key={cat} style={{ padding: 8, background: "#0c1118", borderRadius: 4, border: "1px solid #1a2a3a" }}>
                <div style={{ fontSize: 11, fontWeight: 600, color: "#d69e2e", marginBottom: 4, paddingBottom: 4, borderBottom: "1px solid #1a2a3a" }}>
                  {cat} <span style={{ fontSize: 10, color: "#5a7a8a", fontWeight: 400 }}>({(names as string[]).length})</span>
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
              {(names as string[]).slice(0, 6).map((n, i) => (
                <span key={i} style={{ fontSize: 9, color: "#8ddcff", padding: "2px 6px", background: "#111720", borderRadius: 3, border: "1px solid #1a2a3a" }}>{n}</span>
              ))}
            </div>
        );
      })()}
      {interpretation && <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.5, padding: "4px 6px", background: "#0c1118", borderRadius: 3, marginTop: 4 }}>{interpretation}</div>}
    </div>
  );
}
