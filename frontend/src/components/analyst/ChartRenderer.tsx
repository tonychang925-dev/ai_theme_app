import React from "react";

interface ChartData {
  chart_id: string; trade_date: string; chart_type: string;
  title: string; data: Record<string, any>; interpretation: string;
}

// ── Multi-day Trend Chart ──

interface TrendPoint { date: string; [key: string]: any; }

export function TrendLineChart({ title, data, yKey, yLabel, color, yMax }: {
  title: string; data: TrendPoint[]; yKey: string; yLabel: string; color: string; yMax?: number;
}) {
  if (!data || data.length < 2) return null;
  const W2 = 360, H2 = 140;
  const values = data.map(d => d[yKey] || 0);
  const maxV = yMax || Math.max(...values, 1);
  const minV = Math.min(...values, 0);
  const range = maxV - minV || 1;
  const px = PAD.left, py = PAD.top, pw = W2 - PAD.left - PAD.right, ph = H2 - PAD.top - PAD.bottom;

  const pts = data.map((d, i) => {
    const x = px + (i / (data.length - 1)) * pw;
    const y = py + ph - ((d[yKey] - minV) / range) * ph;
    return `${x},${y}`;
  }).join(" ");

  // Fill area under line
  const fillPts = `${px},${py + ph} ${pts} ${px + pw},${py + ph}`;

  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 4, fontSize: 12 }}>{title}</div>
      <svg width={W2} height={H2} style={{ background: "#0c1118" }}>
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = py + ph * (1 - pct);
          return <g key={pct}>
            <line x1={px} y1={y} x2={px + pw} y2={y} stroke="#1a2a3a" strokeWidth={0.5} />
            <text x={px - 4} y={y + 4} textAnchor="end" fill="#5a7a8a" fontSize={8}>{Math.round(minV + range * pct)}</text>
          </g>;
        })}
        {/* Area fill */}
        <polygon points={fillPts} fill={color} opacity={0.1} />
        {/* Line */}
        <polyline points={pts} fill="none" stroke={color} strokeWidth={2} />
        {/* Dots */}
        {data.map((d, i) => {
          const x = px + (i / (data.length - 1)) * pw;
          const y = py + ph - ((d[yKey] - minV) / range) * ph;
          return <g key={i}>
            <circle cx={x} cy={y} r={4} fill={color} />
            <text x={x} y={y - 8} textAnchor="middle" fill={color} fontSize={9} fontWeight={600}>{d[yKey]}</text>
          </g>;
        })}
        {/* X labels */}
        {data.map((d, i) => {
          const x = px + (i / (data.length - 1)) * pw;
          const label = (d.date || "").slice(5); // MM-DD
          return <text key={i} x={x} y={H2 - 4} textAnchor="middle" fill="#5a7a8a" fontSize={8}>{label}</text>;
        })}
      </svg>
    </div>
  );
}

export function ChartRenderer({ chart }: { chart: ChartData }) {
  switch (chart.chart_type) {
    case "market_breadth": return <BreadthChart data={chart.data} title={chart.title} interpretation={chart.interpretation} />;
    case "emotion_momentum": return <MomentumChart data={chart.data} title={chart.title} interpretation={chart.interpretation} />;
    case "active_capital": return <CapitalChart data={chart.data} title={chart.title} interpretation={chart.interpretation} />;
    case "relay_ecology": return <RelayChart data={chart.data} title={chart.title} interpretation={chart.interpretation} />;
    case "institution_style": return <StyleTable data={chart.data} title="机构资金审美方向" interpretation={chart.interpretation} />;
    case "hot_money_style": return <StyleTable data={chart.data} title="游资情绪方向" interpretation={chart.interpretation} />;
    case "limitup_classification": return <LimitUpChart data={chart.data} title={chart.title} interpretation={chart.interpretation} />;
    default: return <pre style={{ fontSize: 10, color: "#5a7a8a" }}>{JSON.stringify(chart.data, null, 2)}</pre>;
  }
}

