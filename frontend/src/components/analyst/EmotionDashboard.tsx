import React, { useEffect, useState } from "react";

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
  REPAIR: "情绪修复", DIVERGENCE: "情绪退潮", FADE: "情绪衰退",
  ICE_POINT: "情绪冰点", CHAOS: "情绪混沌",
};

function Stars({ count }: { count: number }) {
  const full = Math.round(count);
  return <span style={{ fontSize: 12, letterSpacing: 1 }}>{"★".repeat(full)}{"☆".repeat(5 - full)}</span>;
}

function signalBar(value: number, max = 100) {
  const pct = Math.max(0, Math.min(100, (value + max) / (2 * max) * 100));
  const color = value > 0 ? "#38a169" : value < -30 ? "#e53e3e" : "#d69e2e";
  return <div style={{ height: 3, background: "#1a2a3a", borderRadius: 2, flex: 1, minWidth: 40 }}>
    <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2 }} />
  </div>;
}

// ── Trend data helper ──
function useEmotionTrend(tradeDate: string) {
  const [trend, setTrend] = useState<{ date: string; node: string; score: number }[]>([]);

  useEffect(() => {
    const dates: string[] = [];
    const d = new Date(tradeDate);
    for (let i = 4; i >= 0; i--) {
      const prev = new Date(d);
      prev.setDate(prev.getDate() - i * 1);
      // Skip weekends roughly
      const day = prev.getDay();
      if (day === 0) prev.setDate(prev.getDate() - 2);
      if (day === 6) prev.setDate(prev.getDate() - 1);
      dates.push(prev.toISOString().slice(0, 10));
    }

    Promise.all(
      dates.map(dt =>
        fetch(`/api/v1/emotion/${dt}`)
          .then(r => r.json())
          .then(data => ({ date: dt, node: (data && data.emotion_node) || "CHAOS", score: (data && data.emotion_score) || 0 }))
          .catch(() => ({ date: dt, node: "CHAOS", score: 0 }))
      )
    ).then(setTrend);
  }, [tradeDate]);

  return trend;
}

// ── Main Component ──
export function EmotionDashboard({ tradeDate }: { tradeDate: string }) {
  const [emotion, setEmotion] = useState<EmotionState | null>(null);
  const [loading, setLoading] = useState(true);
  const trend = useEmotionTrend(tradeDate);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/v1/emotion/${tradeDate}`)
      .then(r => r.json()).then(d => { setEmotion(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tradeDate]);

  if (loading) return <div style={{ padding: "8px 16px", color: "#5a7a8a", fontSize: 13 }}>加载情绪数据…</div>;
  if (!emotion || !emotion.emotion_node) return <div style={{ padding: "8px 16px", color: "#5a7a8a", fontSize: 13 }}>无情绪数据</div>;

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

      {/* ── Row 3: Why Panel + Next Probability + Trading Mode ── */}
      <div style={{ marginTop: 10, display: "grid", gridTemplateColumns: "1fr 200px 260px", gap: 12 }}>

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
        <div style={{ padding: 8, background: "#111720", borderRadius: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#ffd85e", marginBottom: 6 }}>明日预测</div>
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
        <div style={{ padding: 8, background: "#111720", borderRadius: 4 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#66d9ef", marginBottom: 6 }}>今日交易模式</div>
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
      </div>

    </div>
  );
}
