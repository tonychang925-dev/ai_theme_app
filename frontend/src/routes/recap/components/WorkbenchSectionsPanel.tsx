/** Phase 4.5.5 — Workbench Sections Panel.

Renders AI + analyst approved workbench content as first-class recap sections:
  - emotion_review (情绪复盘)
  - market_chart_reviews (AI 图表解读)
  - workbench_approval badge (preview/formal/published)
*/

import React from "react";
import type { EmotionReview, MarketChartReview, WorkbenchApproval } from "../../../lib/api";

// ── Emotion node colors ──

const NODE_COLORS: Record<string, string> = {
  CLIMAX: "#e53e3e", ACCELERATION: "#dd6b20", FERMENTATION: "#d69e2e",
  REPAIR: "#38a169", REBOUND: "#38a169", DIVERGENCE: "#3182ce",
  FADE: "#805ad5", ICE_POINT: "#66d9ef", CHAOS: "#5a7a8a",
};
const NODE_ICONS: Record<string, string> = {
  CLIMAX: "🔥", ACCELERATION: "⚡", FERMENTATION: "🌱",
  REPAIR: "🔧", REBOUND: "🔧", DIVERGENCE: "⚔️",
  FADE: "📉", ICE_POINT: "❄️", CHAOS: "🌫️",
};
const RISK_COLORS: Record<string, string> = {
  LOW: "#38a169", MEDIUM: "#d69e2e", HIGH: "#e53e3e", EXTREME: "#805ad5", UNKNOWN: "#5a7a8a",
};
const CHART_STATUS_COLORS: Record<string, string> = {
  "活跃": "#38a169", "亢奋": "#e53e3e", "回流": "#66d9ef", "改善": "#38a169",
  "偏积极": "#38a169", "中性": "#d69e2e", "收缩": "#e53e3e", "退潮": "#dd6b20",
  "冰点": "#66d9ef", "流出": "#e53e3e", "恶化": "#e53e3e", "偏防御": "#dd6b20",
  "无数据": "#5a7a8a",
};
const CHART_ICONS: Record<string, string> = {
  market_breadth: "📊", emotion_momentum: "📈", active_capital: "💰",
  relay_ecology: "🔄", institution_style: "🏛️", hot_money_style: "🎯",
};

// ── Approval Badge ──

function ApprovalBadge({ approval }: { approval: WorkbenchApproval }) {
  const isFormal = approval.mode === "formal" || approval.mode === "published";
  const bg = isFormal ? "#38a16915" : approval.mode === "blocked" ? "#e53e3e15" : "#d69e2e15";
  const border = isFormal ? "#38a16940" : approval.mode === "blocked" ? "#e53e3e40" : "#d69e2e40";
  const color = isFormal ? "#38a169" : approval.mode === "blocked" ? "#e53e3e" : "#d69e2e";
  const label = approval.mode === "formal" ? `✅ 正式报告 · snapshot_v${approval.snapshot_version}`
    : approval.mode === "published" ? `🔒 已发布 · snapshot_v${approval.snapshot_version}`
    : approval.mode === "blocked" ? "🚫 状态异常"
    : "👁️ 仅预览 · 待审核";
  const by = approval.approved_by ? ` · by ${approval.approved_by}` : "";

  return (
    <div style={{
      display: "inline-flex", alignItems: "center", gap: 8,
      padding: "6px 14px", borderRadius: 6,
      background: bg, border: `1px solid ${border}`,
      fontSize: 12, color, fontWeight: 600,
      marginBottom: 12,
    }}>
      <span>{label}{by}</span>
      {!isFormal && (
        <span style={{ fontSize: 10, color: "#5a7a8a" }}>
          {approval.session_status}
        </span>
      )}
    </div>
  );
}

// ── Emotion Review Card ──