// ── SVG chart helpers ──
const W = 340, H = 140, PAD = { top: 10, right: 10, bottom: 25, left: 45 };
const PLOT_W = W - PAD.left - PAD.right, PLOT_H = H - PAD.top - PAD.bottom;

function BarChart({ title, bars, yMax, yLabel, colorMap }: {
  title: string; bars: { label: string; value: number; color: string }[];
  yMax: number; yLabel?: string; colorMap?: Record<string, string>;
}) {
  const n = bars.length;
  const barW = Math.max(8, Math.min(50, (PLOT_W - n * 8) / n));
  const gap = (PLOT_W - barW * n) / (n + 1);

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 4, fontSize: 13 }}>{title}</div>
      <svg width={W} height={H} style={{ background: "#0c1118" }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(pct => {
          const y = PAD.top + PLOT_H * (1 - pct);
          return <g key={pct}>
            <line x1={PAD.left} y1={y} x2={W - PAD.right} y2={y} stroke="#1a2a3a" strokeWidth={0.5} />
            <text x={PAD.left - 4} y={y + 4} textAnchor="end" fill="#5a7a8a" fontSize={9}>{Math.round(yMax * pct)}</text>
          </g>;
        })}
        {/* Bars */}
        {bars.map((b, i) => {
          const h = (b.value / yMax) * PLOT_H;
          const x = PAD.left + gap + i * (barW + gap);
          const y = PAD.top + PLOT_H - h;
          const color = (colorMap && colorMap[b.label]) || b.color;
          return (
            <g key={i}>
              <rect x={x} y={y} width={barW} height={Math.max(1, h)} fill={color} rx={1} />
              <text x={x + barW / 2} y={y - 4} textAnchor="middle" fill={color} fontSize={9} fontWeight={600}>{b.value > 0 ? b.value : ""}</text>
              <text x={x + barW / 2} y={H - 6} textAnchor="middle" fill="#8ddcff" fontSize={8}>{b.label}</text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// ── 1. Market Breadth ──

function BreadthChart({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  const up = data.up_count || 0; const down = data.down_count || 0;
  const lu = data.limit_up_count || 0; const ld = data.limit_down_count || 0;
  const bars = [
    { label: "上涨", value: up, color: "#38a169" },
    { label: "下跌", value: down, color: "#e53e3e" },
    { label: "涨停", value: lu, color: "#e53e3e" },
    { label: "跌停", value: ld, color: "#805ad5" },
  ];
  return (
    <div>
      <BarChart title={title} bars={bars} yMax={Math.max(up, down, lu, ld, 100)} />
      <div style={{ marginTop: 4, fontSize: 10, color: "#5a7a8a" }}>
        {interpretation || `上涨比${(up/(up+down||1)*100).toFixed(0)}%，涨停${lu}家`}
        {data.turnover_yi > 0 && ` · 成交${data.turnover_yi}万亿`}
        {data.label && ` · ${data.label}`}
        {data.pdf_emotion && <span style={{ color: "#d69e2e" }}> · PDF: {data.pdf_emotion}</span>}
      </div>
    </div>
  );
}

// ── 2. Emotion Momentum Trend ──

function MomentumChart({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 4, fontSize: 13 }}>{title}</div>
      <svg width={W} height={H} style={{ background: "#0c1118" }}>
        {/* Gauge background */}
        <rect x={PAD.left} y={PAD.top + PLOT_H / 2 - 10} width={PLOT_W} height={20} rx={10} fill="#1a2a3a" />
        {/* Color zones */}
        {[
          { pct: 0, color: "#66d9ef", label: "冰点" },
          { pct: 0.15, color: "#805ad5", label: "退潮" },
          { pct: 0.3, color: "#dd6b20", label: "分歧" },
          { pct: 0.5, color: "#d69e2e", label: "正常" },
          { pct: 0.7, color: "#38a169", label: "活跃" },
        ].map((z, i) => (
          <rect key={i} x={PAD.left + PLOT_W * z.pct} y={PAD.top + PLOT_H / 2 - 10} width={PLOT_W * 0.2} height={20} fill={z.color} opacity={0.3} />
        ))}
        {/* Needle */}
        {(() => {
          const pct = Math.max(0, Math.min(1, (data.emotion_momentum_score + 18) / 28));
          const nx = PAD.left + PLOT_W * pct;
          const ny = PAD.top + PLOT_H / 2;
          return <line x1={nx} y1={ny - 18} x2={nx} y2={ny + 18} stroke="#ffd85e" strokeWidth={2} />;
        })()}
        {/* Labels */}
        {["-18", "-10", "-5", "0", "+5", "+10"].map((l, i) => (
          <text key={i} x={PAD.left + PLOT_W * (i / 5)} y={H - 4} textAnchor="middle" fill="#5a7a8a" fontSize={8}>{l}</text>
        ))}
      </svg>
      <div style={{ display: "flex", gap: 16, marginTop: 4, flexWrap: "wrap" }}>
        <span style={{ fontSize: 11, color: "#ffd85e" }}>动能: {data.emotion_momentum_score?.toFixed(1) || "-"}</span>
        <span style={{ fontSize: 11, color: "#38a169" }}>首板红盘: {(data.first_board_red_ratio * 100).toFixed(0)}%</span>
        <span style={{ fontSize: 11, color: "#e53e3e" }}>大面: {(data.first_board_big_loss_ratio * 100).toFixed(0)}%</span>
        {data.label && <span style={{ fontSize: 11, color: "#66d9ef" }}>{data.label}</span>}
      </div>
      <div style={{ fontSize: 10, color: "#5a7a8a", marginTop: 2 }}>{interpretation}</div>
    </div>
  );
}

// ── 3. Active Capital ──

function CapitalChart({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  const total = data.total_amount_wan_yi || 0;
  const active = data.active_amount_wan_yi || 0;
  const lu = data.limit_up_count || 0;

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 4, fontSize: 13 }}>{title}</div>
      <svg width={W} height={80} style={{ background: "#0c1118" }}>
        <rect x={PAD.left} y={20} width={PLOT_W} height={24} rx={3} fill="#1a2a3a" />
        <rect x={PAD.left} y={20} width={PLOT_W * Math.min(1, active / Math.max(total, 1) * 20)} height={24} rx={3} fill="#66d9ef" opacity={0.7} />
        <text x={PAD.left + 8} y={36} fill="#fff" fontSize={10} fontWeight={600}>活跃 {active}万亿</text>
        <text x={W - PAD.right} y={36} textAnchor="end" fill="#5a7a8a" fontSize={9}>全市场 {total}万亿</text>
      </svg>
      <div style={{ display: "flex", gap: 16, marginTop: 4 }}>
        <span style={{ fontSize: 11, color: "#66d9ef" }}>涨停: {lu}家</span>
        <span style={{ fontSize: 11, color: "#5a7a8a" }}>{interpretation}</span>
      </div>
    </div>
  );
}

// ── 4. Relay Ecology Ladder ──

function RelayChart({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  const h = data.max_board_height || 0;
  const p1 = data.promotion_1_to_2 || 0;
  const p2 = data.promotion_2_to_3 || 0;
  const p3 = data.promotion_3_to_4 || 0;

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 4, fontSize: 13 }}>{title}</div>
      <svg width={W} height={H} style={{ background: "#0c1118" }}>
        {/* Ladder steps */}
        {[1, 2, 3, 4, 5].map((step, i) => {
          const y = PAD.top + PLOT_H - (step / 5) * PLOT_H;
          return (
            <g key={i}>
              <rect x={PAD.left} y={y - 8} width={PLOT_W - 40} height={16} rx={2} fill={step <= h ? "#e53e3e20" : "#1a2a3a"} stroke={step <= h ? "#e53e3e" : "#243040"} strokeWidth={0.5} />
              <text x={PAD.left + 6} y={y + 4} fill={step <= h ? "#e53e3e" : "#5a7a8a"} fontSize={10} fontWeight={step <= h ? 700 : 400}>{step}板</text>
            </g>
          );
        })}
        {/* Promotion rates on right */}
        <text x={W - PAD.right} y={PAD.top + PLOT_H * 0.2} textAnchor="end" fill="#38a169" fontSize={9}>1→2: {(p1 * 100).toFixed(0)}%</text>
        <text x={W - PAD.right} y={PAD.top + PLOT_H * 0.4} textAnchor="end" fill="#d69e2e" fontSize={9}>2→3: {(p2 * 100).toFixed(0)}%</text>
        <text x={W - PAD.right} y={PAD.top + PLOT_H * 0.6} textAnchor="end" fill="#dd6b20" fontSize={9}>3→4: {(p3 * 100).toFixed(0)}%</text>
      </svg>
      <div style={{ fontSize: 10, color: "#5a7a8a", marginTop: 2 }}>
        最高{h}板 · 封板率{(data.first_board_success_rate * 100).toFixed(0)}% · {data.label || interpretation}
      </div>
    </div>
  );
}

