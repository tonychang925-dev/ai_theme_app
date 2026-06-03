import { Tag } from "antd";
import type { MainlineNarrative } from "../../../lib/api";

interface Props {
  narrative?: MainlineNarrative | null;
}

export default function MainlineNarrativePanel({ narrative }: Props) {
  if (!narrative) return null;

  return (
    <div style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 8, padding: 14, marginBottom: 14 }}>
      <h3 className="section-title recap-panel-title">
        主线叙述
        <Tag color="blue" style={{ marginLeft: 8 }}>结构总结</Tag>
        {narrative.source && <Tag color={narrative.source === "engine_template" ? "green" : "blue"}>{narrative.source}</Tag>}
      </h3>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">主线总结</div>
        <p className="workspace-note">{narrative.summary}</p>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">核心要点</div>
        <ul className="workspace-list">
          {narrative.core_points.map((point, idx) => (
            <li key={`mainline-point-${idx}`}>
              <p className="workspace-note">{point}</p>
            </li>
          ))}
        </ul>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">分歧主线</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {narrative.divergence_mainlines.length > 0 ? narrative.divergence_mainlines.map((item) => <Tag key={item} color="orange">{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">退潮主线</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {narrative.fade_mainlines.length > 0 ? narrative.fade_mainlines.map((item) => <Tag key={item} color="red">{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card" style={{ marginBottom: 12 }}>
        <div className="metric-label section-title">观察主线</div>
        <div className="recap-tag-stack" style={{ flexWrap: "wrap" }}>
          {narrative.watch_only_mainlines.length > 0 ? narrative.watch_only_mainlines.map((item) => <Tag key={item}>{item}</Tag>) : <span className="workspace-note">--</span>}
        </div>
      </div>

      <div className="workspace-card">
        <div className="metric-label section-title">行动摘要</div>
        <p className="workspace-note">{narrative.action_summary}</p>
      </div>
    </div>
  );
}