function EmotionReviewCard({ emo }: { emo: EmotionReview }) {
  if (!emo || !emo.emotion_node) return null;

  const node = emo.emotion_node;
  const color = NODE_COLORS[node] || "#5a7a8a";
  const riskColor = RISK_COLORS[emo.risk_level] || "#5a7a8a";

  return (
    <div style={{
      padding: 16, borderRadius: 8,
      background: "#111720", border: "1px solid #243040",
      marginBottom: 12,
    }}>
      {/* Header: node + score + risk */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <span style={{ fontSize: 32 }}>{NODE_ICONS[node] || "📊"}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color }}>{emo.emotion_label || node}</div>
          <div style={{ fontSize: 11, color: "#5a7a8a" }}>{node}</div>
        </div>
        <div style={{ textAlign: "center", minWidth: 70 }}>
          <div style={{ fontSize: 28, fontWeight: 800, color }}>{emo.emotion_score}</div>
          <div style={{ fontSize: 10, color: "#5a7a8a" }}>/ 100</div>
        </div>
        <div style={{
          padding: "4px 12px", borderRadius: 4, textAlign: "center",
          background: riskColor + "20", border: `1px solid ${riskColor}40`,
        }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: riskColor }}>{emo.risk_level}</div>
          <div style={{ fontSize: 9, color: "#5a7a8a" }}>风险等级</div>
        </div>
      </div>

      {/* Summary + strategy */}
      {emo.summary && (
        <div style={{ fontSize: 13, color: "#8ddcff", lineHeight: 1.6, marginBottom: 10,
          padding: "8px 12px", background: "#0c1118", borderRadius: 4 }}>
          {emo.summary}
        </div>
      )}

      <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 8 }}>
        {emo.strategy_bias && (
          <div style={{ fontSize: 12 }}>
            <span style={{ color: "#5a7a8a" }}>策略倾向：</span>
            <span style={{ color: "#ffd85e", fontWeight: 600 }}>{emo.strategy_bias}</span>
          </div>
        )}
        <div style={{ fontSize: 12 }}>
          <span style={{ color: "#5a7a8a" }}>置信度：</span>
          <span style={{ color: "#66d9ef" }}>{(emo.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>

      {/* 5 dimension scores */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8, marginBottom: 10 }}>
        {(["breadth", "momentum", "relay", "capital", "style"] as const).map(dim => {
          const score = emo[`${dim}_score` as keyof EmotionReview] as number || 0;
          const label = emo[`${dim}_label` as keyof EmotionReview] as string || "";
          const barColor = score > 20 ? "#38a169" : score > 0 ? "#d69e2e" : score > -20 ? "#dd6b20" : "#e53e3e";
          const dimLabels: Record<string, string> = {
            breadth: "赚钱效应", momentum: "情绪动能", relay: "接力生态", capital: "资金面", style: "风格偏好",
          };
          return (
            <div key={dim} style={{ textAlign: "center", padding: "6px 4px", background: "#0c1118", borderRadius: 4 }}>
              <div style={{ fontSize: 10, color: "#5a7a8a", marginBottom: 2 }}>{dimLabels[dim]}</div>
              <div style={{ fontSize: 16, fontWeight: 700, color: barColor }}>{score}</div>
              <div style={{ height: 3, background: "#1a2a3a", borderRadius: 2, margin: "4px 0" }}>
                <div style={{ width: `${Math.max(5, ((score + 30) / 60) * 100)}%`, height: "100%", background: barColor, borderRadius: 2 }} />
              </div>
              <div style={{ fontSize: 9, color: "#8ddcff" }}>{label}</div>
            </div>
          );
        })}
      </div>

      {/* Evidence */}
      {emo.key_evidence?.length > 0 && (
        <div style={{ marginBottom: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#8ddcff", marginBottom: 4 }}>关键证据</div>
          {emo.key_evidence.map((ev, i) => (
            <div key={i} style={{ fontSize: 11, color: "#5a7a8a", padding: "1px 0" }}>✓ {ev}</div>
          ))}
        </div>
      )}

      {/* Analyst adjustment */}
      {emo.analyst_adjustment?.modified && (
        <div style={{ padding: "8px 12px", background: "#d69e2e10", border: "1px solid #d69e2e30", borderRadius: 4, fontSize: 11 }}>
          <span style={{ color: "#d69e2e", fontWeight: 600 }}>分析师修正：</span>
          <span style={{ color: "#e53e3e", textDecoration: "line-through", margin: "0 4px" }}>{emo.analyst_adjustment.from}</span>
          <span style={{ color: "#8ddcff" }}>→</span>
          <span style={{ color: "#38a169", margin: "0 4px" }}>{emo.analyst_adjustment.to}</span>
          <span style={{ color: "#5a7a8a" }}>— {emo.analyst_adjustment.reason}</span>
        </div>
      )}
    </div>
  );
}

// ── Chart Review Card ──

function ChartReviewCard({ chart }: { chart: MarketChartReview }) {
  const icon = CHART_ICONS[chart.chart_type] || "📈";
  const statusColor = CHART_STATUS_COLORS[chart.status] || "#5a7a8a";

  return (
    <div style={{
      padding: 14, borderRadius: 6,
      background: "#111720", border: `1px solid ${statusColor}20`,
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 18 }}>{icon}</span>
        <span style={{ fontSize: 14, fontWeight: 700, color: "#ffd85e" }}>{chart.title}</span>
        <span style={{
          fontSize: 11, padding: "2px 8px", borderRadius: 10,
          background: statusColor + "20", color: statusColor, fontWeight: 600,
        }}>
          {chart.status}
        </span>
        {chart.score !== null && chart.score !== undefined && (
          <span style={{ fontSize: 12, color: "#8ddcff", marginLeft: "auto" }}>
            {typeof chart.score === "number" ? chart.score.toFixed(1) : String(chart.score)}
          </span>
        )}
      </div>

      {/* Summary */}
      <div style={{ fontSize: 12, color: "#8ddcff", lineHeight: 1.5, marginBottom: 8 }}>
        {chart.summary}
      </div>

      {/* Key metrics */}
      {Object.keys(chart.key_metrics).length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
          {Object.entries(chart.key_metrics).slice(0, 4).map(([k, v]) => {
            const display = typeof v === "number" ? (v < 1 ? `${(v * 100).toFixed(0)}%` : String(v)) : String(v ?? "—");
            return (
              <div key={k} style={{
                padding: "3px 8px", background: "#0c1118", borderRadius: 3,
                fontSize: 10, color: "#66d9ef",
              }}>
                {k}: <span style={{ fontWeight: 600 }}>{display}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Evidence */}
      {chart.evidence?.length > 0 && (
        <div style={{ fontSize: 10, color: "#5a7a8a", lineHeight: 1.4 }}>
          {chart.evidence[0]}
        </div>
      )}

      {/* Analyst note */}
      {chart.analyst_note && (
        <div style={{ marginTop: 6, padding: "4px 8px", background: "#d69e2e10", borderRadius: 3, fontSize: 10, color: "#d69e2e" }}>
          📝 {chart.analyst_note}
        </div>
      )}
    </div>
  );
}

// ── Data quality warning ──

function DataQualityNotice({ emo, charts }: {
  emo?: EmotionReview | null;
  charts?: MarketChartReview[] | null;
}) {
  const issues: string[] = [];
  if (emo) {
    if ((emo.source_quality ?? 1) < 0.6) issues.push("情绪数据质量低");
    if (emo.missing_fields?.length) issues.push(`情绪缺失字段: ${emo.missing_fields.join(", ")}`);
  }
  if (charts) {
    const lowQ = charts.filter(c => (c.source_quality ?? 1) < 0.6);
    if (lowQ.length) issues.push(`${lowQ.length} 张图表数据质量低`);
  }
  if (!issues.length) return null;
  return (
    <div style={{
      padding: "8px 12px", borderRadius: 4, marginBottom: 10,
      background: "#ffd85e10", border: "1px solid #ffd85e30",
      fontSize: 11, color: "#ffd85e",
    }}>
      ⚡ 数据质量提醒：{issues.join("；")}
    </div>
  );
}

// ── Main Panel ──

export function WorkbenchSectionsPanel({ data }: {
  data: {
    emotion_review?: EmotionReview | null;
    market_chart_reviews?: MarketChartReview[] | null;
    workbench_approval?: WorkbenchApproval | null;
    attention_review?: Record<string, unknown> | null;
    cognition_reviews?: Record<string, unknown>[] | null;
    narrative_review?: Record<string, unknown> | null;
    playbook_review?: Record<string, unknown> | null;
    analyst_override_review?: Record<string, unknown> | null;
  };
}) {
  const approval = data.workbench_approval;
  const emo = data.emotion_review;
  const charts = data.market_chart_reviews;

  // (1) Hide panel if no workbench data at all
  if (!approval && !emo && (!charts || charts.length === 0)) return null;

  const isBlocked = approval?.mode === "blocked";
  const isPreview = approval && !approval.can_generate_formal_report && !isBlocked;
  const hasEmotion = emo && emo.emotion_node;
  const hasCharts = charts && charts.length > 0;

  return (
    <div style={{ marginBottom: 16 }}>
      {/* Section header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
        <h2 className="recap-panel-title" style={{ margin: 0, fontSize: 16 }}>
          🧠 AI + 分析师协同复盘
        </h2>
        {approval && <ApprovalBadge approval={approval} />}
      </div>

      {/* (4) Blocked mode — red error banner */}
      {isBlocked && (
        <div style={{
          padding: "12px 16px", borderRadius: 6, marginBottom: 12,
          background: "#e53e3e10", border: "1px solid #e53e3e30",
        }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: "#e53e3e", marginBottom: 4 }}>
            🚫 报告状态异常 — Session {approval?.session_status} 但 Snapshot 丢失
          </div>
          <div style={{ fontSize: 12, color: "#d4886b", lineHeight: 1.5 }}>
            {approval?.reason}
          </div>
        </div>
      )}

      {/* (3) Preview mode notice */}
      {isPreview && (
        <div style={{
          padding: "10px 14px", borderRadius: 6, marginBottom: 12,
          background: "#d69e2e10", border: "1px solid #d69e2e30",
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: "#ffd85e", marginBottom: 4 }}>
            👁️ 预览模式 · 待分析师审核
          </div>
          <div style={{ fontSize: 12, color: "#8da6b8", lineHeight: 1.5 }}>
            Workbench 状态为 <b>{approval?.session_status}</b>。
            需完成 AI Draft → 审核 → Approve 后生成正式报告。
          </div>
        </div>
      )}

      {/* (5) Data quality reminder */}
      <DataQualityNotice emo={emo} charts={charts} />

      {/* (1) Emotion — only show when data exists */}
      {hasEmotion ? (
        <EmotionReviewCard emo={emo!} />
      ) : (
        emo && !emo.emotion_node && (
          <div style={{
            padding: "16px", borderRadius: 6, marginBottom: 12, textAlign: "center",
            background: "#111720", border: "1px solid #243040",
            fontSize: 13, color: "#5a7a8a",
          }}>
            暂无情绪复盘数据。请点击「启动分析」生成。
          </div>
        )
      )}

      {/* (2) Chart — show placeholder when empty */}
      <div style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: "#ffd85e", marginBottom: 10, borderLeft: "3px solid #66d9ef", paddingLeft: 10 }}>
          AI 图表解读
        </div>
        {hasCharts ? (
          <div style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
            gap: 10,
          }}>
            {charts.map((c, i) => (
              <ChartReviewCard key={`${c.chart_type}-${i}`} chart={c} />
            ))}
          </div>
        ) : (
          <div style={{
            padding: "16px", borderRadius: 6, textAlign: "center",
            background: "#111720", border: "1px solid #243040",
            fontSize: 13, color: "#5a7a8a",
          }}>
            暂无图表解读数据。请点击「启动分析」生成 AI 图表。
          </div>
        )}
      </div>
    </div>
  );
}