// ── 5/6. Institution / Hot Money Style ──

function StyleTable({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  const dirs: { name: string; state: string; score?: number; inflow?: number }[] = data.directions || [];
  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 6, fontSize: 13 }}>
        {title} <span style={{ fontSize: 10, color: "#5a7a8a", fontWeight: 400 }}>{data.label}{data.market_mode ? ` · ${data.market_mode}` : ""}</span>
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(150px, 1fr))", gap: 4 }}>
        {dirs.map((d, i) => {
          const isNeg = d.state.includes("调整") || d.state.includes("退潮") || d.state.includes("暂未");
          const isPos = d.state.includes("修复") || d.state.includes("启动") || d.state.includes("趋势") || d.state.includes("关注");
          return (
            <div key={i} style={{
              padding: "4px 8px", borderRadius: 3, fontSize: 10,
              background: isNeg ? "#e53e3e15" : isPos ? "#38a16915" : "#1a2a3a",
              border: `1px solid ${isNeg ? "#e53e3e30" : isPos ? "#38a16930" : "#243040"}`,
              display: "flex", justifyContent: "space-between",
            }}>
              <span style={{ color: "#8ddcff" }}>{d.name}</span>
              <span style={{ color: isNeg ? "#e53e3e" : isPos ? "#38a169" : "#5a7a8a", fontWeight: 600 }}>{d.state}</span>
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 10, color: "#5a7a8a", marginTop: 4 }}>{interpretation}</div>
    </div>
  );
}

