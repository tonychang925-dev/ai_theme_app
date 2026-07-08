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

function ScoreBar({ label, score, color = "#66d9ef" }: { label: string; score: number; color?: string }) {
  const pct = Math.max(0, Math.min(100, (score + 100) / 2));
  return (
    <div style={{ marginBottom: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 2 }}>
        <span style={{ color: "#8ddcff" }}>{label}</span>
        <span style={{ color: score >= 0 ? "#39ff14" : "#e53e3e" }}>{score}</span>
      </div>
      <div style={{ height: 4, background: "#1a2a3a", borderRadius: 2 }}>
        <div style={{ width: `${pct}%`, height: "100%", background: color, borderRadius: 2 }} />
      </div>
    </div>
  );
}

export function EmotionDashboard({ tradeDate }: { tradeDate: string }) {
  const [emotion, setEmotion] = useState<EmotionState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetch(`/api/v1/emotion/${tradeDate}`)
      .then(r => r.json()).then(d => { setEmotion(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, [tradeDate]);

  if (loading) return <div style={{ padding: 12, color: "#5a7a8a", fontSize: 13 }}>加载情绪数据…</div>;
  if (!emotion) return <div style={{ padding: 12, color: "#5a7a8a", fontSize: 13 }}>无情绪数据</div>;

  const node = emotion.emotion_node;
  const color = NODE_COLORS[node] || "#5a7a8a";

  return (
    <div style={{ padding: 12, background: "#0c1118", border: `1px solid ${color}40`, borderRadius: 8, color: "#8ddcff" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
        <span style={{ fontSize: 15, fontWeight: 700, color }}>{NODE_ICONS[node] || ""} {node}</span>
        <span style={{ fontSize: 13, color: "#8ddcff" }}>{emotion.emotion_desc}</span>
        <span style={{ fontSize: 20, fontWeight: 800, color }}>{emotion.emotion_score}</span>
      </div>

      {/* Scores */}
      <ScoreBar label={`大盘势能 ${emotion.breadth_label}`} score={emotion.breadth_score} color="#38a169" />
      <ScoreBar label={`情绪动能 ${emotion.momentum_label}`} score={emotion.momentum_score} color="#dd6b20" />
      <ScoreBar label={`接力生态 ${emotion.relay_label}`} score={emotion.relay_score} color="#3182ce" />
      <ScoreBar label={`活跃资金 ${emotion.capital_label}`} score={emotion.capital_score} color="#805ad5" />
      <ScoreBar label={`风格切换 ${emotion.style_label}`} score={emotion.style_score} color="#d69e2e" />

      {/* Raw metrics */}
      {emotion.raw && Object.keys(emotion.raw).length > 0 && (
        <div style={{ marginTop: 10, padding: 8, background: "#111720", borderRadius: 4, display: "flex", flexWrap: "wrap", gap: 8 }}>
          {emotion.raw.limit_up !== undefined && <MetricChip label="涨停" value={String(emotion.raw.limit_up)} color="#e53e3e" />}
          {emotion.raw.turnover_yi !== undefined && <MetricChip label="成交额" value={`${emotion.raw.turnover_yi}万亿`} color="#d69e2e" />}
          {emotion.raw.yesterday_premium_pct !== undefined && <MetricChip label="昨日溢价" value={`${emotion.raw.yesterday_premium_pct}%`} color="#38a169" />}
          {emotion.raw.yesterday_fail_pct !== undefined && <MetricChip label="大面率" value={`${emotion.raw.yesterday_fail_pct}%`} color="#e53e3e" />}
          {emotion.raw.up_count !== undefined && <MetricChip label="涨跌比" value={`${emotion.raw.up_count}/${emotion.raw.down_count}`} color="#66d9ef" />}
        </div>
      )}

      {/* Evidence */}
      {emotion.key_evidence.length > 0 && (
        <div style={{ marginTop: 8 }}>
          {emotion.key_evidence.map((ev, i) => (
            <div key={i} style={{ fontSize: 11, color: "#5a7a8a", padding: "1px 0" }}>{ev}</div>
          ))}
        </div>
      )}

      {/* Strategy */}
      <div style={{ marginTop: 8, padding: "6px 10px", background: color + "20", borderRadius: 4, fontSize: 12, color }}>
        {emotion.strategy_bias}
      </div>
    </div>
  );
}

function MetricChip({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <span style={{ fontSize: 11, padding: "2px 6px", background: color + "15", borderRadius: 3, color }}>
      {label}: <strong>{value}</strong>
    </span>
  );
}
