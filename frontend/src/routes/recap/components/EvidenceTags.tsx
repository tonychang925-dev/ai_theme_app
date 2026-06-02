/** PR-14C: 证据层标签 — 主线 / Layer C / D1 / focus / 仅观察 / 非主线 / 回避。 */
import { Tag } from "antd";
import type { EvidenceAlignment } from "../../../lib/api";

interface Props {
  alignment?: EvidenceAlignment | null;
}

const TAG_CONFIG: Record<string, { color: string; label: string }> = {
  focus_stock: { color: "green", label: "focus" },
  d1_candidate: { color: "blue", label: "D1" },
  layer_c_tracking: { color: "geekblue", label: "Layer C" },
  tracking_only: { color: "default", label: "跟踪" },
  d1: { color: "blue", label: "D1" },
};

export default function EvidenceTags({ alignment }: Props) {
  if (!alignment || !alignment.active_mainline) {
    return <Tag color="default" style={{ fontSize: 10 }}>非主线</Tag>;
  }

  const tags: JSX.Element[] = [];

  // Mainline tag
  tags.push(<Tag key="ml" color="purple" style={{ fontSize: 10 }}>{alignment.mainline_name || "主线"}</Tag>);

  // Lifecycle state
  if (alignment.lifecycle_state) {
    const stateColors: Record<string, string> = {
      fade_watch: "volcano", fade_confirmed: "red", dead: "red",
      divergence: "orange", repair: "geekblue",
      fermentation: "green", acceleration: "cyan",
      start: "blue",
    };
    tags.push(<Tag key="state" color={stateColors[alignment.lifecycle_state] || "default"} style={{ fontSize: 10 }}>{alignment.lifecycle_state}</Tag>);
  }

  // Layer C
  if (alignment.in_layer_c) {
    tags.push(<Tag key="lc" color="geekblue" style={{ fontSize: 10 }}>Layer C</Tag>);
  }

  // D1
  if (alignment.is_d1_candidate) {
    tags.push(<Tag key="d1" color="blue" style={{ fontSize: 10 }}>{alignment.d1_level || "D1"}</Tag>);
  }

  // Focus
  if (alignment.is_focus_stock) {
    tags.push(<Tag key="focus" color="green" style={{ fontSize: 10 }}>focus</Tag>);
  }

  // Trade action
  const actionColors: Record<string, string> = {
    focus: "green", d1_formal: "green", d1_observe: "orange",
    observe_only: "orange", avoid: "red",
  };
  const actionLabels: Record<string, string> = {
    focus: "可交易", d1_formal: "D1确认", d1_observe: "仅观察",
    observe_only: "仅观察", avoid: "回避",
  };
  const action = alignment.trade_action;
  if (action && action !== "focus" && action !== "d1_formal") {
    tags.push(<Tag key="act" color={actionColors[action] || "default"} style={{ fontSize: 10 }}>{actionLabels[action] || action}</Tag>);
  }

  return <span style={{ display: "inline-flex", gap: 2, flexWrap: "wrap" }}>{tags}</span>;
}