// ── 7. Limit-up Classification ──

function LimitUpChart({ data, title, interpretation }: { data: any; title: string; interpretation: string }) {
  const cats: Record<string, string[]> = data.categories || {};
  const stocks: { name: string; theme: string; role: string }[] = data.top_stocks || [];

  return (
    <div style={{ fontSize: 12 }}>
      <div style={{ fontWeight: 600, color: "#ffd85e", marginBottom: 6, fontSize: 13 }}>
        {title} <span style={{ fontSize: 14, color: "#e53e3e" }}>{data.limit_up_count}家</span>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
        {Object.entries(cats).map(([cat, names]) => (
          <div key={cat} style={{ padding: "6px 10px", background: "#111720", borderRadius: 4, border: "1px solid #243040", minWidth: 140 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#d69e2e", marginBottom: 4 }}>{cat} ({(names as string[]).length})</div>
            {(names as string[]).map((n, i) => (
              <div key={i} style={{ fontSize: 10, color: "#8ddcff", padding: "1px 0" }}>{n}</div>
            ))}
          </div>
        ))}
      </div>
      {stocks.length > 0 && (
        <div style={{ marginTop: 6, fontSize: 10, color: "#5a7a8a" }}>
          龙头股: {stocks.slice(0, 6).map((s, i) => <span key={i} style={{ marginRight: 8, color: "#e53e3e" }}>{s.name}({s.role})</span>)}
        </div>
      )}
      <div style={{ fontSize: 10, color: "#5a7a8a", marginTop: 4 }}>{interpretation}</div>
    </div>
  );
}
