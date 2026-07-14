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
  confidence: number;
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

// ── Node derivation helper (pure, no fetch) ──
function deriveNode(score: number): string {
  if (score < -10) return "ICE_POINT";
  if (score < -5) return "FADE";
  if (score < 0) return "DIVERGENCE";
  if (score > 5) return "CLIMAX";
  if (score > 0) return "FERMENTATION";
  return "CHAOS";
}

// ── Main Component ──
export function EmotionDashboard({ tradeDate, tomorrowOutlook, tomorrowWatchpoints, tomorrowForbidden, reviewDocument }: {
  tradeDate: string;
  tomorrowOutlook?: string;
  tomorrowWatchpoints?: string[];
  tomorrowForbidden?: string[];
  reviewDocument?: Record<string, any> | null;
}) {
  const watchpoints = tomorrowWatchpoints || [];
  const forbidden = tomorrowForbidden || [];
  const [emotion, setEmotion] = useState<EmotionState | null>(null);
  const [loading, setLoading] = useState(true);
  const [artifacts, setArtifacts] = useState<EvidenceArtifact[]>([]);
  const [showEvidence, setShowEvidence] = useState(false);
  const [systemCharts, setSystemCharts] = useState<any[]>([]);
  const [multiTrend, setMultiTrend] = useState<any>(null);

  // Derive trend timeline from reviewDocument.evidence.trend_series.momentum
  const trendSeries = reviewDocument?.evidence?.trend_series;
  const trend: { date: string; node: string; score: number }[] = (trendSeries?.momentum || []).map((m: any) => ({
    date: m.date,
    score: m.score ?? 0,
    node: deriveNode(m.score ?? 0),
  }));

  // PR4.5.7: Single data source — ReviewDocument.
  // All emotion/chart/trend data flows from the backend assembler, not from raw JSON.
  useEffect(() => {
    const rdEmotion = reviewDocument?.emotion;
    const rdMarket = reviewDocument?.market;
    if (rdEmotion && (rdEmotion.phase || rdEmotion.score != null)) {
      setEmotion({
        trade_date: tradeDate,
        emotion_node: rdEmotion.phase || null,
        emotion_desc: rdEmotion.strategy || null,
        emotion_score: rdEmotion.score ?? 0,
        confidence: rdEmotion.confidence ?? 0.5,
        breadth_score: rdMarket?.breadth_score ?? 0,
        breadth_label: rdMarket?.breadth_label ?? "",
        momentum_score: 0, momentum_label: "",
        relay_score: 0, relay_label: "",
        capital_score: 0, capital_label: "",
        style_score: 0, style_label: "",
        key_evidence: rdEmotion.key_evidence || [],
        strategy_bias: rdEmotion.strategy || null,
        raw: {
          limit_up: rdMarket?.limit_up_count,
          turnover_yi: rdMarket?.active_capital_yi,
          up_count: rdMarket?.up_count,
          down_count: rdMarket?.down_count,
        } as any,
      } as EmotionState);
      setLoading(false);
      return;
    }
    setEmotion(null);
    setLoading(false);
  }, [tradeDate, reviewDocument]);

  useEffect(() => {
    const trends = reviewDocument?.evidence?.trend_series;
    if (trends && Object.keys(trends).length > 0) {
      setMultiTrend(trends);
    }
  }, [tradeDate, reviewDocument]);

  useEffect(() => {
    const charts = reviewDocument?.evidence?.charts;
    if (Array.isArray(charts) && charts.length > 0) {
      setSystemCharts(charts);
    }
  }, [tradeDate, reviewDocument]);

  if (loading) return <div style={{ padding: "8px 16px", color: "#5a7a8a", fontSize: 13 }}>加载情绪数据…</div>;
  if (!emotion || !emotion.emotion_node) return <div style={{ padding: "8px 16px", color: "#ffa940", fontSize: 13 }}>该日期暂无情绪分析，请点击「启动分析」生成复盘动态数据</div>;

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
            Confidence {Math.round((emotion.confidence ?? 0.5) * 100)}%
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
          {watchpoints.length > 0 && (
            <div style={{ marginBottom: 3 }}>
              {watchpoints.slice(0, 3).map((wp, i) => (
                <div key={i} style={{ fontSize: 10, color: "#8ddcff", padding: "1px 0" }}>• {wp}</div>
              ))}
            </div>
          )}
          {forbidden.length > 0 && (
            <div>
              {forbidden.slice(0, 2).map((fb, i) => (
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
                    <UnifiedCard key="capital" title="资金驱动" borderColor="#66d9ef">
                      {m?.capital && <TrendLineChart title="活跃资金趋势 (6/25~7/8)" data={m.capital} yKey="amount" yLabel="亿" color="#66d9ef" />}
                      {c("active_capital") && <ChartRenderer chart={c("active_capital")} />}
                      <CapitalDirectionCard title="机构资金审美方向" rows={reviewDocument?.capital?.institution_style || []} kind="institution" />
                      <CapitalDirectionCard title="游资情绪方向" rows={reviewDocument?.capital?.hot_money_style || []} kind="hot_money" />
                    </UnifiedCard>,
                    <UnifiedCard key="relay" title="核心板块节律" borderColor="#805ad5">
                      {m?.relay && <TrendLineChart title="最高板趋势 (6/25~7/8)" data={m.relay} yKey="max_height" yLabel="板" color="#d69e2e" />}
                      {c("relay_ecology") && <ChartRenderer chart={c("relay_ecology")} />}
                    </UnifiedCard>,
                    ...["limitup_classification"].map(ct => {
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

// ── PR4.2.37b: Capital Direction Card (reads canonical capital.*_style contract) ──
function CapitalDirectionCard({ title, rows, kind }: { title: string; rows: any[]; kind: "institution" | "hot_money" }) {
  if (!rows || rows.length === 0) return null;
  const display = rows.slice(0, 5);
  const isInst = kind === "institution";
  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontWeight: 700, color: "#ffd85e", fontSize: 13, marginBottom: 6 }}>{title}</div>
      {display.map((row: any, i: number) => {
        const name = row.direction_name || row.theme_name || "";
        const score = row.score ?? 0;
        const conf = row.confidence != null ? Math.round(row.confidence * 100) : null;
        const stage = row.lifecycle_stage || row.attack_stage || "";
        const stageText = _cs(stage);
        const stars = score >= 80 ? "★★★★★" : score >= 65 ? "★★★★☆" : score >= 50 ? "★★★☆☆" : score >= 35 ? "★★☆☆☆" : "★☆☆☆☆";
        return (
          <div key={i} style={{ display: "grid", gridTemplateColumns: "minmax(0,1fr) auto auto", gap: 6, padding: "6px 0", borderTop: "1px solid #243040", fontSize: 12, alignItems: "center" }}>
            <span style={{ color: "#d8e6ef", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis" }}>{name}</span>
            <span style={{ color: "#6f8898", fontSize: 11 }}>
              {stars} {score.toFixed(0)}{conf != null ? ` ${conf}%` : ""}{stageText ? ` ${stageText}` : ""}
            </span>
            <span style={{ color: "#66d9ef", fontWeight: 700, textAlign: "right", minWidth: 28 }}>{score.toFixed(0)}</span>
          </div>
        );
      })}
    </div>
  );
}
const _CS: Record<string,string> = {"fermentation":"发酵","FERMENTATION":"发酵","divergence":"分歧","DIVERGENCE":"分歧","start":"启动","START":"启动","incubation":"孵化","INCUBATION":"孵化","FIRST_WAVE":"首波","CONTINUING":"持续","CLIMAX":"高潮","RETREATING":"退却","decay":"衰退","DECAY":"衰退"};
function _cs(s: string): string { return _CS[s] || s || ""; }
