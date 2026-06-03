import { Tag } from "antd";
import type { D1Narrative } from "../../../lib/api";

interface Props {
  narrative?: D1Narrative | null;
}

export default function D1NarrativePanel({ narrative }: Props) {
  if (!narrative) return null;

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        D1 叙述
        <Tag color="gold" style={{ marginLeft: 8 }}>次日观察</Tag>
        {narrative.source && <Tag color={narrative.source === "engine_template" ? "green" : "blue"}>{narrative.source}</Tag>}
      </h3>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">D1 总结</div>
        <p className="workspace-note">{narrative.summary}</p>
      </div>

      <div className="recap-tag-stack" style={{ flexWrap: "wrap", marginBottom: 12 }}>
        <Tag color="blue">候选 {narrative.candidate_count}</Tag>
        <Tag color="green">正式 {narrative.formal_count}</Tag>
        <Tag color="default">观察 {narrative.observe_count}</Tag>
        <Tag color="purple">focus {narrative.focus_count}</Tag>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">确认条件</div>
        <ul className="workspace-list">
          {narrative.confirmation_requirements.map((item, idx) => (
            <li key={`d1-confirm-${idx}`}>
              <p className="workspace-note">{item}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">失效条件</div>
        <ul className="workspace-list">
          {narrative.invalid_conditions.map((item, idx) => (
            <li key={`d1-invalid-${idx}`}>
              <p className="workspace-note">{item}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="workspace-card">
        <div className="metric-label section-title">风险提示</div>
        <p className="workspace-note">{narrative.risk_warning}</p>
      </div>
    </div>
  );
}
