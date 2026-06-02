/** PR-14C: 证据层标签 — 主线 / Layer C / D1 / focus / 仅观察 / 非主线 / 回避。 */
import { Tag } from "antd";
import type { EvidenceAlignment } from "../../../lib/api";

interface Props {
  alignment?: EvidenceAlignment | null;
}

const STATE_LABELS: Record<string, string> = {
  start: "启动",
  fermentation: "发酵",
  acceleration: "加速",
  divergence: "分歧",
  repair: "修复",
  fade_watch: "退潮观察",
  fade_confirmed: "退潮确认",
  dead: "衰竭",
  unknown: "未知",
};

export default function EvidenceTags({ alignment }: Props) {
  if (!alignment || !alignment.active_mainline) {
    return <Tag color="default">非主线</Tag>;
  }

  const tags: JSX.Element[] = [];

  // Mainline tag
  tags.push(<Tag key="ml" color="purple">{alignment.mainline_name || "主线"}</Tag>);

  // Lifecycle state
  if (alignment.lifecycle_state) {
    const stateColors: Record<string, string> = {
      fade_watch: "volcano", fade_confirmed: "red", dead: "red",
      divergence: "orange", repair: "geekblue",
      fermentation: "green", acceleration: "cyan",
      start: "blue",
    };
    tags.push(<Tag key="state" color={stateColors[alignment.lifecycle_state] || "default"}>{STATE_LABELS[alignment.lifecycle_state] || alignment.lifecycle_state}</Tag>);
  }

  // Layer C
  if (alignment.in_layer_c) {
    tags.push(<Tag key="lc" color="geekblue">强势股池</Tag>);
  }

  // D1
  if (alignment.is_d1_candidate) {
    tags.push(<Tag key="d1" color="blue">{alignment.d1_level || "次日观察"}</Tag>);
  }

  // Focus
  if (alignment.is_focus_stock) {
    tags.push(<Tag key="focus" color="green">重点关注</Tag>);
  }

  // Trade action
  const actionColors: Record<string, string> = {
    focus: "green", d1_formal: "green", d1_observe: "orange",
    observe_only: "orange", avoid: "red",
  };
  const actionLabels: Record<string, string> = {
    focus: "可交易", d1_formal: "次日确认", d1_observe: "仅观察",
    observe_only: "仅观察", avoid: "回避",
  };
  const action = alignment.trade_action;
  if (action && action !== "focus" && action !== "d1_formal") {
    tags.push(<Tag key="act" color={actionColors[action] || "default"}>{actionLabels[action] || action}</Tag>);
  }

  return <span style={{ display: "inline-flex", gap: 2, flexWrap: "wrap" }}>{tags}</span>;
}
