import React, { useEffect, useState } from "react";
import { ChartRenderer, TrendLineChart } from "./ChartRenderer";

interface EvidenceArtifact {
  artifact_id: string;
  trade_date: string;
  artifact_type: string;
  title: string;
  source: string;
  related_module: string;
  page_no?: number;
  extracted_metrics?: Record<string, any>;
  summary: string;
}

interface EmotionState {
  trade_date: string;
  emotion_node: string;
  emotion_desc: string;
  emotion_score: number;
  breadth_score: number; breadth_label: string;
  momentum_score: number; momentum_label: string;
  relay_score: number; relay_label: string;
  capital_score: number; capital_label: string;
  style_score: number; style_label: string;
  key_evidence: string[];
  strategy_bias: string;
  raw: Record<string, number | string>;
}

const NODE_COLORS: Record<string, string> = {
  CLIMAX: "#e53e3e", ACCELERATION: "#dd6b20", FERMENTATION: "#d69e2e",
  REPAIR: "#38a169", DIVERGENCE: "#3182ce", FADE: "#805ad5",
  ICE_POINT: "#66d9ef", CHAOS: "#5a7a8a",
};
const NODE_ICONS: Record<string, string> = {
  CLIMAX: "🔥", ACCELERATION: "⚡", FERMENTATION: "🌱",
  REPAIR: "🔧", DIVERGENCE: "⚔️", FADE: "📉",
  ICE_POINT: "❄️", CHAOS: "🌫️",
};
const NODE_LABELS: Record<string, string> = {
  CLIMAX: "情绪高潮", ACCELERATION: "情绪加速", FERMENTATION: "情绪发酵",
  REPAIR: "情绪修复", REBOUND: "反弹修复", DIVERGENCE: "情绪退潮",
  FADE: "情绪衰退", ICE_POINT: "情绪冰点", CHAOS: "情绪混沌",
  ACCELERATING: "加速中", PEAKING: "见顶", EXHAUSTING: "衰竭",
  HEALTHY: "健康", FORCED: "受压", PANIC: "恐慌",
};

function Stars({ count }: { count: number }) {
  const full = Math.round(count);
  return <span style={{ fontSize: 12, letterSpacing: 1 }}>{"★".repeat(full)}{"☆".repeat(5 - full)}</span>;
}

// ── Trend data helper ──
function useEmotionTrend(tradeDate: string) {
  const [trend, setTrend] = useState<{ date: string; node: string; score: number }[]>([]);

  useEffect(() => {
    // Load from static trend.json — instant, no API calls
    fetch(`/api/analyst-charts/trend.json`)
      .then(r => r.json())
      .then(data => {
        const scores = (data.momentum || []).map((m: any) => ({
          date: m.date, score: m.score,
          node: m.score < -10 ? "ICE_POINT" : m.score < -5 ? "FADE" : m.score < 0 ? "DIVERGENCE" : m.score > 5 ? "CLIMAX" : m.score > 0 ? "FERMENTATION" : "CHAOS",
        }));
        setTrend(scores);
      })
      .catch(() => setTrend([]));
  }, [tradeDate]);

  return trend;
}

// ── Main Component ──
export function EmotionDashboard({ tradeDate, tomorrowOutlook, tomorrowWatchpoints, tomorrowForbidden }: {
  tradeDate: string;
  tomorrowOutlook?: string;
  tomorrowWatchpoints?: string[];
  tomorrowForbidden?: string[];
}) {
  const [emotion, setEmotion] = useState<EmotionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]);
  const [showEvidence, setShowEvidence] = useState(false);
  const [systemCharts, setSystemCharts] = useState<any[]>([]);
  const [multiTrend, setMultiTrend] = useState<any>(null);
  const trend = useEmotionTrend(tradeDate);

  // Auto-load chart data when date changes (not just on expand)
  // NOTE: do NOT use an async function as the effect itself — React
  // expects a synchronous cleanup function, but async always returns a Promise.
  useEffect(() => {
    const ctrl = new AbortController();

    fetch(`/api/analyst-charts/trend.json`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => setMultiTrend(data))
      .catch(() => setMultiTrend(null));

    fetch(`/api/analyst-charts/${tradeDate}.json`, { signal: ctrl.signal })
      .then(r => r.ok ? r.json() : Promise.reject())
      .then(data => {
        if (Array.isArray(data) && data.length > 0) setSystemCharts(data);
        else setSystemCharts([]);
      })
      .catch(() => setSystemCharts([]));

    return () => ctrl.abort();
  }, [tradeDate]);


  useEffect(() => {
    setLoading(true);
    setEmotion(null);
    const ctrl = new AbortController();
    (async () => {
      // Prefer calibrated data from workbench, merge raw data from static JSON
      try {
        const [drResp, staticResp] = await Promise.all([
          fetch(`/api/v2/daily-review-v2?date=${encodeURIComponent(tradeDate)}`, { signal: ctrl.signal }),
          fetch(`/api/emotion-${tradeDate}.json`, { signal: ctrl.signal }).catch(() => null),
        ]);
        if (drResp.ok) {
          const dr = await drResp.json();
          const er = dr.emotion_review;
          if (er && er.emotion_node) {
            const raw = (staticResp && (staticResp as Response).ok)
              ? await (staticResp as Response).json().then((d: any) => d.raw || d).catch(() => ({}))
              : {};
            setEmotion({
              trade_date: tradeDate,
              emotion_node: er.emotion_node,
              emotion_desc: er.summary || "",
              emotion_score: er.emotion_score || 0,
              breadth_score: er.breadth_score || 0, breadth_label: er.breadth_label || "",
              momentum_score: er.momentum_score || 0, momentum_label: er.momentum_label || "",
              relay_score: er.relay_score || 0, relay_label: er.relay_label || "",
              capital_score: er.capital_score || 0, capital_label: er.capital_label || "",
              style_score: er.style_score || 0, style_label: er.style_label || "",
              key_evidence: er.key_evidence || [],
              strategy_bias: er.strategy_bias || "",
              raw: raw as any,
            } as EmotionState);
            setLoading(false);
            return;
          }
        }
      } catch { /* fall through to static JSON */ }

      try {
        const resp = await fetch(`/api/emotion-${tradeDate}.json`, { signal: ctrl.signal });
        if (resp.ok) {
          const d = await resp.json();
          if (d && d.emotion_node) { setEmotion(d); setLoading(false); return; }
        }
      } catch { /* missing file OK */ }
      setLoading(false);
    })();

    return () => ctrl.abort();
  }, [tradeDate]);

  if (loading) return <div style={{ padding: "8px 16px", color: "#5a7a8a", fontSize: 13 }}>加载情绪数据…</div>;
  if (!emotion || !emotion.emotion_node) return <div style={{ padding: "8px 16px", color: "#ffa940", fontSize: 13 }}>该日期暂无数据，请点击「启动分析」生成</div>;

  const node = emotion.emotion_node || "CHAOS";
  const color = NODE_COLORS[node] || "#5a7a8a";
  const raw = emotion.raw || {};
  const evidence = emotion.key_evidence || [];

  // ── Trading mode derivation ──
  const allowedActions: string[] = [];
  const forbiddenActions: string[] = [];
  if (node === "ICE_POINT" || (node === "DIVERGENCE" && emotion.emotion_score < -20)) {
    allowedActions.push("首板试错", "新题材观察", "低吸"); forbiddenActions.push("高位接力", "追龙头", "打连板");
  } else if (node === "DIVERGENCE" || node === "FADE") {
    allowedActions.push("首板", "低吸", "观察"); forbiddenActions.push("接力", "追高", "重仓");
  } else if (node === "REPAIR" || node === "FERMENTATION") {
    allowedActions.push("龙头", "趋势", "首板"); forbiddenActions.push("追高");
  } else if (node === "ACCELERATION" || node === "CLIMAX") {
    allowedActions.push("低位补涨", "趋势"); forbiddenActions.push("追龙头", "高位接力");
  } else {
    allowedActions.push("观察", "轻仓"); forbiddenActions.push("重仓", "追高");
  }

  // ── Next-day probability (heuristic from trend) ──
  const scores = trend.map(t => t.score);
  const lastScore = scores[scores.length - 1] || 0;
  const prevScore = scores[scores.length - 2] || 0;
  const delta = lastScore - prevScore;
  const repairProb = Math.max(5, Math.min(80, 40 + delta * 0.5));
  const continueProb = Math.max(10, Math.min(70, 50 - delta * 0.3));
  const worsenProb = 100 - repairProb - continueProb;

  return (
    <div style={{ background: "#0c1118", padding: "10px 16px 12px 16px" }}>

      {/* ── Row 1: Main Emotion + Key Metrics ── */}
      <div style={{ display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap" }}>
        {/* Emotion Node */}
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 180 }}>
          <span style={{ fontSize: 28 }}>{NODE_ICONS[node] || ""}</span>
          <div>
            <div style={{ fontSize: 18, fontWeight: 800, color }}>{NODE_LABELS[node] || node}</div>
            <div style={{ fontSize: 11, color: "#5a7a8a" }}>{node}</div>
          </div>
        </div>

        {/* Score gauge */}
        <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 100 }}>
          <span style={{ fontSize: 24, fontWeight: 800, color }}>{emotion.emotion_score}</span>
          <span style={{ fontSize: 11, color: "#5a7a8a" }}>/ 100</span>
        </div>

        <div style={{ width: 1, height: 40, background: "#243040" }} />

        {/* Quick metrics */}
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "center" }}>
          {raw.limit_up !== undefined && (
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: "#e53e3e" }}>{raw.limit_up}</div>
              <div style={{ fontSize: 10, color: "#5a7a8a" }}>涨停</div>
            </div>
          )}
          {(raw.turnover_wan_yi !== undefined || raw.turnover_yi !== undefined) && (
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: "#d69e2e" }}>{raw.turnover_wan_yi || raw.turnover_yi}万亿</div>
              <div style={{ fontSize: 10, color: "#5a7a8a" }}>成交额</div>
            </div>
          )}
          {raw.up_count !== undefined && (
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: emotion.breadth_score > 0 ? "#38a169" : "#e53e3e" }}>{raw.up_count}/{raw.down_count}</div>
              <div style={{ fontSize: 10, color: "#5a7a8a" }}>涨跌比</div>
            </div>
          )}
        </div>

        <div style={{ width: 1, height: 40, background: "#243040" }} />

        {/* Star ratings */}
        <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
          <div style={{ textAlign: "center" }}>
            <Stars count={emotion.breadth_score > 30 ? 4 : emotion.breadth_score > 0 ? 3 : emotion.breadth_score > -30 ? 2 : 1} />
            <div style={{ fontSize: 10, color: "#5a7a8a" }}>赚钱效应</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <Stars count={emotion.momentum_score > 30 ? 4 : emotion.momentum_score > 0 ? 3 : emotion.momentum_score > -30 ? 2 : 1} />
            <div style={{ fontSize: 10, color: "#5a7a8a" }}>游资情绪</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <Stars count={emotion.style_score > 20 ? 4 : emotion.style_score > 0 ? 3 : 1} />
            <div style={{ fontSize: 10, color: "#5a7a8a" }}>机构趋势</div>
          </div>
          <div style={{ textAlign: "center" }}>
            <Stars count={emotion.emotion_score < -30 ? 4 : emotion.emotion_score < -10 ? 3 : 2} />
            <div style={{ fontSize: 10, color: "#e53e3e" }}>风险等级</div>
          </div>
        </div>
      </div>

      {/* ── Row 2: Trend Timeline ── */}
      <div style={{ marginTop: 10, display: "flex", alignItems: "center", gap: 4, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, color: "#5a7a8a", minWidth: 50 }}>5日趋势</span>
        {trend.map((t, i) => {
          const c = NODE_COLORS[t.node] || "#5a7a8a";
          const isLast = i === trend.length - 1;
          return (
            <React.Fragment key={t.date}>
              <div title={`${t.date}: ${t.node} (${t.score})`}
                style={{
                  width: isLast ? 16 : 10, height: isLast ? 16 : 10,
                  borderRadius: "50%", background: c,
                  border: isLast ? `2px solid ${c}` : "none",
                  cursor: "pointer", transition: "0.2s",
                }} />
              {i < trend.length - 1 && <div style={{ width: 20, height: 2, background: "#243040" }} />}
            </React.Fragment>
          );
        })}
        <span style={{ fontSize: 10, color: "#5a7a8a", marginLeft: 8 }}>
          {trend.map(t => NODE_LABELS[t.node] || t.node).join(" → ")}
        </span>
      </div>

      {/* ── Row 3: Why + Next Prob + Trading + Tomorrow (4 equal cols) ── */}
      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 1fr 1fr 1fr", gap: 10 }}>

        {/* Why Panel */}
        <div style={{ padding: 8, background: "#111720", borderRadius: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#8ddcff", marginBottom: 4 }}>为什么是{NODE_LABELS[node] || node}？</div>
          {evidence.map((ev, i) => (
            <div key={i} style={{ fontSize: 11, color: "#5a7a8a", padding: "1px 0" }}>✓ {ev}</div>
          ))}
          <div style={{ marginTop: 4, fontSize: 10, color: "#39ff14" }}>
            Confidence {Math.max(60, 100 + emotion.emotion_score)}%
          </div>
        </div>

        {/* Next Probability */}
        <div style={{ padding: 10, background: "#111720", borderRadius: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#ffd85e", marginBottom: 8 }}>明日预测</div>
          <div style={{ marginBottom: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
              <span style={{ color: "#38a169" }}>修复</span><span style={{ color: "#8ddcff" }}>{Math.round(repairProb)}%</span>
            </div>
            <div style={{ height: 4, background: "#1a2a3a", borderRadius: 2, marginTop: 2 }}>
              <div style={{ width: `${repairProb}%`, height: "100%", background: "#38a169", borderRadius: 2 }} />
            </div>
          </div>
          <div style={{ marginBottom: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
              <span style={{ color: "#d69e2e" }}>持续</span><span style={{ color: "#8ddcff" }}>{Math.round(continueProb)}%</span>
            </div>
            <div style={{ height: 4, background: "#1a2a3a", borderRadius: 2, marginTop: 2 }}>
              <div style={{ width: `${continueProb}%`, height: "100%", background: "#d69e2e", borderRadius: 2 }} />
            </div>
          </div>
          <div style={{ marginBottom: 4 }}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11 }}>
              <span style={{ color: "#e53e3e" }}>恶化</span><span style={{ color: "#8ddcff" }}>{Math.round(worsenProb)}%</span>
            </div>
            <div style={{ height: 4, background: "#1a2a3a", borderRadius: 2, marginTop: 2 }}>
              <div style={{ width: `${worsenProb}%`, height: "100%", background: "#e53e3e", borderRadius: 2 }} />
            </div>
          </div>
        </div>

        {/* Trading Mode */}
        <div style={{ padding: 10, background: "#111720", borderRadius: 4 }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#66d9ef", marginBottom: 8 }}>今日交易模式</div>
          <div style={{ marginBottom: 6 }}>
            <div style={{ fontSize: 10, color: "#39ff14", marginBottom: 3 }}>✓ 允许</div>
            {allowedActions.map(a => (
              <span key={a} style={{ fontSize: 11, color: "#39ff14", background: "#39ff1420", padding: "1px 6px", borderRadius: 3, marginRight: 4 }}>{a}</span>
            ))}
          </div>
          <div>
            <div style={{ fontSize: 10, color: "#e53e3e", marginBottom: 3 }}>✗ 禁止</div>
            {forbiddenActions.map(a => (
              <span key={a} style={{ fontSize: 11, color: "#e53e3e", background: "#e53e3e20", padding: "1px 6px", borderRadius: 3, marginRight: 4 }}>{a}</span>
            ))}
          </div>
        </div>

        {/* Tomorrow Outlook */}
        <div style={{ padding: 10, background: "#111720", borderRadius: 4, overflow: "auto" }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#ffd85e", marginBottom: 6 }}>📋 明日操作提示</div>
          {tomorrowOutlook ? (
            <div style={{ fontSize: 11, color: "#8ddcff", marginBottom: 6, lineHeight: 1.5 }}>
              {tomorrowOutlook}
            </div>
          ) : (
            <div style={{ fontSize: 10, color: "#5a7a8a" }}>暂无明日预判</div>
          )}
          {tomorrowWatchpoints.length > 0 && (
            <div style={{ marginBottom: 3 }}>
              {tomorrowWatchpoints.slice(0, 3).map((wp, i) => (
                <div key={i} style={{ fontSize: 10, color: "#8ddcff", padding: "1px 0" }}>• {wp}</div>
              ))}
            </div>
          )}
          {tomorrowForbidden.length > 0 && (
            <div>
              {tomorrowForbidden.slice(0, 2).map((fb, i) => (
                <span key={i} style={{ fontSize: 10, color: "#fca5a5", background: "#e53e3e15", padding: "1px 5px", borderRadius: 3, marginRight: 4 }}>✗ {fb}</span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ── Evidence Charts (collapsible) ── */}
      <div style={{ marginTop: 10 }}>
        <div
          onClick={() => setShowEvidence(!showEvidence)}
          style={{ fontSize: 11, color: "#5a7a8a", cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
          <span>{showEvidence ? "▼" : "▶"} 分析师图表 Evidence Charts</span>
          {(artifacts.length + systemCharts.length) > 0 && <span style={{ color: "#66d9ef" }}>({artifacts.length + systemCharts.length}) {systemCharts.length > 0 ? `含${systemCharts.length}张系统图表` : ""}</span>}
        </div>
        {showEvidence && (
          <div style={{ marginTop: 8 }}>
            {/* ── Unified Cards: 2-column grid, trend(top) + detail(bottom) ── */}
            {systemCharts.length > 0 && (
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
                {(() => {
                  const c = (t: string) => systemCharts.find((x: any) => x.chart_type === t);
                  const m = multiTrend;
                  return [
                    <UnifiedCard key="breadth" title="大盘势能" borderColor="#e53e3e">
                      {m?.breadth && <TrendLineChart title="涨停家数趋势 (6/25~7/8)" data={m.breadth} yKey="limit_up" yLabel="涨停" color="#e53e3e" />}
                      {c("market_breadth") && <ChartRenderer chart={c("market_breadth")} />}
                    </UnifiedCard>,
                    <UnifiedCard key="momentum" title="情绪动能" borderColor="#dd6b20">
                      {m?.momentum && <TrendLineChart title="情绪动能趋势 (6/25~7/8)" data={m.momentum} yKey="score" yLabel="动能" color="#dd6b20" />}
                      {c("emotion_momentum") && <ChartRenderer chart={c("emotion_momentum")} />}
                    </UnifiedCard>,
                    <UnifiedCard key="capital" title="活跃资金成交量" borderColor="#66d9ef">
                      {m?.capital && <TrendLineChart title="活跃资金趋势 (6/25~7/8)" data={m.capital} yKey="active_yi" yLabel="亿" color="#66d9ef" />}
                      {c("active_capital") && <ChartRenderer chart={c("active_capital")} />}
                    </UnifiedCard>,
                    <UnifiedCard key="relay" title="核心板块节律" borderColor="#805ad5">
                      {m?.relay && <TrendLineChart title="最高板趋势 (6/25~7/8)" data={m.relay} yKey="max_height" yLabel="板" color="#d69e2e" />}
                      {c("relay_ecology") && <ChartRenderer chart={c("relay_ecology")} />}
                    </UnifiedCard>,
                    ...["institution_style","hot_money_style","limitup_classification"].map(ct => {
                      const ch = c(ct); if (!ch) return null;
                      return <UnifiedCard key={ct} title={ch.title} borderColor="#5a7a8a"><ChartRenderer chart={ch} /></UnifiedCard>;
                    }).filter(Boolean),
                  ].flat().filter(Boolean);
                })()}
              </div>
            )}
            {/* PDF fallback */}
            {systemCharts.length === 0 && artifacts.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {artifacts.map(a => (
                  <div key={a.artifact_id} style={{ padding: 8, background: "#111720", borderRadius: 4, border: "1px solid #243040", width: 280, fontSize: 11 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                      <span style={{ fontWeight: 600, color: "#8ddcff" }}>{a.title}</span>
                      <span style={{ color: "#5a7a8a" }}>P{a.page_no || "?"}</span>
                    </div>
                    <div style={{ color: "#5a7a8a", marginBottom: 4 }}>{a.artifact_type === "table" ? "📊" : "📈"} {a.source}</div>
                    {a.summary && <div style={{ fontSize: 10, color: "#8ddcff", lineHeight: 1.4 }}>{a.summary}</div>}
                  </div>
                ))}
              </div>
            )}
            {systemCharts.length === 0 && artifacts.length === 0 && (
              <div style={{ fontSize: 11, color: "#5a7a8a", padding: 8 }}>该日期暂无图表证据</div>
            )}
          </div>
        )}
      </div>

    </div>
  );
}

// ── Unified Card: trend chart (top) + detail data (bottom) ──
function UnifiedCard({ title, borderColor, children }: { title: string; borderColor: string; children: React.ReactNode }) {
  return (
    <div style={{ padding: 12, background: "#111720", borderRadius: 6, border: `1px solid ${borderColor}20` }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", marginBottom: 10, fontSize: 14, borderLeft: `3px solid ${borderColor}`, paddingLeft: 10 }}>{title}</div>
      {children}
    </div>
  );
}
